"""P0-7 (Phase B) transactional people import tests (D-B1 / D-B2).

Real-link tests against a real SQLite database on ``tmp_path``: batched
unit-of-work scopes (D-B1 按批原子), mid-batch rollback semantics, row-level
error isolation, and identity-less name+department dedupe (D-B2). The bare
no-UoW path (in-memory repositories) is covered by
``test_application_service_workflows.py`` and stays backward compatible.
"""

from pathlib import Path

import pytest

from photo_archiver.application.dtos import PersonImportRow
from photo_archiver.application.services import ImportPeopleService
from photo_archiver.domain import Person, PersonIdentity, PersonRepository
from photo_archiver.infrastructure import SQLiteConnectionProvider, SQLiteUnitOfWork
from photo_archiver.infrastructure.database.sqlite_person_repository import SQLitePersonRepository


class _UnusedReader:
    """Reader stand-in: ``import_rows`` never touches the reader port."""

    def read(
        self,
        source_path: Path,
        has_header: bool = True,
        sheet_name: str | None = None,
    ) -> list[PersonImportRow]:
        """Satisfy the port; never called by the ``import_rows`` entry point."""
        return []


class _CrashOnNameRepository:
    """Wrap a real repository, raising a non-row-level error for one name.

    ``RuntimeError`` is deliberately outside the service's row-level catch
    (``ValueError``/``ValidationError``) so it simulates an unexpected crash
    inside a batch instead of a bad row.
    """

    def __init__(self, inner: PersonRepository, crash_name: str) -> None:
        """Store the inner repository and the name that must crash."""
        self._inner = inner
        self._crash_name = crash_name

    def add(self, person: Person) -> None:
        """Delegate to the inner repository unless the crash name is hit."""
        if person.name == self._crash_name:
            raise RuntimeError("simulated crash mid-batch")
        self._inner.add(person)

    def find_by_id(self, person_id) -> Person | None:  # noqa: ANN001 - test double
        """Delegate lookup to the inner repository."""
        return self._inner.find_by_id(person_id)

    def find_by_identity(self, identity: PersonIdentity) -> Person | None:
        """Delegate identity lookup to the inner repository."""
        return self._inner.find_by_identity(identity)

    def find_by_name_department(self, name: str, department: str | None) -> Person | None:
        """Delegate name/department lookup to the inner repository."""
        return self._inner.find_by_name_department(name, department)

    def list_all(self) -> list[Person]:
        """Delegate listing to the inner repository."""
        return self._inner.list_all()


def _row(
    name: str,
    *,
    identity: str | None = None,
    department: str | None = None,
    row_number: int | None = None,
) -> PersonImportRow:
    """Build a normalized import row with optional fields."""
    return PersonImportRow(
        name=name,
        identity=identity,
        department=department,
        row_number=row_number,
    )


@pytest.fixture()
def provider(tmp_path: Path) -> SQLiteConnectionProvider:
    """Return an initialized SQLite connection provider over a temp file."""
    provider = SQLiteConnectionProvider(tmp_path / "import.db")
    provider.initialize_schema()
    return provider


def _make_service(
    provider: SQLiteConnectionProvider,
    repository: PersonRepository | None = None,
    *,
    with_uow: bool = True,
    batch_size: int = 500,
) -> ImportPeopleService:
    """Build the service over real SQLite plumbing (or an injected repository)."""
    return ImportPeopleService(
        _UnusedReader(),
        repository if repository is not None else SQLitePersonRepository(provider),
        unit_of_work=SQLiteUnitOfWork(provider) if with_uow else None,
        batch_size=batch_size,
    )


def test_rows_persist_across_multiple_atomic_batches(provider: SQLiteConnectionProvider) -> None:
    """All rows of a multi-batch import persist and are reported (D-B1)."""
    repository = SQLitePersonRepository(provider)
    service = _make_service(provider, repository=repository, batch_size=2)
    rows = [_row(f"Person {index}", row_number=index + 1) for index in range(5)]

    result = service.import_rows(rows)

    persisted = {person.name for person in repository.list_all()}
    assert result.imported_count == 5
    assert result.skipped_count == 0
    assert result.errors == ()
    assert len(result.person_ids) == 5
    assert persisted == {"Person 0", "Person 1", "Person 2", "Person 3", "Person 4"}


def test_mid_batch_crash_rolls_back_current_batch_only(
    provider: SQLiteConnectionProvider,
) -> None:
    """A crash mid-batch rolls back that batch; earlier batches stay durable.

    batch_size=2, rows A1 A2 | BOOM A4 | A5: batch 1 commits, batch 2 raises
    RuntimeError from inside the UoW scope (rolled back) and stops the run, so
    A5 is never attempted. Exactly the "never a half-batch" contract.
    """
    inner = SQLitePersonRepository(provider)
    repository = _CrashOnNameRepository(inner, crash_name="BOOM")
    service = _make_service(provider, repository=repository, batch_size=2)
    rows = [
        _row("A1", row_number=1),
        _row("A2", row_number=2),
        _row("BOOM", row_number=3),
        _row("A4", row_number=4),
        _row("A5", row_number=5),
    ]

    with pytest.raises(RuntimeError, match="simulated crash mid-batch"):
        service.import_rows(rows)

    persisted = {person.name for person in inner.list_all()}
    assert persisted == {"A1", "A2"}, "batch 1 must stay committed, batch 2 rolled back"


def test_row_level_error_is_isolated_and_batch_survives(
    provider: SQLiteConnectionProvider,
) -> None:
    """A bad row is recorded with its row number; neighbours still import."""
    repository = SQLitePersonRepository(provider)
    service = _make_service(provider, repository=repository)
    rows = [
        _row("Alice", row_number=1),
        _row("   ", row_number=7),  # Person rejects blank names (ValidationError)
        _row("Bob", row_number=3),
    ]

    result = service.import_rows(rows)

    assert result.imported_count == 2
    assert len(result.errors) == 1
    assert "row 7" in result.errors[0]
    persisted = {person.name for person in repository.list_all()}
    assert persisted == {"Alice", "Bob"}


def test_identity_dedupe_across_separate_imports(provider: SQLiteConnectionProvider) -> None:
    """A row whose identity already exists is skipped, mirroring the old path."""
    repository = SQLitePersonRepository(provider)
    service = _make_service(provider, repository=repository)

    first = service.import_rows([_row("Alice", identity="A001")])
    second = service.import_rows([_row("Alice clone", identity="A001")])

    assert first.imported_count == 1
    assert second.imported_count == 0
    assert second.skipped_count == 1
    assert len(repository.list_all()) == 1


def test_identity_less_rows_dedupe_by_name_and_department(
    provider: SQLiteConnectionProvider,
) -> None:
    """Identity-less rows dedupe on normalized name+department (D-B2).

    Normalization mirrors ``Person.__post_init__``: names are stripped and
    blank departments collapse to ``None``. Distinct departments (including a
    stored NULL vs a concrete value) are different people — the SQLite lookup
    uses the NULL-safe ``department IS ?`` predicate.
    """
    repository = SQLitePersonRepository(provider)
    service = _make_service(provider, repository=repository)

    first = service.import_rows([_row("Carol", department=" Archive ")])
    duplicate = service.import_rows([_row("Carol ", department="Archive")])
    other_department = service.import_rows([_row("Carol", department="Other")])
    null_department = service.import_rows([_row("Carol")])

    assert first.imported_count == 1
    assert duplicate.imported_count == 0 and duplicate.skipped_count == 1
    assert other_department.imported_count == 1
    assert null_department.imported_count == 1

    persisted = {
        (person.name, person.department) for person in repository.list_all()
    }
    assert persisted == {("Carol", "Archive"), ("Carol", "Other"), ("Carol", None)}


def test_duplicates_inside_one_batch_are_seen_within_the_same_scope(
    provider: SQLiteConnectionProvider,
) -> None:
    """Dedupe also fires within a single batch (same UoW connection scope)."""
    repository = SQLitePersonRepository(provider)
    service = _make_service(provider, repository=repository, batch_size=10)
    rows = [
        _row("Dave", identity="D1", row_number=1),
        _row("Dave", identity="D1", row_number=2),
        _row("Eve", department="X", row_number=3),
        _row("Eve", department="X", row_number=4),
    ]

    result = service.import_rows(rows)

    assert result.imported_count == 2
    assert result.skipped_count == 2
    assert len(repository.list_all()) == 2


def test_service_without_uow_persists_bare_rows(provider: SQLiteConnectionProvider) -> None:
    """The optional-UoW convention: ``None`` keeps the bare per-row path."""
    repository = SQLitePersonRepository(provider)
    service = _make_service(provider, repository=repository, with_uow=False)

    result = service.import_rows([_row("Frank"), _row("Grace")])

    assert result.imported_count == 2
    assert len(repository.list_all()) == 2

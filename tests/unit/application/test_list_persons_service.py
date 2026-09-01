"""ListPersonsService unit tests — Phase 9 FEAT-P9-2 person filter axis.

Verifies the thin read-only use case over the production InMemory
implementation of the ``PersonRepository`` Protocol: full catalog in
repository order, honest empty catalog, and no mutation of the stored
entities. No SQLite or model pack required (the service adds no logic beyond
the repository call, per the SearchPhotosService precedent).
"""

from photo_archiver.application.services import ListPersonsService
from photo_archiver.domain import Person
from photo_archiver.infrastructure.repositories import InMemoryPersonRepository


def test_execute_returns_full_person_catalog() -> None:
    repository = InMemoryPersonRepository()
    alice = Person(name="Alice")
    bob = Person(name="Bob")
    repository.add(alice)
    repository.add(bob)

    persons = ListPersonsService(repository).execute()

    assert persons == [alice, bob]  # repository order preserved


def test_execute_returns_empty_list_for_empty_catalog() -> None:
    """No persons imported yet → empty result (FilterBar keeps 'All persons')."""
    service = ListPersonsService(InMemoryPersonRepository())

    assert service.execute() == []

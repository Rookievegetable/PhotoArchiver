"""People-administration service — stage B of the people-import redesign.

The roster is an ordered, editable list: this service adds, edits and
re-sequences people. Design notes:

- validation is the ``Person`` entity's (name required, text normalized); the
  service only adds the registry-level rules (identity uniqueness);
- editing reuses the ``add`` upsert instead of introducing a second write path
  (the repository contract already replaces the aggregate with the same id);
- a newly added person is appended to the end of the roster via
  ``max_roster_order() + 1`` (stage A ruling: the sequence is globally
  monotonic);
- ``reorder`` writes the whole roster's positions in one unit of work, because
  the page's drag action defines the complete order;
- batch review reads ``ImportBatchRepository.list_batches()`` and counts the
  people still pointing at each batch, so a person always shows its origin.

Wording: the ``Person`` entity keeps language-neutral messages, while the
messages this service raises are the ones the UI shows verbatim — so the roster
rules (including the entity's name rule) are surfaced in Chinese here.
"""

from uuid import UUID

from loguru import logger

from photo_archiver.application.commands.people_admin import (
    AddPersonCommand,
    EditPersonCommand,
    ReorderPeopleCommand,
)
from photo_archiver.application.dtos.people_admin import ImportBatchSummary, PeopleRoster
from photo_archiver.application.ports import UnitOfWork
from photo_archiver.domain.entities import Person
from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.domain.repositories import ImportBatchRepository, PersonRepository
from photo_archiver.domain.value_objects import PersonIdentity


_ENTITY_MESSAGES = {
    "Person name must not be empty": "姓名不能为空",
}
"""Chinese wording for the entity rules a user can hit (stage-B review fix #1)."""


class ManagePeopleService:
    """Add, edit and re-sequence the person roster (stage B)."""

    def __init__(
        self,
        people: PersonRepository,
        import_batches: ImportBatchRepository,
        unit_of_work: UnitOfWork | None = None,
    ) -> None:
        """Initialize the service with its ports.

        Args:
            people: Registry source of truth (upsert, lookup, roster order).
            import_batches: Batch catalog for the batch-review column.
            unit_of_work: Optional transactional scope; ``None`` persists bare.
        """
        self._people = people
        self._import_batches = import_batches
        self._unit_of_work = unit_of_work

    def add_person(self, command: AddPersonCommand) -> Person:
        """Create one person and append them to the end of the roster.

        Raises:
            ValidationError: The person fields are invalid or the identity is
                already registered.
        """
        identity = self._identity_or_none(command.identity)
        self._ensure_identity_available(identity)
        try:
            person = Person(
                name=command.name,
                identity=identity,
                department=command.department,
                note=command.note,
                roster_order=(self._people.max_roster_order() or 0) + 1,
            )
        except ValidationError as exc:
            raise self._localized_validation(exc) from exc
        self._people.add(person)
        logger.info("AUDIT add-person actor=local-user person_id={} name={}", person.id, person.name)
        return person

    def edit_person(self, command: EditPersonCommand) -> Person:
        """Replace one existing person's editable fields.

        Raises:
            ValidationError: The person does not exist, the fields are invalid
                or the identity is taken by someone else.
        """
        person = self._people.find_by_id(command.person_id)
        if person is None:
            raise ValidationError(f"人员不存在：{command.person_id}")
        identity = self._identity_or_none(command.identity)
        self._ensure_identity_available(identity, owner_id=command.person_id)
        person.name = command.name
        person.identity = identity
        person.department = command.department
        person.note = command.note
        try:
            person.__post_init__()  # re-run entity normalization + validation in place
        except ValidationError as exc:
            raise self._localized_validation(exc) from exc
        self._people.add(person)
        logger.info("AUDIT edit-person actor=local-user person_id={} name={}", person.id, person.name)
        return person

    def reorder_people(self, command: ReorderPeopleCommand) -> int:
        """Write the full roster order (position N = place N) in one transaction.

        Raises:
            ValidationError: One or more ids are not registered, or the same id
                appears twice (an ambiguous order is never persisted).
        """
        ordered_ids = command.ordered_ids
        if len(set(ordered_ids)) != len(ordered_ids):
            raise ValidationError("重排序列表包含重复的人员")
        missing = [pid for pid in ordered_ids if self._people.find_by_id(pid) is None]
        if missing:
            raise ValidationError(f"重排序目标不存在：{missing}")
        orders = [(person_id, position) for position, person_id in enumerate(ordered_ids, 1)]
        if self._unit_of_work is not None:
            with self._unit_of_work:
                updated = self._people.reorder(orders)
        else:
            updated = self._people.reorder(orders)
        logger.info(
            "AUDIT reorder-people actor=local-user requested={} updated={}", len(orders), updated,
        )
        return updated

    def roster(self) -> PeopleRoster:
        """Return the ordered roster plus the per-batch person counts."""
        people = tuple(self._people.list_all())
        counts: dict[UUID, int] = {}
        for person in people:
            if person.source_batch_id is not None:
                counts[person.source_batch_id] = counts.get(person.source_batch_id, 0) + 1
        batches = tuple(
            ImportBatchSummary(batch=batch, person_count=counts.get(batch.id, 0))
            for batch in self._import_batches.list_batches()
            if batch.id is not None
        )
        return PeopleRoster(people=people, batches=batches)

    @staticmethod
    def _localized_validation(exc: ValidationError) -> ValidationError:
        """Return the user-facing (Chinese) form of an entity validation error.

        The entity stays language-neutral; the Application layer owns the
        wording the Presentation shows verbatim, so a rule the user can hit
        (an empty name) is translated here. Unknown messages pass through
        unchanged — a new entity rule is never silently reworded.
        """
        return ValidationError(_ENTITY_MESSAGES.get(str(exc), str(exc)))

    @staticmethod
    def _identity_or_none(raw_identity: str | None) -> PersonIdentity | None:
        """Normalize the optional identity cell into a value object."""
        text = (raw_identity or "").strip()
        return PersonIdentity(text) if text else None

    def _ensure_identity_available(
        self, identity: PersonIdentity | None, owner_id: UUID | None = None,
    ) -> None:
        """Refuse an identity already registered to a different person."""
        if identity is None:
            return
        existing = self._people.find_by_identity(identity)
        if existing is not None and existing.id != owner_id:
            raise ValidationError(f"工号已被其他人员占用：{identity.value}")

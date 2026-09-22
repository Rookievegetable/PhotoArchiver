"""People-administration DTOs (people-import redesign stage B)."""

from dataclasses import dataclass

from photo_archiver.domain.entities import ImportBatch, Person


@dataclass(frozen=True, slots=True)
class ImportBatchSummary:
    """One import batch plus how many of its people are still registered.

    Stage B batch review: the people page lets the user inspect which import a
    person came from, so batches are listed with their confirmed person count.
    """

    batch: ImportBatch
    person_count: int


@dataclass(frozen=True, slots=True)
class PeopleRoster:
    """The roster as the people page renders it: ordered people and batches."""

    people: tuple[Person, ...]
    batches: tuple[ImportBatchSummary, ...]

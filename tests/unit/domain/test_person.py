"""Tests for person domain entity."""

import pytest

from photo_archiver.domain import Person, PersonIdentity, ValidationError


def test_person_requires_non_empty_name() -> None:
    """Person name is mandatory."""
    with pytest.raises(ValidationError):
        Person(name="   ")


def test_person_normalizes_optional_fields() -> None:
    """Person trims required and optional fields."""
    person = Person(
        name="  Alice  ",
        identity=PersonIdentity("  A001  "),
        department="  Archives  ",
        note="  Lead  ",
    )

    assert person.id is not None
    assert person.name == "Alice"
    assert person.identity == PersonIdentity("A001")
    assert person.department == "Archives"
    assert person.note == "Lead"


def test_person_identity_rejects_empty_value() -> None:
    """Person identity is optional but cannot be blank when provided."""
    with pytest.raises(ValidationError):
        PersonIdentity(" ")
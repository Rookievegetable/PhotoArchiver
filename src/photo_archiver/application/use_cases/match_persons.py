"""Use case boundary for the face matching workflow."""

from photo_archiver.application.dtos import MatchResult


class MatchPersonsUseCase:
    """Define the face matching use case contract.

    Implementations orchestrate detection → recognition → matching against
    known person embeddings, returning one :class:`MatchResult` per photo.
    The use case MUST NOT mutate widgets or load AI models directly — it
    coordinates ports injected by the caller.
    """

    def execute(self, command) -> tuple[MatchResult, ...]:  # type: ignore[empty-body]
        """Run matching for the command's photos and return one result per photo."""
        raise NotImplementedError

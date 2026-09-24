"""Face count range value object — 人脸数范围（阶段 C 范围选择的最小单元）.

阶段 C（多脸检测、识别范围选择与可重跑）：范围 UI 的多选预设
（[1] [2-3] [4-5] [6-10] [11+]）只是本值对象的快捷生成器——
不建立固定 RecognitionMode，任意范围组合都由本类型表达。
"""

from dataclasses import dataclass

from photo_archiver.domain.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class FaceCountRange:
    """Represent an inclusive face-count range; ``max_count=None`` means unbounded.

    Invariants: ``min_count >= 1`` and, when set, ``max_count >= min_count``.
    Text forms round-trip through ``parse``/``str``: ``"1"`` (single value),
    ``"2-3"`` (bounded), ``"11+"`` (unbounded).
    """

    min_count: int
    max_count: int | None = None

    def __post_init__(self) -> None:
        """Validate range bounds."""
        if self.min_count < 1:
            raise ValidationError("FaceCountRange min_count must be >= 1")
        if self.max_count is not None and self.max_count < self.min_count:
            raise ValidationError("FaceCountRange max_count must be >= min_count")

    def contains(self, face_count: int) -> bool:
        """Return True when ``face_count`` falls inside the inclusive range."""
        if face_count < self.min_count:
            return False
        return self.max_count is None or face_count <= self.max_count

    @classmethod
    def parse(cls, text: str) -> "FaceCountRange":
        """Parse ``"1"`` / ``"2-3"`` / ``"11+"`` into a FaceCountRange.

        Raises:
            ValidationError: When the text is not a valid range form, or the
                parsed bounds violate the range invariants.
        """
        normalized = text.strip()
        if normalized.endswith("+"):
            return cls(min_count=cls._parse_int(normalized[:-1], text), max_count=None)
        if "-" in normalized:
            low, _, high = normalized.partition("-")
            return cls(
                min_count=cls._parse_int(low, text),
                max_count=cls._parse_int(high, text),
            )
        value = cls._parse_int(normalized, text)
        return cls(min_count=value, max_count=value)

    def __str__(self) -> str:
        """Return the canonical text form (``"1"`` / ``"2-3"`` / ``"11+"``)."""
        if self.max_count is None:
            return f"{self.min_count}+"
        if self.max_count == self.min_count:
            return str(self.min_count)
        return f"{self.min_count}-{self.max_count}"

    @staticmethod
    def _parse_int(fragment: str, source: str) -> int:
        """Parse one integer fragment, reporting the full source on failure."""
        try:
            return int(fragment)
        except ValueError:
            raise ValidationError(f"Invalid FaceCountRange text: {source!r}") from None

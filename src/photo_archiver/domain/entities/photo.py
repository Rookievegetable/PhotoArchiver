"""Photo entity."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.domain.value_objects import PhotoMetadata, PhotoPath


@dataclass(slots=True)
class Photo:
    """Represent a photo discovered by the archive workflow.

    ``captured_at`` 持拍摄时刻（EXIF DateTimeOriginal 优先），落 Phase 2
    Step 11 裁决 #2：Archive 阶段只消费此领域字段拼 ``{event_or_date}`` 段，
    不直接解析 EXIF。本字段由导入阶段（PillowPhotoMetadataReader →
    PhotoMetadata.captured_at → RegisterPhotoService）统一填充。

    与 ``created_at`` 的区别：``created_at`` 持注册时刻（缺省填
    ``datetime.now()``），用于持久化排序；``captured_at`` 持照片本身
    的拍摄时刻，缺省时为 ``None``——不自动填 ``now()`` 以免欺骗归档目录。
    """

    path: PhotoPath
    id: UUID | None = None
    folder_id: UUID | None = None
    metadata: PhotoMetadata | None = None
    original_name: str | None = None
    created_at: datetime | None = None
    captured_at: datetime | None = None

    def __post_init__(self) -> None:
        """Initialize generated fields and normalize optional text."""
        if not isinstance(self.path, PhotoPath):
            raise ValidationError("Photo path must be a PhotoPath")
        if self.id is None:
            self.id = uuid4()
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.original_name is not None:
            normalized_name = self.original_name.strip()
            self.original_name = normalized_name or None
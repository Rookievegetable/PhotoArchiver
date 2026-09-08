"""Person repository interface."""

from typing import Protocol
from uuid import UUID

from photo_archiver.domain.entities import Person
from photo_archiver.domain.value_objects import PersonIdentity


class PersonRepository(Protocol):
    """Define persistence operations for person entities."""

    def add(self, person: Person) -> None:
        """Add a person entity or replace the existing aggregate with the same id."""

    def find_by_id(self, person_id: UUID) -> Person | None:
        """Find a person by its domain identifier."""

    def find_by_identity(self, identity: PersonIdentity) -> Person | None:
        """Find a person by its external identity."""

    def find_by_name_department(self, name: str, department: str | None) -> Person | None:
        """Find a person by exact normalized name and department (P0-7, D-B2).

        Args:
            name: Already-stripped person name.
            department: Already-normalized department (empty string normalized
                to ``None``, mirroring ``Person.__post_init__``).
        """

    def list_all(self) -> list[Person]:
        """Return all known people."""

    def remove(self, person_id: UUID) -> int:
        """Remove the person from the registry; return 1 when removed, else 0.

        ADR-034（D2）：删除仅作用于库内登记——人脸嵌入随人员级联删除、
        其识别结果归属置空为"未知人员"（SQLite 外键既有语义）、**照片全部
        保留**；磁盘文件一律不动（D3）。幂等：目标不存在返 0，不抛错。
        """
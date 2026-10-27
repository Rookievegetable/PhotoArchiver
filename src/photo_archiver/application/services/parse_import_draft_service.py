"""Parse roster files into editable import draft batches (stage A).

Owner plan §4.1: nothing here silently writes people — the service builds a
persisted draft (raw values, parsed fields, structured warnings, per-row
actions) that the preview dialog edits before
:class:`~photo_archiver.application.services.confirm_import_service.ConfirmImportService`
atomically writes the registry. Multi-name cells and group titles produce
advisories, never silent splits or silent skips.
"""

import hashlib
import re
from pathlib import Path

from photo_archiver.application.commands.import_draft import (
    ParseImportDraftCommand,
    ReparseImportDraftCommand,
)
from photo_archiver.application.dtos.import_draft import ImportDraft, RawRosterTable
from photo_archiver.application.ports.roster_table_reader import RosterTableReader
from photo_archiver.domain.entities import (
    ImportBatch,
    ImportDraftRow,
    BATCH_STATUS_DRAFT,
    DRAFT_ACTION_CREATE,
    DRAFT_ACTION_MERGE_EXISTING,
    DRAFT_ACTION_SKIP,
)
from photo_archiver.domain.repositories import ImportBatchRepository, PersonRepository

# 疑似组标题："2组" / "第 2 组" / "名单" / "名单表"
_GROUP_TITLE_RE = re.compile(r"^\s*(第?\s*\d+\s*组|名单表?)\s*$")
# 疑似多人分隔符：顿号、中英文逗号、分号、换行、连续空格
_MULTI_NAME_RE = re.compile(r"[、，,；;\n]|\s{2,}")
_SPLIT_RE = re.compile(r"[、，,；;\n]+|\s{2,}")

# 字段映射：表头关键词（大小写不敏感的包含匹配）
_FIELD_KEYWORDS = {
    "name": ("姓名", "名字", "name"),
    "identity": ("工号", "编号", "学号", "身份证", "identity"),
    "department": ("部门", "单位", "院系", "department"),
    "note": ("备注", "说明", "note"),
    "group": ("组别", "组名", "分组", "group"),
}
_DEFAULT_POSITIONAL_MAPPING = {"name": 0, "identity": 1, "department": 2, "note": 3, "group": 4}
_FIELDS = ("name", "identity", "department", "note", "group")


class ParseImportDraftService:
    """Parse one roster file into a persisted, editable draft batch."""

    def __init__(
        self,
        reader: RosterTableReader,
        import_batches: ImportBatchRepository,
        people: PersonRepository,
    ) -> None:
        """Initialize with the reader port and the draft/people repositories."""
        self._reader = reader
        self._import_batches = import_batches
        self._people = people

    def execute(self, command: ParseImportDraftCommand) -> ImportDraft:
        """Parse the file, persist a fresh draft batch, and return it."""
        source_path = Path(command.source_path)
        file_hash = self._hash_file(source_path)
        table = self._reader.read_raw(
            source_path, has_header=command.has_header, sheet_name=command.sheet_name,
        )
        mapping = self._detect_field_mapping(table)
        batch = ImportBatch(
            file_name=source_path.name,
            file_hash=file_hash,
            source_type=table.source_type,
            encoding=table.encoding,
            delimiter=table.delimiter,
            has_header=command.has_header,
            sheet_name=command.sheet_name,
            status=BATCH_STATUS_DRAFT,
        )
        rows = self._build_rows(batch, table, mapping)
        self._import_batches.add_batch(batch)
        self._import_batches.replace_draft_rows(batch.id, rows)  # type: ignore[arg-type]
        return self._assemble(batch, rows, table.header, mapping)

    def list_sheets(self, source_path: Path) -> tuple[str, ...]:
        """List worksheet names when the reader supports it (preview combo)."""
        list_sheets = getattr(self._reader, "list_sheets", None)
        if list_sheets is None:
            return ()
        try:
            return tuple(list_sheets(Path(source_path)))
        except Exception:  # noqa: BLE001  预览能力探测失败不阻断导入
            return ()

    def reparse(self, command: ReparseImportDraftCommand) -> ImportDraft:
        """Re-run the parse after the user changed header/sheet/mapping options."""
        batch = self._import_batches.get_batch(command.batch_id)
        if batch is None:
            raise ValueError(f"import batch not found: {command.batch_id}")
        table = self._reader.read_raw(
            Path(command.source_path),
            has_header=command.has_header,
            sheet_name=command.sheet_name,
        )
        rows = self._build_rows(batch, table, command.field_mapping)
        self._import_batches.replace_draft_rows(command.batch_id, rows)
        return self._assemble(batch, rows, table.header, command.field_mapping)

    def split_draft_row(self, batch_id, row_id) -> ImportDraft:  # noqa: ANN001
        """Split one multi-name draft row into one row per name (user action).

        The other parsed fields are copied to every split row; the multi-name
        advisory is cleared on the resulting rows. Order is resequenced so the
        split rows keep the original position.

        无可拆内容（用户已把姓名改成单名）时返回原草稿、零改动——调用方需
        用 :meth:`split_draft_row_with_status` 区分 no-op（P9：不得静默）。
        """
        return self.split_draft_row_with_status(batch_id, row_id)[0]

    def split_draft_row_with_status(self, batch_id, row_id) -> tuple[ImportDraft, bool]:  # noqa: ANN001
        """Split one row; return ``(draft, changed)``——``changed=False`` 即 no-op。

        P9（界面优化）：拆分点击后若无任何可拆内容，界面必须给出可见反馈；
        本方法的布尔结果就是该反馈的判定依据。
        """
        rows = self._import_batches.list_draft_rows(batch_id)
        target = next((row for row in rows if row.id == row_id), None)
        if target is None:
            raise ValueError(f"draft row not found: {row_id}")
        segments = [segment.strip() for segment in _SPLIT_RE.split(target.parsed_name) if segment.strip()]
        if len(segments) <= 1:
            return self._assemble_current(batch_id, rows), False
        rebuilt: list[ImportDraftRow] = []
        for row in rows:
            if row.id != row_id:
                rebuilt.append(row)
                continue
            for segment in segments:
                rebuilt.append(ImportDraftRow(
                    batch_id=row.batch_id,
                    source_row=row.source_row,
                    raw_values=row.raw_values,
                    parsed_name=segment,
                    parsed_identity=row.parsed_identity if len(segments) == 1 else None,
                    parsed_department=row.parsed_department,
                    parsed_note=row.parsed_note,
                    parsed_group=row.parsed_group,
                    warnings=tuple(w for w in row.warnings if w[0] != "multi_name"),
                    action=DRAFT_ACTION_CREATE,
                    order_index=row.order_index,
                ))
        rebuilt.sort(key=lambda r: r.order_index)
        for index, row in enumerate(rebuilt):
            row.order_index = index
        self._import_batches.replace_draft_rows(batch_id, rebuilt)
        return self._assemble_current(batch_id, rebuilt), True

    def save_draft_rows(self, batch_id, rows: list[ImportDraftRow]) -> ImportDraft:  # noqa: ANN001
        """Persist preview edits (field changes, action switches, reorders)."""
        for index, row in enumerate(sorted(rows, key=lambda r: r.order_index)):
            row.order_index = index
        self._import_batches.replace_draft_rows(batch_id, rows)
        return self._assemble_current(batch_id, rows)

    # ── internals ────────────────────────────────────────────────────────

    def _assemble_current(self, batch_id, rows: list[ImportDraftRow]) -> ImportDraft:  # noqa: ANN001
        """Rebuild the ImportDraft view from persisted rows."""
        batch = self._import_batches.get_batch(batch_id)
        if batch is None:
            raise ValueError(f"import batch not found: {batch_id}")
        mapping = self._positional_mapping()
        multi = tuple(
            row.id for row in rows
            if row.id is not None and any(w[0] == "multi_name" for w in row.warnings)
        )
        return ImportDraft(batch=batch, rows=rows, header=None,
                           field_mapping=mapping, multi_name_row_ids=multi)

    def _assemble(
        self,
        batch: ImportBatch,
        rows: list[ImportDraftRow],
        header: list[str] | None,
        mapping: dict[str, int],
    ) -> ImportDraft:
        """Build the ImportDraft view from freshly parsed rows."""
        multi = tuple(
            row.id for row in rows
            if row.id is not None and any(w[0] == "multi_name" for w in row.warnings)
        )
        return ImportDraft(batch=batch, rows=rows, header=header,
                           field_mapping=mapping, multi_name_row_ids=multi)

    def _build_rows(
        self,
        batch: ImportBatch,
        table: RawRosterTable,
        mapping: dict[str, int],
    ) -> list[ImportDraftRow]:
        """Convert raw rows into warned, action-tagged draft rows."""
        rows: list[ImportDraftRow] = []
        seen_identities: dict[str, int] = {}
        seen_name_departments: dict[tuple[str, str | None], int] = {}
        for order_index, cells in enumerate(table.rows):
            values = [cell.strip() for cell in cells]
            name = self._cell(values, mapping, "name")
            identity = self._cell(values, mapping, "identity") or None
            department = self._cell(values, mapping, "department") or None
            note = self._cell(values, mapping, "note") or None
            group = self._cell(values, mapping, "group") or None
            warnings: list[tuple[str, str]] = []
            action = DRAFT_ACTION_CREATE

            if not name:
                warnings.append(("empty_name", ""))
                action = DRAFT_ACTION_SKIP
            else:
                segments = [s for s in _SPLIT_RE.split(name) if s.strip()]
                if len(segments) > 1:
                    warnings.append(("multi_name", str(len(segments))))
                if _GROUP_TITLE_RE.match(name):
                    warnings.append(("group_title", name))
                    action = DRAFT_ACTION_SKIP

            if identity:
                if identity in seen_identities:
                    warnings.append(("identity_duplicate_in_file", identity))
                    action = DRAFT_ACTION_SKIP
                seen_identities.setdefault(identity, order_index)
                existing = self._people.find_by_identity(self._identity_value(identity))
                if existing is not None:
                    warnings.append(("identity_duplicate_db", identity))
                    # Owner ruling (LIMIT-008 / acceptance F-A2): a duplicate
                    # inside the same file keeps priority — both warnings are
                    # listed, but the row is skipped, not merged.
                    if action != DRAFT_ACTION_SKIP:
                        action = DRAFT_ACTION_MERGE_EXISTING
            key = (name, department)
            if name and key in seen_name_departments:
                warnings.append(("name_department_duplicate_in_file", name))
            seen_name_departments.setdefault(key, order_index)
            if name and department is not None:
                existing_pair = self._people.find_by_name_department(name, department)
                if existing_pair is not None and action == DRAFT_ACTION_CREATE:
                    warnings.append(("name_department_duplicate_db", name))
                    action = DRAFT_ACTION_MERGE_EXISTING

            rows.append(ImportDraftRow(
                batch_id=batch.id,  # type: ignore[arg-type]  # set in __post_init__
                source_row=order_index + 1,
                raw_values=values,
                parsed_name=name,
                parsed_identity=identity,
                parsed_department=department,
                parsed_note=note,
                parsed_group=group,
                warnings=tuple(warnings),
                action=action,
                order_index=order_index,
            ))
        return rows

    @staticmethod
    def _cell(values: list[str], mapping: dict[str, int], field_name: str) -> str:
        """Read one mapped cell; out-of-range columns read as empty."""
        index = mapping.get(field_name)
        if index is None or index >= len(values):
            return ""
        return values[index]

    def _detect_field_mapping(self, table: RawRosterTable) -> dict[str, int]:
        """Guess the field→column mapping from header keywords, else positional."""
        if table.header is None:
            return self._positional_mapping()
        mapping: dict[str, int] = {}
        lowered = [str(title).strip().lower() for title in table.header]
        for field_name in _FIELDS:
            for index, title in enumerate(lowered):
                if any(keyword in title for keyword in _FIELD_KEYWORDS[field_name]):
                    mapping[field_name] = index
                    break
        mapping.setdefault("name", 0)
        return mapping

    @staticmethod
    def _positional_mapping() -> dict[str, int]:
        """Headerless files default to the documented positional contract."""
        return dict(_DEFAULT_POSITIONAL_MAPPING)

    @staticmethod
    def _identity_value(identity: str):
        from photo_archiver.domain import PersonIdentity

        return PersonIdentity(identity)

    def _hash_file(self, source_path: Path) -> str:
        """SHA-256 of the source file for batch traceability（AUD-010：字节经 reader 端口）."""
        digest = hashlib.sha256()
        digest.update(self._reader.read_bytes(source_path))
        return digest.hexdigest()

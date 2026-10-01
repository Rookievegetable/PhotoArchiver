"""Searchable name combo helper (2026-10-01 审核中心身份选择).

Shares the FilterBar person-axis pattern (editable combo + smart-ranked
completion via :func:`person_name_ranker.rank_person_names`) with the
review center's identity selectors: typing re-ranks the completion list
(全等 → 前缀 → 连续包含 → 子序列), picking a completion locates the
matching combo item. Items are read back from the combo itself
(``itemText``) — no duplicate state; duplicate names resolve to the first
matching item (same documented limitation as FilterBar).
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QStringListModel
from PySide6.QtWidgets import QComboBox, QCompleter

from photo_archiver.presentation.person_name_ranker import rank_person_names


class NameSearchComboBinder(QObject):
    """Attach smart-search completion to a combo whose items carry names.

    The combo becomes editable with ``NoInsert`` policy (typed text never
    creates entries); the completion list is rebuilt from the combo's own
    item texts on every edit, ranked by the shared name ranker.
    """

    def __init__(self, combo: QComboBox, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._combo = combo
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._completer = QCompleter(combo)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setCompletionMode(
            QCompleter.CompletionMode.UnfilteredPopupCompletion
        )
        self._completer_model = QStringListModel(self._completer)
        self._completer.setModel(self._completer_model)
        combo.setCompleter(self._completer)
        self._completer.activated.connect(self._on_completion_activated)
        combo.editTextChanged.connect(self._on_search_text_changed)

    def _on_search_text_changed(self, text: str) -> None:
        """Rebuild the completion list, smart-ranked for the typed text."""
        names = [self._combo.itemText(i) for i in range(self._combo.count())]
        self._completer_model.setStringList(rank_person_names(text, names))

    def _on_completion_activated(self, name: str) -> None:
        """Map a picked completion back to the first combo item with that name."""
        index = next(
            (i for i in range(self._combo.count())
             if self._combo.itemText(i) == name),
            -1,
        )
        if index >= 0:
            self._combo.setCurrentIndex(index)

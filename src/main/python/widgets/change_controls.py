# SPDX-License-Identifier: GPL-2.0-or-later
"""Inline controls for Push/Undo/Redo/Revert, displayed next to keyboard selector."""
import sys
from qtpy.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QCheckBox
from qtpy.QtGui import QKeySequence
from qtpy.QtCore import Qt

from change_manager import ChangeManager


class ChangeControls(QWidget):
    """Inline widget with Push, Undo, Redo, Revert buttons and pending changes counter."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.cm = ChangeManager.instance()
        is_web = sys.platform == "emscripten"
        mod = "⌘" if sys.platform == "darwin" else "^"

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Undo button - no shortcut on web (browser captures Ctrl+Z)
        self.btn_undo = QPushButton("Undo" if is_web else f"Undo {mod}Z")
        if not is_web:
            self.btn_undo.setShortcut(QKeySequence.Undo)
        self.btn_undo.clicked.connect(self._on_undo)
        self.btn_undo.setEnabled(False)
        layout.addWidget(self.btn_undo)

        # Redo button - no shortcut on web
        self.btn_redo = QPushButton("Redo" if is_web else f"Redo {mod}⇧Z")
        if not is_web:
            self.btn_redo.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        self.btn_redo.clicked.connect(self._on_redo)
        self.btn_redo.setEnabled(False)
        layout.addWidget(self.btn_redo)

        layout.addStretch()

        # Revert button - discard all pending changes
        self.btn_revert = QPushButton("Revert")
        self.btn_revert.setToolTip("Discard all pending changes")
        self.btn_revert.clicked.connect(self._on_revert)
        self.btn_revert.setEnabled(False)
        layout.addWidget(self.btn_revert)

        # Push button - no shortcut on web (browser captures Ctrl+S)
        self.btn_push = QPushButton("Push" if is_web else f"Push {mod}S")
        if not is_web:
            self.btn_push.setShortcut(QKeySequence.Save)
        self.btn_push.clicked.connect(self._on_push)
        self.btn_push.setEnabled(False)
        layout.addWidget(self.btn_push)

        # Instant push checkbox
        self.auto_checkbox = QCheckBox("Instant Change Pushes")
        self.auto_checkbox.setToolTip("When checked, every change is immediately sent to device")
        self.auto_checkbox.stateChanged.connect(self._on_auto_changed)
        layout.addWidget(self.auto_checkbox)

        self.setLayout(layout)

        # Connect to ChangeManager signals
        self.cm.can_save_changed.connect(self._update_push_state)
        self.cm.can_undo_changed.connect(self._update_undo_state)
        self.cm.can_redo_changed.connect(self._update_redo_state)
        self.cm.auto_commit_changed.connect(self._update_auto_state)

    def _on_push(self):
        """Handle Push action."""
        self.cm.save()

    def _on_undo(self):
        """Handle Undo action."""
        self.cm.undo()

    def _on_redo(self):
        """Handle Redo action."""
        self.cm.redo()

    def _on_revert(self):
        """Handle Revert action - discard all pending changes."""
        self.cm.revert_all()

    def _update_push_state(self, can_push):
        """Update Push button enabled state and highlight."""
        self.btn_push.setEnabled(can_push)
        self.btn_revert.setEnabled(can_push)
        highlight = "QPushButton { color: palette(link); }" if can_push else ""
        self.btn_push.setStyleSheet(highlight)
        self.btn_revert.setStyleSheet(highlight)

    def _update_undo_state(self, can_undo):
        """Update Undo button enabled state, tooltip, and highlight."""
        self.btn_undo.setEnabled(can_undo)
        size = self.cm.undo_stack_size()
        max_size = self.cm.max_undo_stack_size()
        self.btn_undo.setToolTip(f"{size}/{max_size} in history")
        highlight = "QPushButton { color: palette(link); }" if can_undo else ""
        self.btn_undo.setStyleSheet(highlight)

    def _update_redo_state(self, can_redo):
        """Update Redo button enabled state and highlight."""
        self.btn_redo.setEnabled(can_redo)
        highlight = "QPushButton { color: palette(link); }" if can_redo else ""
        self.btn_redo.setStyleSheet(highlight)

    def _on_auto_changed(self, state):
        """Handle Auto checkbox toggle."""
        self.cm.auto_commit = (state == Qt.Checked)

    def _update_auto_state(self, auto_commit):
        """Update UI when auto_commit changes."""
        # Update checkbox without triggering signal
        self.auto_checkbox.blockSignals(True)
        self.auto_checkbox.setChecked(auto_commit)
        self.auto_checkbox.blockSignals(False)

        # Hide push/revert buttons when auto-push is on
        self.btn_push.setVisible(not auto_commit)
        self.btn_revert.setVisible(not auto_commit)

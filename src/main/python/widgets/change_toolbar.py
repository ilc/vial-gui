# SPDX-License-Identifier: GPL-2.0-or-later
"""Toolbar for Save/Undo/Redo operations."""
import sys
from qtpy.QtWidgets import QToolBar, QLabel, QWidget, QSizePolicy
from qtpy.QtGui import QKeySequence, QAction
from qtpy.QtCore import Qt

from change_manager import ChangeManager


class ChangeToolbar(QToolBar):
    """Toolbar with Save, Undo, Redo buttons and pending changes counter."""

    def __init__(self, parent=None):
        super().__init__("Changes", parent)
        self.setMovable(False)
        self.setFloatable(False)

        self.cm = ChangeManager.instance()
        mod = "Cmd" if sys.platform == "darwin" else "Ctrl"

        # Save action
        self.save_action = QAction("Save", self)
        self.save_action.setShortcut(QKeySequence.Save)
        self.save_action.setToolTip(f"Save all pending changes to device ({mod}+S)")
        self.save_action.triggered.connect(self._on_save)
        self.save_action.setEnabled(False)
        self.addAction(self.save_action)

        # Undo action
        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.undo_action.setToolTip(f"Undo last change ({mod}+Z)")
        self.undo_action.triggered.connect(self._on_undo)
        self.undo_action.setEnabled(False)
        self.addAction(self.undo_action)

        # Redo action
        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        self.redo_action.setToolTip(f"Redo last undone change ({mod}+Shift+Z)")
        self.redo_action.triggered.connect(self._on_redo)
        self.redo_action.setEnabled(False)
        self.addAction(self.redo_action)

        self.addSeparator()

        # Spacer to push label to the right of its section
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.addWidget(spacer)

        # Pending changes label
        self.pending_label = QLabel("")
        self.addWidget(self.pending_label)

        # Connect to ChangeManager signals
        self.cm.can_save_changed.connect(self._update_save_state)
        self.cm.can_undo_changed.connect(self._update_undo_state)
        self.cm.can_redo_changed.connect(self._update_redo_state)
        self.cm.changed.connect(self._update_pending_label)

    def _on_save(self):
        """Handle Save action."""
        self.cm.save()

    def _on_undo(self):
        """Handle Undo action."""
        self.cm.undo()

    def _on_redo(self):
        """Handle Redo action."""
        self.cm.redo()

    def _update_save_state(self, can_save):
        """Update Save button enabled state."""
        self.save_action.setEnabled(can_save)

    def _update_undo_state(self, can_undo):
        """Update Undo button enabled state."""
        self.undo_action.setEnabled(can_undo)

    def _update_redo_state(self, can_redo):
        """Update Redo button enabled state."""
        self.redo_action.setEnabled(can_redo)

    def _update_pending_label(self):
        """Update the pending changes counter label."""
        count = self.cm.pending_count()
        if count == 0:
            self.pending_label.setText("")
        elif count == 1:
            self.pending_label.setText("1 pending change")
        else:
            self.pending_label.setText(f"{count} pending changes")

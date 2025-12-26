# SPDX-License-Identifier: GPL-2.0-or-later
from qtpy import QtCore
from qtpy.QtCore import Signal, QObject, Qt
from qtpy.QtWidgets import (QWidget, QSizePolicy, QHBoxLayout, QVBoxLayout, QLabel,
                             QScrollArea, QPushButton)

from change_manager import ChangeManager, ComboChange
from protocol.constants import VIAL_PROTOCOL_DYNAMIC
from widgets.key_widget import KeyWidget
from tabbed_keycodes import TabbedKeycodes
from vial_device import VialKeyboard
from editor.basic_editor import BasicEditor
from widgets.flowlayout import FlowLayout


class ComboEntryUI(QObject):
    """A single combo entry: small index + 4 input keys + arrow + output key"""

    key_changed = Signal(int)  # emits combo index
    deleted = Signal(int)  # emits combo index

    def __init__(self, idx):
        super().__init__()

        self.idx = idx
        self.kc_inputs = []
        self.all_keys = []  # All keys in order for auto-advance

        # Main horizontal layout for the combo
        self.container = QHBoxLayout()
        self.container.setSpacing(2)
        self.container.setContentsMargins(4, 4, 4, 4)

        # Small superscript-style index number
        self.index_label = QLabel()
        self.index_label.setStyleSheet("font-size: 9px; color: palette(text); min-width: 20px;")
        self.index_label.setAlignment(Qt.AlignRight | Qt.AlignTop)
        self.update_index_label()
        self.container.addWidget(self.index_label)

        # 4 input keys
        for x in range(4):
            kc_widget = KeyWidget()
            kc_widget.changed.connect(lambda idx=x: self.on_key_changed_at(idx))
            self.container.addWidget(kc_widget)
            self.kc_inputs.append(kc_widget)
            self.all_keys.append(kc_widget)

        # Arrow
        arrow = QLabel("\u2192")  # →
        arrow.setStyleSheet("font-size: 16px; color: palette(text);")
        arrow.setAlignment(Qt.AlignCenter)
        self.container.addWidget(arrow)

        # Output key
        self.kc_output = KeyWidget()
        self.kc_output.changed.connect(lambda: self.on_key_changed_at(4))
        self.container.addWidget(self.kc_output)
        self.all_keys.append(self.kc_output)

        # Create the widget
        self.widget_container = QWidget()
        self.widget_container.setObjectName("comboEntry")
        self.widget_container.setStyleSheet("#comboEntry { border: 2px solid transparent; }")
        self.widget_container.setLayout(self.container)
        self.widget_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def update_index_label(self):
        self.index_label.setText(str(self.idx + 1))

    def set_modified(self, modified):
        """Set visual indicator for uncommitted changes."""
        if modified:
            self.widget_container.setStyleSheet("#comboEntry { border: 2px solid palette(link); }")
        else:
            self.widget_container.setStyleSheet("#comboEntry { border: 2px solid transparent; }")

    def widget(self):
        return self.widget_container

    def load(self, data):
        objs = self.kc_inputs + [self.kc_output]
        for o in objs:
            o.blockSignals(True)

        for x in range(4):
            self.kc_inputs[x].set_keycode(data[x])
        self.kc_output.set_keycode(data[4])

        for o in objs:
            o.blockSignals(False)

    def save(self):
        return (
            self.kc_inputs[0].keycode,
            self.kc_inputs[1].keycode,
            self.kc_inputs[2].keycode,
            self.kc_inputs[3].keycode,
            self.kc_output.keycode
        )

    def is_empty(self):
        """Check if this combo has no keys defined"""
        for kc in self.kc_inputs:
            if kc.keycode and kc.keycode != "KC_NO":
                return False
        if self.kc_output.keycode and self.kc_output.keycode != "KC_NO":
            return False
        return True

    def on_key_changed_at(self, key_idx):
        """Called when a specific key in the combo changes - auto-advance to next"""
        self.key_changed.emit(self.idx)

        # Auto-advance to next key (0-3 are inputs, 4 is output)
        next_idx = key_idx + 1
        if next_idx < len(self.all_keys):
            next_key = self.all_keys[next_idx]
            # Select the key (set it as active so it highlights)
            next_key.active_key = next_key.widgets[0]
            next_key.active_mask = False
            next_key.update()
            # Open the keycode tray for the next key
            TabbedKeycodes.open_tray(next_key)

    def delete_widgets(self):
        """Clean up widgets for deletion"""
        for kc in self.kc_inputs:
            kc.delete()
        self.kc_output.delete()


class Combos(BasicEditor):

    CM_KEY_TYPE = 'combo'

    def __init__(self):
        super().__init__()
        self.keyboard = None

        self.combo_entries = []
        self.combo_entries_available = []

        # Pre-create combo entry UIs
        for x in range(128):
            entry = ComboEntryUI(x)
            entry.key_changed.connect(self.on_key_changed)
            self.combo_entries_available.append(entry)

        # Header with count and buttons
        header = QHBoxLayout()
        self.count_label = QLabel("0 of 0 combos defined")
        header.addWidget(self.count_label)
        header.addStretch()

        self.add_btn = QPushButton("+ Add")
        self.add_btn.setFixedWidth(60)
        self.add_btn.clicked.connect(self.on_add_combo)
        header.addWidget(self.add_btn)

        self.show_all_btn = QPushButton("Show All")
        self.show_all_btn.setCheckable(True)
        self.show_all_btn.setFixedWidth(80)
        self.show_all_btn.toggled.connect(self.on_show_all_toggled)
        header.addWidget(self.show_all_btn)

        header_widget = QWidget()
        header_widget.setLayout(header)
        self.addWidget(header_widget)

        # Scrollable area for combos
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Flow layout for combo entries
        self.flow_container = QWidget()
        self.flow_layout = FlowLayout()
        self.flow_layout.setSpacing(8)
        self.flow_container.setLayout(self.flow_layout)

        self.scroll.setWidget(self.flow_container)
        self.addWidget(self.scroll)

        self.show_all = False

    def rebuild_ui(self):
        # Clear flow layout
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            if item.widget():
                item.widget().hide()

        # Load data into entries
        self.combo_entries = self.combo_entries_available[:self.keyboard.combo_count]
        for x, e in enumerate(self.combo_entries):
            e.load(self.keyboard.combo_get(x))

        self.refresh_display()

    def refresh_display(self):
        """Refresh which combos are shown based on show_all setting"""
        cm = ChangeManager.instance()

        # Clear flow layout
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            if item.widget():
                item.widget().hide()

        # Count defined combos and add widgets
        defined_count = 0
        for e in self.combo_entries:
            # Update modified indicator
            e.set_modified(cm.is_modified(('combo', e.idx)))

            if not e.is_empty():
                defined_count += 1

            if self.show_all or not e.is_empty():
                e.widget().show()
                self.flow_layout.addWidget(e.widget())

        # Update count label
        self.count_label.setText(f"{defined_count} of {len(self.combo_entries)} combos defined")

        # Update button text
        if self.show_all:
            self.show_all_btn.setText("Hide Empty")
        else:
            self.show_all_btn.setText("Show All")

    def on_show_all_toggled(self, checked):
        self.show_all = checked
        self.refresh_display()

    def on_add_combo(self):
        """Find first empty combo, show it, and select its first key"""
        for e in self.combo_entries:
            if e.is_empty():
                # Make sure this combo is visible
                if not self.show_all:
                    e.widget().show()
                    self.flow_layout.addWidget(e.widget())

                # Select the first key of this combo
                first_key = e.all_keys[0]
                first_key.active_key = first_key.widgets[0]
                first_key.active_mask = False
                first_key.update()
                TabbedKeycodes.open_tray(first_key)

                # Scroll to make it visible
                self.scroll.ensureWidgetVisible(e.widget())
                return

        # No empty combos available
        # Could show a message, but for now just do nothing

    def rebuild(self, device):
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard
            self.rebuild_ui()

    def _reload_entry(self, idx):
        if idx < len(self.combo_entries):
            self.combo_entries[idx].load(self.keyboard.combo_get(idx))

    def valid(self):
        return isinstance(self.device, VialKeyboard) and \
               (self.device.keyboard and self.device.keyboard.vial_protocol >= VIAL_PROTOCOL_DYNAMIC
                and self.device.keyboard.combo_count > 0)

    def on_key_changed(self, idx):
        new_value = self.combo_entries[idx].save()
        old_value = self.keyboard.combo_entries[idx]

        if old_value != new_value:
            # Track change in ChangeManager for undo/redo
            change = ComboChange(idx, old_value, new_value)
            ChangeManager.instance().add_change(change)
            # Update local state
            self.keyboard.combo_entries[idx] = new_value

        # Refresh display in case combo became empty or non-empty
        if not self.show_all:
            self.refresh_display()
        else:
            # Just update count
            defined_count = sum(1 for e in self.combo_entries if not e.is_empty())
            self.count_label.setText(f"{defined_count} of {len(self.combo_entries)} combos defined")

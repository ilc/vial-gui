# SPDX-License-Identifier: GPL-2.0-or-later
from qtpy import QtCore
from qtpy.QtCore import Signal, QObject, Qt
from qtpy.QtWidgets import (QWidget, QSizePolicy, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QSpinBox, QScrollArea, QGridLayout)

from change_manager import ChangeManager, TapDanceChange
from protocol.constants import VIAL_PROTOCOL_DYNAMIC
from widgets.key_widget import KeyWidget
from tabbed_keycodes import TabbedKeycodes
from vial_device import VialKeyboard
from editor.basic_editor import BasicEditor
from widgets.flowlayout import FlowLayout


class TapDanceEntryUI(QObject):
    """A single tap dance entry with labeled columns"""

    key_changed = Signal(int)  # emits tap dance index
    timing_changed = Signal(int)  # emits tap dance index

    def __init__(self, idx):
        super().__init__()

        self.idx = idx
        self.all_keys = []

        # Use grid layout for proper column alignment
        self.container = QGridLayout()
        self.container.setSpacing(2)
        self.container.setContentsMargins(4, 4, 4, 4)

        # Row 0: Index and column headers
        self.index_label = QLabel()
        self.index_label.setStyleSheet("font-size: 9px; color: palette(text);")
        self.index_label.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        self.update_index_label()
        self.container.addWidget(self.index_label, 0, 0)

        for col, label_text in enumerate(["Tap", "Hold", "2xTap", "T+H"]):
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-size: 9px; color: palette(text);")
            lbl.setAlignment(Qt.AlignCenter)
            self.container.addWidget(lbl, 0, col + 1)

        term_header = QLabel("Term")
        term_header.setStyleSheet("font-size: 9px; color: palette(text);")
        term_header.setAlignment(Qt.AlignCenter)
        self.container.addWidget(term_header, 0, 5)

        # Row 1: Keys and tapping term
        self.kc_on_tap = KeyWidget()
        self.kc_on_tap.changed.connect(lambda: self.on_key_changed_at(0))
        self.container.addWidget(self.kc_on_tap, 1, 1)
        self.all_keys.append(self.kc_on_tap)

        self.kc_on_hold = KeyWidget()
        self.kc_on_hold.changed.connect(lambda: self.on_key_changed_at(1))
        self.container.addWidget(self.kc_on_hold, 1, 2)
        self.all_keys.append(self.kc_on_hold)

        self.kc_on_double_tap = KeyWidget()
        self.kc_on_double_tap.changed.connect(lambda: self.on_key_changed_at(2))
        self.container.addWidget(self.kc_on_double_tap, 1, 3)
        self.all_keys.append(self.kc_on_double_tap)

        self.kc_on_tap_hold = KeyWidget()
        self.kc_on_tap_hold.changed.connect(lambda: self.on_key_changed_at(3))
        self.container.addWidget(self.kc_on_tap_hold, 1, 4)
        self.all_keys.append(self.kc_on_tap_hold)

        self.txt_tapping_term = QSpinBox()
        self.txt_tapping_term.setMinimum(0)
        self.txt_tapping_term.setMaximum(10000)
        self.txt_tapping_term.setSuffix("ms")
        self.txt_tapping_term.setFixedWidth(75)
        self.txt_tapping_term.valueChanged.connect(self.on_timing_changed_internal)
        self.container.addWidget(self.txt_tapping_term, 1, 5)

        # Create the widget
        self.widget_container = QWidget()
        self.widget_container.setObjectName("tapDanceEntry")
        self.widget_container.setStyleSheet("#tapDanceEntry { border: 2px solid transparent; }")
        self.widget_container.setLayout(self.container)
        self.widget_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def update_index_label(self):
        self.index_label.setText(str(self.idx))

    def set_modified(self, modified):
        """Set visual indicator for uncommitted changes."""
        if modified:
            self.widget_container.setStyleSheet("#tapDanceEntry { border: 2px solid palette(link); }")
        else:
            self.widget_container.setStyleSheet("#tapDanceEntry { border: 2px solid transparent; }")

    def widget(self):
        return self.widget_container

    def load(self, data):
        objs = [self.kc_on_tap, self.kc_on_hold, self.kc_on_double_tap,
                self.kc_on_tap_hold, self.txt_tapping_term]
        for o in objs:
            o.blockSignals(True)

        self.kc_on_tap.set_keycode(data[0])
        self.kc_on_hold.set_keycode(data[1])
        self.kc_on_double_tap.set_keycode(data[2])
        self.kc_on_tap_hold.set_keycode(data[3])
        self.txt_tapping_term.setValue(data[4])

        for o in objs:
            o.blockSignals(False)

    def save(self):
        return (
            self.kc_on_tap.keycode,
            self.kc_on_hold.keycode,
            self.kc_on_double_tap.keycode,
            self.kc_on_tap_hold.keycode,
            self.txt_tapping_term.value()
        )

    def is_empty(self):
        """Check if this tap dance has no keys defined"""
        for kc in self.all_keys:
            if kc.keycode and kc.keycode != "KC_NO":
                return False
        return True

    def on_key_changed_at(self, key_idx):
        """Called when a specific key changes - auto-advance to next"""
        self.key_changed.emit(self.idx)

        # Auto-advance to next key (0-3)
        next_idx = key_idx + 1
        if next_idx < len(self.all_keys):
            next_key = self.all_keys[next_idx]
            next_key.active_key = next_key.widgets[0]
            next_key.active_mask = False
            next_key.update()
            TabbedKeycodes.open_tray(next_key)

    def on_timing_changed_internal(self):
        self.timing_changed.emit(self.idx)

    def delete_widgets(self):
        """Clean up widgets for deletion"""
        for kc in self.all_keys:
            kc.delete()


class TapDance(BasicEditor):

    CM_KEY_TYPE = 'tap_dance'

    def __init__(self):
        super().__init__()
        self.keyboard = None

        self.tap_dance_entries = []
        self.tap_dance_entries_available = []

        # Pre-create tap dance entry UIs
        for x in range(128):
            entry = TapDanceEntryUI(x)
            entry.key_changed.connect(self.on_key_changed)
            entry.timing_changed.connect(self.on_timing_changed)
            self.tap_dance_entries_available.append(entry)

        # Header with count and buttons
        header = QHBoxLayout()
        self.count_label = QLabel("0 of 0 tap dances defined")
        header.addWidget(self.count_label)
        header.addStretch()

        self.add_btn = QPushButton("+ Add")
        self.add_btn.setFixedWidth(60)
        self.add_btn.clicked.connect(self.on_add_tap_dance)
        header.addWidget(self.add_btn)

        self.show_all_btn = QPushButton("Show All")
        self.show_all_btn.setCheckable(True)
        self.show_all_btn.setFixedWidth(80)
        self.show_all_btn.toggled.connect(self.on_show_all_toggled)
        header.addWidget(self.show_all_btn)

        header_widget = QWidget()
        header_widget.setLayout(header)
        self.addWidget(header_widget)

        # Scrollable area for tap dances
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Flow layout for tap dance entries
        self.flow_container = QWidget()
        self.flow_layout = FlowLayout()
        self.flow_layout.setSpacing(12)
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
        self.tap_dance_entries = self.tap_dance_entries_available[:self.keyboard.tap_dance_count]
        for x, e in enumerate(self.tap_dance_entries):
            e.load(self.keyboard.tap_dance_get(x))

        self.refresh_display()

    def refresh_display(self):
        """Refresh which tap dances are shown based on show_all setting"""
        cm = ChangeManager.instance()

        # Clear flow layout
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            if item.widget():
                item.widget().hide()

        # Count defined tap dances and add widgets
        defined_count = 0
        for e in self.tap_dance_entries:
            # Update modified indicator
            e.set_modified(cm.is_modified(('tap_dance', e.idx)))

            if not e.is_empty():
                defined_count += 1

            if self.show_all or not e.is_empty():
                e.widget().show()
                self.flow_layout.addWidget(e.widget())

        # Update count label
        self.count_label.setText(f"{defined_count} of {len(self.tap_dance_entries)} tap dances defined")

        # Update button text
        if self.show_all:
            self.show_all_btn.setText("Hide Empty")
        else:
            self.show_all_btn.setText("Show All")

    def on_show_all_toggled(self, checked):
        self.show_all = checked
        self.refresh_display()

    def on_add_tap_dance(self):
        """Find first empty tap dance, show it, and select its first key"""
        for e in self.tap_dance_entries:
            if e.is_empty():
                # Make sure this entry is visible
                if not self.show_all:
                    e.widget().show()
                    self.flow_layout.addWidget(e.widget())

                # Select the first key
                first_key = e.all_keys[0]
                first_key.active_key = first_key.widgets[0]
                first_key.active_mask = False
                first_key.update()
                TabbedKeycodes.open_tray(first_key)

                # Scroll to make it visible
                self.scroll.ensureWidgetVisible(e.widget())
                return

    def rebuild(self, device):
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard
            self.rebuild_ui()

    def _reload_entry(self, idx):
        if idx < len(self.tap_dance_entries):
            self.tap_dance_entries[idx].load(self.keyboard.tap_dance_get(idx))

    def valid(self):
        return isinstance(self.device, VialKeyboard) and \
               (self.device.keyboard and self.device.keyboard.vial_protocol >= VIAL_PROTOCOL_DYNAMIC
                and self.device.keyboard.tap_dance_count > 0)

    def _apply_change(self, idx):
        """Track a tap dance change for undo/redo."""
        new_value = self.tap_dance_entries[idx].save()
        old_value = self.keyboard.tap_dance_entries[idx]

        if old_value != new_value:
            change = TapDanceChange(idx, old_value, new_value)
            ChangeManager.instance().add_change(change)
            self.keyboard.tap_dance_entries[idx] = new_value

    def on_key_changed(self, idx):
        self._apply_change(idx)
        # Refresh display in case tap dance became empty or non-empty
        if not self.show_all:
            self.refresh_display()
        else:
            # Just update count
            defined_count = sum(1 for e in self.tap_dance_entries if not e.is_empty())
            self.count_label.setText(f"{defined_count} of {len(self.tap_dance_entries)} tap dances defined")

    def on_timing_changed(self, idx):
        self._apply_change(idx)

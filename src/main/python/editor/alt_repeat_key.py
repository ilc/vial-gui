# SPDX-License-Identifier: GPL-2.0-or-later
from qtpy.QtCore import Qt, Signal, QObject
from qtpy.QtGui import QFont
from qtpy.QtWidgets import (QWidget, QSizePolicy, QGridLayout, QHBoxLayout, QVBoxLayout,
                             QLabel, QCheckBox, QScrollArea, QPushButton, QToolTip)

from change_manager import ChangeManager, AltRepeatKeyChange
from protocol.constants import VIAL_PROTOCOL_DYNAMIC
from widgets.key_widget import KeyWidget
from tabbed_keycodes import TabbedKeycodes
from protocol.alt_repeat_key import AltRepeatKeyOptions, AltRepeatKeyEntry
from vial_device import VialKeyboard
from editor.basic_editor import BasicEditor
from widgets.flowlayout import FlowLayout


class AltRepeatKeyEntryUI(QObject):
    """A single alt repeat key entry in compact grid format"""

    changed = Signal(int)  # emits entry index

    def __init__(self, idx):
        super().__init__()
        self.idx = idx
        self.all_keys = []

        # Use grid layout for alignment
        self.container = QGridLayout()
        self.container.setSpacing(4)
        self.container.setContentsMargins(6, 6, 6, 6)

        # Row 0: Headers
        col = 0
        self.index_label = QLabel()
        self.index_label.setStyleSheet("font-size: 9px; color: palette(text);")
        self.index_label.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        self.update_index_label()
        self.container.addWidget(self.index_label, 0, col)
        col += 1

        # Enable column (no header, just checkbox below)
        col += 1

        # Key headers with tooltips
        key_tooltips = [
            ("Last", "Last key pressed before Repeat"),
            ("Alt", "Alternative key to output"),
        ]
        for label_text, tooltip in key_tooltips:
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-size: 9px; color: palette(text);")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setToolTip(tooltip)
            self.container.addWidget(lbl, 0, col)
            col += 1

        # Mod headers with tooltips
        mod_tooltips = [
            ("LC", "Left Control"),
            ("LS", "Left Shift"),
            ("LA", "Left Alt"),
            ("LG", "Left GUI/Super"),
            ("RC", "Right Control"),
            ("RS", "Right Shift"),
            ("RA", "Right Alt"),
            ("RG", "Right GUI/Super"),
        ]
        for abbrev, tooltip in mod_tooltips:
            lbl = QLabel(abbrev)
            lbl.setStyleSheet("font-size: 9px; color: palette(text);")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setToolTip(tooltip)
            self.container.addWidget(lbl, 0, col)
            col += 1

        # Option headers with tooltips
        opt_tooltips = [
            ("Def", "Default: Use this alt key when no other matches"),
            ("Bi", "Bidirectional: Works both ways (A→B and B→A)"),
            ("Ign", "Ignore Handedness: Match mods regardless of left/right"),
        ]
        for abbrev, tooltip in opt_tooltips:
            lbl = QLabel(abbrev)
            lbl.setStyleSheet("font-size: 9px; color: palette(text);")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setToolTip(tooltip)
            self.container.addWidget(lbl, 0, col)
            col += 1

        # Row 1: Controls
        col = 1  # Skip index column

        # Enable checkbox
        self.enable_chk = QCheckBox()
        self.enable_chk.setToolTip("Enable this alt repeat key entry")
        self.enable_chk.stateChanged.connect(self.on_change_internal)
        self.container.addWidget(self.enable_chk, 1, col, Qt.AlignCenter)
        col += 1

        # Last key
        self.last_key = KeyWidget()
        self.last_key.changed.connect(lambda: self.on_key_changed_at(0))
        self.container.addWidget(self.last_key, 1, col)
        self.all_keys.append(self.last_key)
        col += 1

        # Alt key
        self.alt_key = KeyWidget()
        self.alt_key.changed.connect(lambda: self.on_key_changed_at(1))
        self.container.addWidget(self.alt_key, 1, col)
        self.all_keys.append(self.alt_key)
        col += 1

        # Mod checkboxes with tooltips
        self.mod_checks = []
        for i, (_, tooltip) in enumerate(mod_tooltips):
            chk = QCheckBox()
            chk.setToolTip(f"Allow with {tooltip}")
            chk.stateChanged.connect(self.on_change_internal)
            self.container.addWidget(chk, 1, col, Qt.AlignCenter)
            self.mod_checks.append(chk)
            col += 1

        # Option checkboxes
        self.opt_default = QCheckBox()
        self.opt_default.setToolTip("Default: Use this alt key when no other matches")
        self.opt_default.stateChanged.connect(self.on_change_internal)
        self.container.addWidget(self.opt_default, 1, col, Qt.AlignCenter)
        col += 1

        self.opt_bidirectional = QCheckBox()
        self.opt_bidirectional.setToolTip("Bidirectional: Works both ways (A→B and B→A)")
        self.opt_bidirectional.stateChanged.connect(self.on_change_internal)
        self.container.addWidget(self.opt_bidirectional, 1, col, Qt.AlignCenter)
        col += 1

        self.opt_ignore_handedness = QCheckBox()
        self.opt_ignore_handedness.setToolTip("Ignore Handedness: Match mods regardless of left/right")
        self.opt_ignore_handedness.stateChanged.connect(self.on_change_internal)
        self.container.addWidget(self.opt_ignore_handedness, 1, col, Qt.AlignCenter)

        # Create the widget
        self.widget_container = QWidget()
        self.widget_container.setObjectName("altRepeatKeyEntry")
        self.widget_container.setStyleSheet("#altRepeatKeyEntry { border: 2px solid transparent; }")
        self.widget_container.setLayout(self.container)
        self.widget_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        # Set tooltip font programmatically
        QToolTip.setFont(QFont('Sans', 11))

    def update_index_label(self):
        self.index_label.setText(str(self.idx + 1))

    def widget(self):
        return self.widget_container

    def set_modified(self, modified):
        """Set visual indicator for uncommitted changes."""
        if modified:
            self.widget_container.setStyleSheet("#altRepeatKeyEntry { border: 2px solid palette(link); }")
        else:
            self.widget_container.setStyleSheet("#altRepeatKeyEntry { border: 2px solid transparent; }")

    def load(self, arep):
        # Block signals
        widgets = [self.enable_chk] + self.mod_checks + [self.opt_default, self.opt_bidirectional, self.opt_ignore_handedness]
        for w in widgets:
            w.blockSignals(True)
        for k in self.all_keys:
            k.blockSignals(True)

        self.enable_chk.setChecked(arep.options.enabled)
        self.last_key.set_keycode(arep.keycode)
        self.alt_key.set_keycode(arep.alt_keycode)

        # Load mods
        for i, chk in enumerate(self.mod_checks):
            chk.setChecked(bool(arep.allowed_mods & (1 << i)))

        # Load options
        self.opt_default.setChecked(arep.options.default_to_this_alt_key)
        self.opt_bidirectional.setChecked(arep.options.bidirectional)
        self.opt_ignore_handedness.setChecked(arep.options.ignore_mod_handedness)

        # Unblock signals
        for w in widgets:
            w.blockSignals(False)
        for k in self.all_keys:
            k.blockSignals(False)

    def save(self):
        arep = AltRepeatKeyEntry()

        # Save options
        arep.options = AltRepeatKeyOptions()
        arep.options.enabled = self.enable_chk.isChecked()
        arep.options.default_to_this_alt_key = self.opt_default.isChecked()
        arep.options.bidirectional = self.opt_bidirectional.isChecked()
        arep.options.ignore_mod_handedness = self.opt_ignore_handedness.isChecked()

        arep.keycode = self.last_key.keycode
        arep.alt_keycode = self.alt_key.keycode

        # Save mods
        mods = 0
        for i, chk in enumerate(self.mod_checks):
            if chk.isChecked():
                mods |= (1 << i)
        arep.allowed_mods = mods

        return arep

    def is_empty(self):
        """Check if this entry has no keys defined"""
        for kc in self.all_keys:
            if kc.keycode and kc.keycode != "KC_NO":
                return False
        return True

    def on_key_changed_at(self, key_idx):
        """Called when a key changes - auto-advance to next"""
        self.changed.emit(self.idx)

        # Auto-advance: Last key -> Alt key
        next_idx = key_idx + 1
        if next_idx < len(self.all_keys):
            next_key = self.all_keys[next_idx]
            next_key.active_key = next_key.widgets[0]
            next_key.active_mask = False
            next_key.update()
            TabbedKeycodes.open_tray(next_key)

    def on_change_internal(self):
        self.changed.emit(self.idx)


class AltRepeatKey(BasicEditor):

    CM_KEY_TYPE = 'alt_repeat_key'

    def __init__(self):
        super().__init__()
        self.keyboard = None

        self.entries = []
        self.entries_available = []

        # Pre-create entry UIs
        for x in range(128):
            entry = AltRepeatKeyEntryUI(x)
            entry.changed.connect(self.on_change)
            self.entries_available.append(entry)

        # Header with count and buttons
        header = QHBoxLayout()
        self.count_label = QLabel("0 of 0 alt repeat keys defined")
        header.addWidget(self.count_label)
        header.addStretch()

        self.add_btn = QPushButton("+ Add")
        self.add_btn.setFixedWidth(60)
        self.add_btn.clicked.connect(self.on_add_entry)
        header.addWidget(self.add_btn)

        self.show_all_btn = QPushButton("Show All")
        self.show_all_btn.setCheckable(True)
        self.show_all_btn.setFixedWidth(80)
        self.show_all_btn.toggled.connect(self.on_show_all_toggled)
        header.addWidget(self.show_all_btn)

        header_widget = QWidget()
        header_widget.setLayout(header)
        self.addWidget(header_widget)

        # Scrollable area for entries
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Flow layout for entries to wrap when window is narrow
        self.entries_container = QWidget()
        self.entries_layout = FlowLayout()
        self.entries_layout.setSpacing(8)
        self.entries_container.setLayout(self.entries_layout)

        self.scroll.setWidget(self.entries_container)
        self.addWidget(self.scroll)

        self.show_all = False

    def rebuild_ui(self):
        # Clear layout
        while self.entries_layout.count():
            item = self.entries_layout.takeAt(0)
            if item.widget():
                item.widget().hide()

        # Load data into entries
        self.entries = self.entries_available[:self.keyboard.alt_repeat_key_count]
        for x, e in enumerate(self.entries):
            e.load(self.keyboard.alt_repeat_key_get(x))

        self.refresh_display()

    def refresh_display(self):
        """Refresh which entries are shown based on show_all setting"""
        cm = ChangeManager.instance()

        # Clear layout
        while self.entries_layout.count():
            item = self.entries_layout.takeAt(0)
            if item.widget():
                item.widget().hide()

        # Count defined entries and add widgets
        defined_count = 0
        for e in self.entries:
            # Update modified indicator
            e.set_modified(cm.is_modified(('alt_repeat_key', e.idx)))

            if not e.is_empty():
                defined_count += 1

            if self.show_all or not e.is_empty():
                e.widget().show()
                self.entries_layout.addWidget(e.widget())

        # Update count label
        self.count_label.setText(f"{defined_count} of {len(self.entries)} alt repeat keys defined")

        # Update button text
        if self.show_all:
            self.show_all_btn.setText("Hide Empty")
        else:
            self.show_all_btn.setText("Show All")

    def on_show_all_toggled(self, checked):
        self.show_all = checked
        self.refresh_display()

    def on_add_entry(self):
        """Find first empty entry, show it, and select its first key"""
        for e in self.entries:
            if e.is_empty():
                # Make sure this entry is visible
                if not self.show_all:
                    e.widget().show()
                    self.entries_layout.addWidget(e.widget())

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
        if idx < len(self.entries):
            self.entries[idx].load(self.keyboard.alt_repeat_key_get(idx))

    def valid(self):
        return isinstance(self.device, VialKeyboard) and \
               (self.device.keyboard and self.device.keyboard.vial_protocol >= VIAL_PROTOCOL_DYNAMIC
                and self.device.keyboard.alt_repeat_key_count > 0)

    def on_change(self, idx):
        new_value = self.entries[idx].save()
        old_value = self.keyboard.alt_repeat_key_entries[idx]

        if old_value != new_value:
            change = AltRepeatKeyChange(idx, old_value, new_value)
            ChangeManager.instance().add_change(change)
            self.keyboard.alt_repeat_key_entries[idx] = new_value

        # Refresh display in case entry became empty or non-empty
        if not self.show_all:
            self.refresh_display()
        else:
            # Just update count
            defined_count = sum(1 for e in self.entries if not e.is_empty())
            self.count_label.setText(f"{defined_count} of {len(self.entries)} alt repeat keys defined")

# SPDX-License-Identifier: GPL-2.0-or-later
import sys
from qtpy.QtCore import Qt, Signal, QObject
from qtpy.QtWidgets import (QWidget, QSizePolicy, QGridLayout, QHBoxLayout, QVBoxLayout,
                             QLabel, QCheckBox, QScrollArea, QPushButton, QMenu, QWidgetAction,
                             QToolButton, QFrame)

from change_manager import ChangeManager, KeyOverrideChange
from protocol.constants import VIAL_PROTOCOL_DYNAMIC
from widgets.key_widget import KeyWidget
from widgets.flowlayout import FlowLayout
from tabbed_keycodes import TabbedKeycodes
from protocol.key_override import KeyOverrideOptions, KeyOverrideEntry
from vial_device import VialKeyboard
from editor.basic_editor import BasicEditor


class LayersPopup(QMenu):
    """Popup menu for layer selection"""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Layer checkboxes in 2 rows of 8
        grid = QGridLayout()
        grid.setSpacing(2)
        self.layer_chks = []
        for i in range(16):
            chk = QCheckBox(str(i))
            chk.stateChanged.connect(self.on_change)
            row = i // 8
            col = i % 8
            grid.addWidget(chk, row, col)
            self.layer_chks.append(chk)
        layout.addLayout(grid)

        # Enable/Disable all buttons
        btn_layout = QHBoxLayout()
        btn_all = QPushButton("All")
        btn_all.setFixedWidth(50)
        btn_all.clicked.connect(self.enable_all)
        btn_none = QPushButton("None")
        btn_none.setFixedWidth(50)
        btn_none.clicked.connect(self.disable_all)
        btn_layout.addWidget(btn_all)
        btn_layout.addWidget(btn_none)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        widget.setLayout(layout)
        action = QWidgetAction(self)
        action.setDefaultWidget(widget)
        self.addAction(action)

    def load(self, data):
        for x, chk in enumerate(self.layer_chks):
            chk.blockSignals(True)
            chk.setChecked(bool(data & (1 << x)))
            chk.blockSignals(False)

    def save(self):
        out = 0
        for x, chk in enumerate(self.layer_chks):
            out |= int(chk.isChecked()) << x
        return out

    def get_summary(self):
        """Return summary text for button"""
        count = sum(1 for chk in self.layer_chks if chk.isChecked())
        if count == 16:
            return "All"
        elif count == 0:
            return "None"
        else:
            return str(count)

    def enable_all(self):
        for chk in self.layer_chks:
            chk.setChecked(True)

    def disable_all(self):
        for chk in self.layer_chks:
            chk.setChecked(False)

    def on_change(self):
        self.changed.emit()


class OptionsPopup(QMenu):
    """Popup menu for options"""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)

        self.opt_activation_trigger_down = QCheckBox("Activate on trigger down")
        self.opt_activation_trigger_down.setToolTip("Activate when the trigger key is pressed down")

        self.opt_activation_required_mod_down = QCheckBox("Activate on mod down")
        self.opt_activation_required_mod_down.setToolTip("Activate when a required modifier is pressed down")

        self.opt_activation_negative_mod_up = QCheckBox("Activate on negative mod up")
        self.opt_activation_negative_mod_up.setToolTip("Activate when a negative modifier is released")

        self.opt_one_mod = QCheckBox("Any trigger mod activates")
        self.opt_one_mod.setToolTip("Activate on any single trigger modifier instead of requiring all")

        self.opt_no_reregister_trigger = QCheckBox("No reregister on deactivate")
        self.opt_no_reregister_trigger.setToolTip("Don't register the trigger key again after override deactivates")

        self.opt_no_unregister_on_other_key_down = QCheckBox("No unregister on other key")
        self.opt_no_unregister_on_other_key_down.setToolTip("Don't deactivate when another key is pressed")

        self.all_opts = [
            self.opt_activation_trigger_down,
            self.opt_activation_required_mod_down,
            self.opt_activation_negative_mod_up,
            self.opt_one_mod,
            self.opt_no_reregister_trigger,
            self.opt_no_unregister_on_other_key_down
        ]

        for opt in self.all_opts:
            opt.stateChanged.connect(self.on_change)
            layout.addWidget(opt)

        widget.setLayout(layout)
        action = QWidgetAction(self)
        action.setDefaultWidget(widget)
        self.addAction(action)

    def load(self, opt: KeyOverrideOptions):
        for w in self.all_opts:
            w.blockSignals(True)
        self.opt_activation_trigger_down.setChecked(opt.activation_trigger_down)
        self.opt_activation_required_mod_down.setChecked(opt.activation_required_mod_down)
        self.opt_activation_negative_mod_up.setChecked(opt.activation_negative_mod_up)
        self.opt_one_mod.setChecked(opt.one_mod)
        self.opt_no_reregister_trigger.setChecked(opt.no_reregister_trigger)
        self.opt_no_unregister_on_other_key_down.setChecked(opt.no_unregister_on_other_key_down)
        for w in self.all_opts:
            w.blockSignals(False)

    def save(self) -> KeyOverrideOptions:
        opts = KeyOverrideOptions()
        opts.activation_trigger_down = self.opt_activation_trigger_down.isChecked()
        opts.activation_required_mod_down = self.opt_activation_required_mod_down.isChecked()
        opts.activation_negative_mod_up = self.opt_activation_negative_mod_up.isChecked()
        opts.one_mod = self.opt_one_mod.isChecked()
        opts.no_reregister_trigger = self.opt_no_reregister_trigger.isChecked()
        opts.no_unregister_on_other_key_down = self.opt_no_unregister_on_other_key_down.isChecked()
        return opts

    def get_summary(self):
        """Return summary text for button"""
        count = sum(1 for opt in self.all_opts if opt.isChecked())
        return str(count) if count > 0 else "0"

    def on_change(self):
        self.changed.emit()


class KeyOverrideEntryUI(QObject):
    """A single key override entry in compact card format"""

    changed = Signal(int)  # emits entry index

    def __init__(self, idx):
        super().__init__()
        self.idx = idx
        self.all_keys = []

        # Main container
        self.container = QVBoxLayout()
        self.container.setSpacing(4)
        self.container.setContentsMargins(8, 8, 8, 8)

        # Row 1: Index, enable, trigger → replacement, layers btn, options btn
        row1 = QHBoxLayout()
        row1.setSpacing(4)

        # Index label
        self.index_label = QLabel(str(idx + 1))
        self.index_label.setStyleSheet("font-size: 9px; color: palette(text);")
        self.index_label.setFixedWidth(20)
        self.index_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row1.addWidget(self.index_label)

        # Enable checkbox
        self.enable_chk = QCheckBox()
        self.enable_chk.setToolTip("Enable this key override")
        self.enable_chk.stateChanged.connect(self.on_change_internal)
        row1.addWidget(self.enable_chk)

        # Trigger key
        self.trigger_key = KeyWidget()
        self.trigger_key.changed.connect(lambda: self.on_key_changed_at(0))
        row1.addWidget(self.trigger_key)
        self.all_keys.append(self.trigger_key)

        # Arrow
        arrow = QLabel("→")
        arrow.setStyleSheet("font-size: 14px; color: palette(text);")
        row1.addWidget(arrow)

        # Replacement key
        self.replacement_key = KeyWidget()
        self.replacement_key.changed.connect(lambda: self.on_key_changed_at(1))
        row1.addWidget(self.replacement_key)
        self.all_keys.append(self.replacement_key)

        row1.addSpacing(20)

        # Layers and Options stacked vertically
        buttons_layout = QVBoxLayout()
        buttons_layout.setSpacing(2)
        buttons_layout.setContentsMargins(0, 0, 0, 0)

        self.layers_popup = LayersPopup()
        self.layers_popup.changed.connect(self.on_layers_changed)
        self.layers_btn = QToolButton()
        self.layers_btn.setText("Layers: All")
        self.layers_btn.setToolTip("Select which layers this override is active on")
        # On web, use manual popup to avoid blocking; on desktop use InstantPopup
        if sys.platform == "emscripten":
            self.layers_btn.clicked.connect(lambda: self.layers_popup.popup(self.layers_btn.mapToGlobal(self.layers_btn.rect().bottomLeft())))
        else:
            self.layers_btn.setPopupMode(QToolButton.InstantPopup)
            self.layers_btn.setMenu(self.layers_popup)
        buttons_layout.addWidget(self.layers_btn)

        self.options_popup = OptionsPopup()
        self.options_popup.changed.connect(self.on_options_changed)
        self.options_btn = QToolButton()
        self.options_btn.setText("Options: 0")
        self.options_btn.setToolTip("Configure override behavior options")
        # On web, use manual popup to avoid blocking; on desktop use InstantPopup
        if sys.platform == "emscripten":
            self.options_btn.clicked.connect(lambda: self.options_popup.popup(self.options_btn.mapToGlobal(self.options_btn.rect().bottomLeft())))
        else:
            self.options_btn.setPopupMode(QToolButton.InstantPopup)
            self.options_btn.setMenu(self.options_popup)
        buttons_layout.addWidget(self.options_btn)

        row1.addLayout(buttons_layout)

        self.container.addLayout(row1)

        # Mod grid - header row + 3 mod rows in a single grid for alignment
        mod_grid = QGridLayout()
        mod_grid.setContentsMargins(0, 0, 0, 0)
        mod_grid.setSpacing(2)

        # Header row (row 0)
        # Empty cell for row label column
        mod_grid.addWidget(QLabel(""), 0, 0)

        mod_names = ["LC", "LS", "LA", "LG", "RC", "RS", "RA", "RG"]
        mod_tooltips = ["Left Ctrl", "Left Shift", "Left Alt", "Left GUI",
                        "Right Ctrl", "Right Shift", "Right Alt", "Right GUI"]
        for col, (name, tooltip) in enumerate(zip(mod_names, mod_tooltips)):
            lbl = QLabel(name)
            lbl.setStyleSheet("font-size: 9px; color: palette(text);")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setToolTip(tooltip)
            mod_grid.addWidget(lbl, 0, col + 1)

        # Mod rows with labels and checkboxes
        self.mod_rows = []

        row_data = [
            ("Trigger", "Trigger modifiers - must be held for override to activate"),
            ("Negative", "Negative modifiers - override won't activate if these are held"),
            ("Suppress", "Suppressed modifiers - these won't be sent when override activates"),
        ]

        for row_idx, (label_text, row_tooltip) in enumerate(row_data):
            grid_row = row_idx + 1  # +1 for header

            # Row label
            row_label = QLabel(label_text)
            row_label.setStyleSheet("font-size: 9px; color: palette(text);")
            row_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row_label.setToolTip(row_tooltip)
            mod_grid.addWidget(row_label, grid_row, 0)

            # Checkboxes
            checkboxes = []
            for col, tooltip in enumerate(mod_tooltips):
                chk = QCheckBox()
                chk.setToolTip(tooltip)
                chk.stateChanged.connect(self.on_change_internal)
                mod_grid.addWidget(chk, grid_row, col + 1)
                checkboxes.append(chk)
            self.mod_rows.append(checkboxes)

        # Wrap grid in widget to control sizing
        mod_widget = QWidget()
        mod_widget.setLayout(mod_grid)
        mod_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.container.addWidget(mod_widget)

        # Create the widget with frame
        self.widget_container = QFrame()
        self.widget_container.setObjectName("keyOverrideEntry")
        self.widget_container.setFrameStyle(QFrame.StyledPanel)
        self.widget_container.setStyleSheet("#keyOverrideEntry { border: 2px solid transparent; }")
        self.widget_container.setLayout(self.container)
        self.widget_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def widget(self):
        return self.widget_container

    def set_modified(self, modified):
        """Set visual indicator for uncommitted changes."""
        if modified:
            self.widget_container.setStyleSheet("#keyOverrideEntry { border: 2px solid palette(link); }")
        else:
            self.widget_container.setStyleSheet("#keyOverrideEntry { border: 2px solid transparent; }")

    def _load_mods(self, row_idx, data):
        """Load modifier data into a row of checkboxes"""
        for x, chk in enumerate(self.mod_rows[row_idx]):
            chk.blockSignals(True)
            chk.setChecked(bool(data & (1 << x)))
            chk.blockSignals(False)

    def _save_mods(self, row_idx):
        """Save modifier data from a row of checkboxes"""
        out = 0
        for x, chk in enumerate(self.mod_rows[row_idx]):
            out |= int(chk.isChecked()) << x
        return out

    def load(self, ko):
        # Block signals
        self.enable_chk.blockSignals(True)
        for k in self.all_keys:
            k.blockSignals(True)

        self.enable_chk.setChecked(ko.options.enabled)
        self.trigger_key.set_keycode(ko.trigger)
        self.replacement_key.set_keycode(ko.replacement)
        self.layers_popup.load(ko.layers)
        self._load_mods(0, ko.trigger_mods)
        self._load_mods(1, ko.negative_mod_mask)
        self._load_mods(2, ko.suppressed_mods)
        self.options_popup.load(ko.options)

        # Update button labels
        self.layers_btn.setText(f"Layers: {self.layers_popup.get_summary()}")
        self.options_btn.setText(f"Options: {self.options_popup.get_summary()}")

        # Unblock signals
        self.enable_chk.blockSignals(False)
        for k in self.all_keys:
            k.blockSignals(False)

    def save(self):
        ko = KeyOverrideEntry()
        ko.options = self.options_popup.save()
        ko.options.enabled = self.enable_chk.isChecked()
        ko.trigger = self.trigger_key.keycode
        ko.replacement = self.replacement_key.keycode
        ko.layers = self.layers_popup.save()
        ko.trigger_mods = self._save_mods(0)
        ko.negative_mod_mask = self._save_mods(1)
        ko.suppressed_mods = self._save_mods(2)
        return ko

    def is_empty(self):
        """Check if this entry has no keys defined"""
        for kc in self.all_keys:
            if kc.keycode and kc.keycode != "KC_NO":
                return False
        return True

    def on_key_changed_at(self, key_idx):
        """Called when a key changes - auto-advance to next"""
        self.changed.emit(self.idx)

        # Auto-advance: Trigger -> Replacement
        if key_idx == 0:
            next_key = self.replacement_key
            next_key.active_key = next_key.widgets[0]
            next_key.active_mask = False
            next_key.update()
            TabbedKeycodes.open_tray(next_key)

    def on_change_internal(self):
        self.changed.emit(self.idx)

    def on_layers_changed(self):
        self.layers_btn.setText(f"Layers: {self.layers_popup.get_summary()}")
        self.changed.emit(self.idx)

    def on_options_changed(self):
        self.options_btn.setText(f"Options: {self.options_popup.get_summary()}")
        self.changed.emit(self.idx)


class KeyOverride(BasicEditor):

    CM_KEY_TYPE = 'key_override'

    def __init__(self):
        super().__init__()
        self.keyboard = None
        self.entries = []
        self.entries_available = []
        self.show_all = False

        # Pre-create entry UIs
        for x in range(128):
            entry = KeyOverrideEntryUI(x)
            entry.changed.connect(self.on_change)
            self.entries_available.append(entry)

        # Header with count and buttons
        header = QHBoxLayout()
        self.count_label = QLabel("0 of 0 key overrides defined")
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
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Flow layout for entries
        self.entries_container = QWidget()
        self.entries_layout = FlowLayout()
        self.entries_layout.setSpacing(8)
        self.entries_container.setLayout(self.entries_layout)

        self.scroll.setWidget(self.entries_container)
        self.addWidget(self.scroll)

    def rebuild_ui(self):
        # Clear layout
        while self.entries_layout.count():
            item = self.entries_layout.takeAt(0)
            if item.widget():
                item.widget().hide()

        # Load data into entries
        self.entries = self.entries_available[:self.keyboard.key_override_count]
        for x, e in enumerate(self.entries):
            e.load(self.keyboard.key_override_get(x))

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
            e.set_modified(cm.is_modified(('key_override', e.idx)))

            if not e.is_empty():
                defined_count += 1

            if self.show_all or not e.is_empty():
                e.widget().show()
                self.entries_layout.addWidget(e.widget())

        # Update count label
        self.count_label.setText(f"{defined_count} of {len(self.entries)} key overrides defined")

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
            self.entries[idx].load(self.keyboard.key_override_get(idx))

    def valid(self):
        return isinstance(self.device, VialKeyboard) and \
               (self.device.keyboard and self.device.keyboard.vial_protocol >= VIAL_PROTOCOL_DYNAMIC
                and self.device.keyboard.key_override_count > 0)

    def on_change(self, idx):
        new_value = self.entries[idx].save()
        old_value = self.keyboard.key_override_entries[idx]

        if old_value != new_value:
            change = KeyOverrideChange(idx, old_value, new_value)
            ChangeManager.instance().add_change(change)
            self.keyboard.key_override_entries[idx] = new_value

        # Refresh display in case entry became empty or non-empty
        if not self.show_all:
            self.refresh_display()
        else:
            # Just update count
            defined_count = sum(1 for e in self.entries if not e.is_empty())
            self.count_label.setText(f"{defined_count} of {len(self.entries)} key overrides defined")

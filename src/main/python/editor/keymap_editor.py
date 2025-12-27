# SPDX-License-Identifier: GPL-2.0-or-later
import json
import sys

from qtpy.QtWidgets import (QHBoxLayout, QLabel, QVBoxLayout, QMessageBox, QWidget,
                             QScrollArea, QSizePolicy, QToolButton, QMenu, QApplication,
                             QComboBox)
from qtpy.QtCore import Qt, Signal, QTimer

from any_keycode_dialog import AnyKeycodeDialog
from change_manager import ChangeManager, KeymapChange, EncoderChange
from editor.basic_editor import BasicEditor
from widgets.keyboard_widget import KeyboardWidget, EncoderWidget
from keycodes.keycodes import Keycode
from widgets.square_button import SquareButton
from tabbed_keycodes import TabbedKeycodes, keycode_filter_masked
from util import tr, KeycodeDisplay
from vial_device import VialKeyboard
from serial_assignment import SerialMode
import storage


class ClickableWidget(QWidget):

    clicked = Signal()

    def mousePressEvent(self, evt):
        super().mousePressEvent(evt)
        self.clicked.emit()


class KeymapEditor(BasicEditor):

    def __init__(self, layout_editor):
        super().__init__()

        self.layout_editor = layout_editor
        self._cm_changed_connected = False

        self.layout_layers = QHBoxLayout()
        self.layout_size = QHBoxLayout()
        layer_label = QLabel(tr("KeymapEditor", "Layer"))

        layout_labels_container = QHBoxLayout()
        layout_labels_container.addWidget(layer_label)
        layout_labels_container.addLayout(self.layout_layers)
        layout_labels_container.addStretch()

        # Auto-Advance dropdown
        self.advance_combo = QComboBox()
        self.advance_modes = [
            (SerialMode.TOP_TO_BOTTOM, "Top to bottom"),
            (SerialMode.LEFT_TO_RIGHT, "Left to right"),
            (SerialMode.CLUSTER, "By cluster"),
            (SerialMode.DIRECTION, "By direction"),
        ]
        for mode, label in self.advance_modes:
            self.advance_combo.addItem(label, mode)
        self.advance_combo.currentIndexChanged.connect(self._on_advance_changed)
        layout_labels_container.addWidget(self.advance_combo)

        # Layer operations dropdown
        self.layer_btn = QToolButton()
        self.layer_btn.setText("Layer ▾")
        self.layer_menu = QMenu()
        self.layer_menu.addAction("Copy layer", self.copy_layer)
        self.layer_menu.addAction("Paste layer", self.paste_layer)
        self.layer_menu.addSeparator()
        self.layer_menu.addAction("Fill with KC_NO", lambda: self.fill_layer("KC_NO"))
        self.layer_menu.addAction("Fill with KC_TRNS", lambda: self.fill_layer("KC_TRNS"))
        self.layer_menu.addAction("KC_NO → KC_TRNS", self.convert_no_to_trns)

        # On web, use manual popup to avoid blocking; on desktop use InstantPopup
        if sys.platform == "emscripten":
            self.layer_btn.clicked.connect(lambda: self.layer_menu.popup(self.layer_btn.mapToGlobal(self.layer_btn.rect().bottomLeft())))
        else:
            self.layer_btn.setPopupMode(QToolButton.InstantPopup)
            self.layer_btn.setMenu(self.layer_menu)
        layout_labels_container.addWidget(self.layer_btn)

        layout_labels_container.addLayout(self.layout_size)

        # contains the actual keyboard
        self.container = KeyboardWidget(layout_editor)
        self.container.clicked.connect(self.on_key_clicked)
        self.container.deselected.connect(self.on_key_deselected)

        # Wrap keyboard in scroll area with auto-hiding scrollbars
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.container)
        self.scroll_area.setWidgetResizable(False)  # Keep keyboard at natural size
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        # Use window background color for keyboard area
        self.scroll_area.setStyleSheet("QScrollArea { border: 1px solid palette(mid); background: palette(window); }")

        layout = QVBoxLayout()
        layout.addLayout(layout_labels_container)
        layout.addWidget(self.scroll_area, 1)  # stretch factor 1 ensures it gets space
        w = ClickableWidget()
        w.setLayout(layout)
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        w.clicked.connect(self.on_empty_space_clicked)

        self.layer_buttons = []
        self.keyboard = None
        self.current_layer = 0

        layout_editor.changed.connect(self.on_layout_changed)

        self.container.anykey.connect(self.on_any_keycode)

        self.tabbed_keycodes = TabbedKeycodes()
        self.tabbed_keycodes.keycode_changed.connect(self.on_keycode_changed)
        self.tabbed_keycodes.anykey.connect(self.on_any_keycode)

        self.addWidget(w)
        self.addWidget(self.tabbed_keycodes)

        self.device = None
        KeycodeDisplay.notify_keymap_override(self)

    def on_empty_space_clicked(self):
        self.container.deselect()
        self.container.update()

    def on_keycode_changed(self, code):
        self.set_key(code)

    def rebuild_layers(self):
        # delete old layer labels
        for label in self.layer_buttons:
            label.hide()
            label.deleteLater()
        self.layer_buttons = []

        # create new layer labels
        for x in range(self.keyboard.layers):
            btn = SquareButton(str(x))
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setRelSize(1.667)
            btn.setCheckable(True)
            btn.setStyleSheet("QPushButton { margin: 2px; }")
            btn.clicked.connect(lambda state, idx=x: self.switch_layer(idx))
            self.layout_layers.addWidget(btn)
            self.layer_buttons.append(btn)
        for x in range(0,2):
            btn = SquareButton("-") if x else SquareButton("+")
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setCheckable(False)
            btn.clicked.connect(lambda state, idx=x: self.adjust_size(idx))
            self.layout_size.addWidget(btn)
            self.layer_buttons.append(btn)

    def adjust_size(self, minus):
        current = self.container.get_scale()
        if minus:
            new_scale = max(0.5, current - 0.1)
        else:
            new_scale = min(3.0, current + 0.1)
        self.container.set_scale(new_scale)
        self.refresh_layer_display()
        # Just resize container without auto-fitting (user is manually adjusting)
        self.container.resize(self.container.sizeHint())
        self.container.update()

    def rebuild(self, device):
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard

            # Also connect to 'changed' for layer button updates
            cm = ChangeManager.instance()
            if self._cm_changed_connected:
                cm.changed.disconnect(self.on_change_manager_changed)
            cm.changed.connect(self.on_change_manager_changed)
            self._cm_changed_connected = True

            # get number of layers
            self.rebuild_layers()

            self.container.set_keys(self.keyboard.keys, self.keyboard.encoders)

            self.current_layer = 0
            self.container.current_layer = 0  # For modified key indicators
            self.on_layout_changed()

            self.tabbed_keycodes.recreate_keycode_buttons()
            TabbedKeycodes.tray.recreate_keycode_buttons()
            self.refresh_layer_display()

            # Update User tab label based on whether Svalboard is connected
            is_svalboard = getattr(self.keyboard, 'is_svalboard', False)
            label = "Svalboard" if is_svalboard else "User"
            self.tabbed_keycodes.set_user_tab_label(label)

            # Configure serial assignment dropdown
            self.container._matrix_cols = self.keyboard.cols
            # Show/hide Svalboard-specific modes
            for i, (m, _) in enumerate(self.advance_modes):
                # Hide CLUSTER and DIRECTION for non-Svalboard
                hidden = m in (SerialMode.CLUSTER, SerialMode.DIRECTION) and not is_svalboard
                # QComboBox doesn't have hide for items, so we remove/add - but simpler to just leave them
                # Users can still select them, they just won't be useful

            # Load saved serial mode
            saved_mode_name = storage.get("serial_mode", SerialMode.TOP_TO_BOTTOM.name)
            try:
                mode = SerialMode[saved_mode_name]
            except KeyError:
                mode = SerialMode.TOP_TO_BOTTOM
            # Fall back if Svalboard mode but not Svalboard
            if mode in (SerialMode.CLUSTER, SerialMode.DIRECTION) and not is_svalboard:
                mode = SerialMode.TOP_TO_BOTTOM
            # Set combo to saved mode
            for i, (m, _) in enumerate(self.advance_modes):
                if m == mode:
                    self.advance_combo.blockSignals(True)
                    self.advance_combo.setCurrentIndex(i)
                    self.advance_combo.blockSignals(False)
                    break
            self.container.set_serial_mode(mode)

            # Delay resize to after event loop processes layout
            QTimer.singleShot(0, self._update_container_size)
        self.container.setEnabled(self.valid())

    def _update_container_size(self):
        """Update container size after layout is processed"""
        self.container.resize(self.container.sizeHint())
        self.container.update()
        # Delay auto-fit to ensure viewport is properly sized
        QTimer.singleShot(100, self._auto_fit_keyboard)

    def _auto_fit_keyboard(self):
        """Auto-scale keyboard to fit in scroll area without scrolling"""
        available_width = self.scroll_area.viewport().width()
        available_height = self.scroll_area.viewport().height()

        if available_width <= 50 or available_height <= 50:
            return

        # Calculate base dimensions at scale=1
        current_scale = self.container.get_scale()
        if current_scale <= 0:
            current_scale = 1

        # Current dimensions are at current_scale, so base = current / scale
        base_width = self.container.width / current_scale
        base_height = self.container.height / current_scale

        if base_width <= 0 or base_height <= 0:
            return

        # Calculate scale to fit
        scale_for_width = available_width / base_width
        scale_for_height = available_height / base_height
        new_scale = min(scale_for_width, scale_for_height) * 0.95  # 5% margin

        # Clamp to reasonable range
        new_scale = max(0.3, min(3.0, new_scale))

        if abs(new_scale - current_scale) > 0.01:
            self.container.set_scale(new_scale)
            self.container.resize(self.container.sizeHint())
            self.refresh_layer_display()

    def valid(self):
        return isinstance(self.device, VialKeyboard)

    def save_layout(self):
        return self.keyboard.save_layout()

    def restore_layout(self, data):
        if json.loads(data.decode("utf-8")).get("uid") != self.keyboard.keyboard_id:
            ret = QMessageBox.question(self.widget(), "",
                                       tr("KeymapEditor", "Saved keymap belongs to a different keyboard,"
                                                          " are you sure you want to continue?"),
                                       QMessageBox.Yes | QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
        self.keyboard.restore_layout(data)
        self.refresh_layer_display()

    def on_any_keycode(self):
        if self.container.active_key is None:
            return
        current_code = self.code_for_widget(self.container.active_key)
        if self.container.active_mask:
            kc = Keycode.find_inner_keycode(current_code)
            current_code = kc.qmk_id

        self.dlg = AnyKeycodeDialog(current_code)
        self.dlg.finished.connect(self.on_dlg_finished)
        self.dlg.setModal(True)
        self.dlg.show()

    def on_dlg_finished(self, res):
        if res > 0:
            self.on_keycode_changed(self.dlg.value)

    def code_for_widget(self, widget):
        if widget.desc.row is not None:
            return self.keyboard.layout[(self.current_layer, widget.desc.row, widget.desc.col)]
        else:
            return self.keyboard.encoder_layout[(self.current_layer, widget.desc.encoder_idx,
                                                 widget.desc.encoder_dir)]

    def refresh_layer_display(self):
        """ Refresh text on key widgets to display data corresponding to current layer """

        self.container.update_layout()

        cm = ChangeManager.instance()

        # Check which layers have uncommitted changes
        layers_with_changes = set()
        for key in cm.get_modified_keys():
            if key[0] == 'keymap' and len(key) >= 2:
                layers_with_changes.add(key[1])
            elif key[0] == 'encoder' and len(key) >= 2:
                layers_with_changes.add(key[1])

        for idx, btn in enumerate(self.layer_buttons):
            btn.setEnabled(idx != self.current_layer)
            btn.setChecked(idx == self.current_layer)

            # Highlight layers with uncommitted changes
            if idx < self.keyboard.layers:
                if idx in layers_with_changes:
                    btn.setStyleSheet("QPushButton { margin: 0px; border: 2px solid palette(link); }")
                else:
                    btn.setStyleSheet("QPushButton { margin: 2px; }")

        for widget in self.container.widgets:
            code = self.code_for_widget(widget)
            KeycodeDisplay.display_keycode(widget, code)
        self.container.update()
        self.container.updateGeometry()

    def switch_layer(self, idx):
        self.container.deselect()
        self.current_layer = idx
        self.container.current_layer = idx  # For modified key indicators
        self.refresh_layer_display()

    def set_key(self, keycode):
        """ Change currently selected key to provided keycode """

        if self.container.active_key is None:
            return

        if isinstance(self.container.active_key, EncoderWidget):
            self.set_key_encoder(keycode)
        else:
            self.set_key_matrix(keycode)

        self.container.select_next()

    def set_key_encoder(self, keycode):
        l, i, d = self.current_layer, self.container.active_key.desc.encoder_idx,\
                            self.container.active_key.desc.encoder_dir

        # if masked, ensure that this is a byte-sized keycode
        if self.container.active_mask:
            if not Keycode.is_basic(keycode):
                return
            kc = Keycode.find_outer_keycode(self.keyboard.encoder_layout[(l, i, d)])
            if kc is None:
                return
            keycode = kc.qmk_id.replace("(kc)", "({})".format(keycode))

        old_value = self.keyboard.encoder_layout[(l, i, d)]
        if old_value != keycode:
            # Track change for undo/redo
            change = EncoderChange(l, i, d, old_value, keycode)
            ChangeManager.instance().add_change(change)
            # Update local state for UI
            self.keyboard.encoder_layout[(l, i, d)] = keycode
            self.refresh_layer_display()

    def set_key_matrix(self, keycode):
        l, r, c = self.current_layer, self.container.active_key.desc.row, self.container.active_key.desc.col

        if r >= 0 and c >= 0:
            # if masked, ensure that this is a byte-sized keycode
            if self.container.active_mask:
                if not Keycode.is_basic(keycode):
                    return
                kc = Keycode.find_outer_keycode(self.keyboard.layout[(l, r, c)])
                if kc is None:
                    return
                keycode = kc.qmk_id.replace("(kc)", "({})".format(keycode))

            old_value = self.keyboard.layout[(l, r, c)]
            if old_value != keycode:
                # Track change for undo/redo
                change = KeymapChange(l, r, c, old_value, keycode)
                ChangeManager.instance().add_change(change)
                # Update local state for UI
                self.keyboard.layout[(l, r, c)] = keycode
                self.refresh_layer_display()

    def on_key_clicked(self):
        """ Called when a key on the keyboard widget is clicked """
        self.refresh_layer_display()
        if self.container.active_mask:
            self.tabbed_keycodes.set_keycode_filter(keycode_filter_masked)
        else:
            self.tabbed_keycodes.set_keycode_filter(None)

    def on_key_deselected(self):
        self.tabbed_keycodes.set_keycode_filter(None)

    def on_layout_changed(self):
        if self.keyboard is None:
            return

        self.refresh_layer_display()
        self.keyboard.set_layout_options(self.layout_editor.pack())

    def on_keymap_override(self):
        self.refresh_layer_display()

    def on_change_manager_changed(self):
        """Called when ChangeManager state changes (undo/redo)."""
        self.refresh_layer_display()

    def _on_values_restored(self, affected_keys):
        """Refresh keyboard widget when keymap/encoder values are restored by undo/redo."""
        for key in affected_keys:
            if key[0] in ('keymap', 'encoder'):
                # Refresh keyboard widget display from keyboard.layout
                self.refresh_layer_display()
                return

    def _on_advance_changed(self, index):
        """Handle serial assignment mode change."""
        mode = self.advance_combo.currentData()
        self.container.set_serial_mode(mode)
        storage.set("serial_mode", mode.name)

    def copy_layer(self):
        """Copy current layer keycodes to clipboard as JSON."""
        if self.keyboard is None:
            return
        layer_data = []
        for row in range(self.keyboard.rows):
            for col in range(self.keyboard.cols):
                key = (self.current_layer, row, col)
                layer_data.append(self.keyboard.layout.get(key, "KC_NO"))
        clipboard = QApplication.clipboard()
        clipboard.setText(json.dumps(layer_data))

    def _set_key_at(self, layer, row, col, keycode):
        """Set a key at the given position, tracking the change."""
        key = (layer, row, col)
        old_value = self.keyboard.layout.get(key)
        if old_value != keycode:
            change = KeymapChange(layer, row, col, old_value, keycode)
            ChangeManager.instance().add_change(change)
            self.keyboard.layout[key] = keycode

    def paste_layer(self):
        """Paste layer keycodes from clipboard JSON."""
        if self.keyboard is None:
            return
        clipboard = QApplication.clipboard()
        try:
            layer_data = json.loads(clipboard.text())
            if not isinstance(layer_data, list):
                return
            cm = ChangeManager.instance()
            cm.begin_group("Paste layer")
            idx = 0
            for row in range(self.keyboard.rows):
                for col in range(self.keyboard.cols):
                    if idx < len(layer_data):
                        self._set_key_at(self.current_layer, row, col, layer_data[idx])
                        idx += 1
            cm.end_group()
            self.refresh_layer_display()
        except (json.JSONDecodeError, TypeError):
            pass  # Invalid clipboard data

    def fill_layer(self, keycode):
        """Fill all keys on current layer with a keycode."""
        if self.keyboard is None:
            return
        cm = ChangeManager.instance()
        cm.begin_group("Fill layer")
        for row in range(self.keyboard.rows):
            for col in range(self.keyboard.cols):
                self._set_key_at(self.current_layer, row, col, keycode)
        cm.end_group()
        self.refresh_layer_display()

    def convert_no_to_trns(self):
        """Convert all KC_NO keys on current layer to KC_TRNS."""
        if self.keyboard is None:
            return
        cm = ChangeManager.instance()
        cm.begin_group("Convert KC_NO to KC_TRNS")
        for row in range(self.keyboard.rows):
            for col in range(self.keyboard.cols):
                key = (self.current_layer, row, col)
                if self.keyboard.layout.get(key) == "KC_NO":
                    self._set_key_at(self.current_layer, row, col, "KC_TRNS")
        cm.end_group()
        self.refresh_layer_display()

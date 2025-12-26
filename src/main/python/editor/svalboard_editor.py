# SPDX-License-Identifier: GPL-2.0-or-later
from qtpy import QtCore
from qtpy.QtCore import Qt
from qtpy.QtGui import QColor
from qtpy.QtWidgets import (QWidget, QPushButton, QHBoxLayout, QVBoxLayout,
                              QGridLayout, QLabel, QComboBox, QCheckBox,
                              QColorDialog, QGroupBox, QScrollArea, QSizePolicy,
                              QFrame)

from change_manager import ChangeManager, SvalboardSettingChange, SvalboardLayerColorChange
from editor.basic_editor import BasicEditor
from widgets.clickable_label import ClickableLabel
from util import tr
from vial_device import VialKeyboard


class SvalboardEditor(BasicEditor):

    def __init__(self):
        super().__init__()
        self.keyboard = None

        # Pending changes (for deferred save)
        self.pending_layer_colors = None
        self.pending_settings = None

        # Create scrollable container
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        container_widget = QWidget()
        self.container = QVBoxLayout()
        self.container.setAlignment(Qt.AlignTop)
        container_widget.setLayout(self.container)
        scroll.setWidget(container_widget)

        # Layer Colors section
        self._create_layer_colors_section()

        # Left/Right Pointer sections side by side
        self._create_pointer_sections()

        # Mouse Layer section
        self._create_mouse_section()

        # Scroll section
        self._create_scroll_section()

        # Experimental/Dangerous section
        self._create_experimental_section()

        self.container.addStretch()
        self.addWidget(scroll)

    def _create_layer_colors_section(self):
        group = QGroupBox(tr("SvalboardEditor", "Layer Colors"))
        layout = QGridLayout()

        self.layer_color_widgets = []
        # 4x8 grid for up to 32 layers
        for i in range(32):
            row = i // 8
            col = i % 8

            frame = QWidget()
            frame.setObjectName("layer_color_frame")
            frame.setStyleSheet("#layer_color_frame { border: 2px solid transparent; }")
            frame_layout = QVBoxLayout()
            frame_layout.setContentsMargins(2, 2, 2, 2)
            frame_layout.setSpacing(2)

            color_btn = ClickableLabel()
            color_btn.setFixedSize(30, 20)
            color_btn.setStyleSheet("background-color: #000000; border: 1px solid gray;")
            color_btn.clicked.connect(lambda idx=i: self.on_layer_color_click(idx))

            label = QLabel(str(i))
            label.setAlignment(Qt.AlignCenter)

            frame_layout.addWidget(color_btn, alignment=Qt.AlignCenter)
            frame_layout.addWidget(label)
            frame.setLayout(frame_layout)

            layout.addWidget(frame, row, col)
            self.layer_color_widgets.append((frame, color_btn, label))

        group.setLayout(layout)
        self.layer_colors_group = group
        self.container.addWidget(group)

    def _create_pointer_sections(self):
        # Container for left and right pointer groups side by side
        pointer_container = QHBoxLayout()

        # Left Pointer group
        self.left_pointer_group = QGroupBox(tr("SvalboardEditor", "Left Pointer"))
        left_group = self.left_pointer_group
        left_layout = QVBoxLayout()

        # DPI row in a frame for highlighting
        self.left_dpi_frame = QFrame()
        self.left_dpi_frame.setObjectName("setting_frame")
        self.left_dpi_frame.setStyleSheet("#setting_frame { border: 2px solid transparent; }")
        dpi_layout = QHBoxLayout()
        dpi_layout.setContentsMargins(2, 2, 2, 2)
        dpi_layout.addWidget(QLabel(tr("SvalboardEditor", "DPI")))
        self.left_dpi = QComboBox()
        self.left_dpi.currentIndexChanged.connect(self.on_setting_changed)
        dpi_layout.addWidget(self.left_dpi)
        self.left_dpi_frame.setLayout(dpi_layout)
        left_layout.addWidget(self.left_dpi_frame)

        self.left_scroll = QCheckBox(tr("SvalboardEditor", "Scroll mode"))
        self.left_scroll.setStyleSheet("border: 2px solid transparent;")
        self.left_scroll.stateChanged.connect(self.on_setting_changed)
        left_layout.addWidget(self.left_scroll)

        left_group.setLayout(left_layout)
        pointer_container.addWidget(left_group)

        # Right Pointer group
        self.right_pointer_group = QGroupBox(tr("SvalboardEditor", "Right Pointer"))
        right_group = self.right_pointer_group
        right_layout = QVBoxLayout()

        # DPI row in a frame for highlighting
        self.right_dpi_frame = QFrame()
        self.right_dpi_frame.setObjectName("setting_frame")
        self.right_dpi_frame.setStyleSheet("#setting_frame { border: 2px solid transparent; }")
        dpi_layout = QHBoxLayout()
        dpi_layout.setContentsMargins(2, 2, 2, 2)
        dpi_layout.addWidget(QLabel(tr("SvalboardEditor", "DPI")))
        self.right_dpi = QComboBox()
        self.right_dpi.currentIndexChanged.connect(self.on_setting_changed)
        dpi_layout.addWidget(self.right_dpi)
        self.right_dpi_frame.setLayout(dpi_layout)
        right_layout.addWidget(self.right_dpi_frame)

        self.right_scroll = QCheckBox(tr("SvalboardEditor", "Scroll mode"))
        self.right_scroll.setStyleSheet("border: 2px solid transparent;")
        self.right_scroll.stateChanged.connect(self.on_setting_changed)
        right_layout.addWidget(self.right_scroll)

        right_group.setLayout(right_layout)
        pointer_container.addWidget(right_group)

        self.container.addLayout(pointer_container)

    def _create_mouse_section(self):
        self.mouse_group = QGroupBox(tr("SvalboardEditor", "Mouse Layer"))
        layout = QVBoxLayout()

        # Auto-mouse
        self.auto_mouse = QCheckBox(tr("SvalboardEditor", "Enable"))
        self.auto_mouse.setStyleSheet("border: 2px solid transparent;")
        self.auto_mouse.stateChanged.connect(self.on_setting_changed)
        layout.addWidget(self.auto_mouse)

        # Mouse layer timeout in a frame for highlighting
        self.mh_timeout_frame = QFrame()
        self.mh_timeout_frame.setObjectName("setting_frame")
        self.mh_timeout_frame.setStyleSheet("#setting_frame { border: 2px solid transparent; }")
        timeout_layout = QHBoxLayout()
        timeout_layout.setContentsMargins(2, 2, 2, 2)
        timeout_layout.addWidget(QLabel(tr("SvalboardEditor", "Timeout")))
        self.mh_timeout = QComboBox()
        self.mh_timeout.currentIndexChanged.connect(self.on_setting_changed)
        timeout_layout.addWidget(self.mh_timeout)
        self.mh_timeout_frame.setLayout(timeout_layout)
        layout.addWidget(self.mh_timeout_frame)

        self.mouse_group.setLayout(layout)
        self.container.addWidget(self.mouse_group)

    def _create_scroll_section(self):
        group = QGroupBox(tr("SvalboardEditor", "Scroll"))
        layout = QVBoxLayout()

        # Axis scroll lock
        self.axis_scroll_lock = QCheckBox(tr("SvalboardEditor", "Axis lock"))
        self.axis_scroll_lock.setStyleSheet("border: 2px solid transparent;")
        self.axis_scroll_lock.stateChanged.connect(self.on_setting_changed)
        layout.addWidget(self.axis_scroll_lock)

        # Natural scroll (inverts vertical scroll direction)
        self.natural_scroll = QCheckBox(tr("SvalboardEditor", "Natural scroll"))
        self.natural_scroll.setStyleSheet("border: 2px solid transparent;")
        self.natural_scroll.stateChanged.connect(self.on_setting_changed)
        layout.addWidget(self.natural_scroll)

        group.setLayout(layout)
        self.container.addWidget(group)

    def _create_experimental_section(self):
        group = QGroupBox(tr("SvalboardEditor", "Experimental/Dangerous"))
        layout = QVBoxLayout()

        # Turbo scan in a frame for highlighting
        self.turbo_scan_frame = QFrame()
        self.turbo_scan_frame.setObjectName("setting_frame")
        self.turbo_scan_frame.setStyleSheet("#setting_frame { border: 2px solid transparent; }")
        turbo_layout = QHBoxLayout()
        turbo_layout.setContentsMargins(2, 2, 2, 2)
        turbo_layout.addWidget(QLabel(tr("SvalboardEditor", "Turbo scan level")))
        self.turbo_scan = QComboBox()
        self.turbo_scan.currentIndexChanged.connect(self.on_setting_changed)
        turbo_layout.addWidget(self.turbo_scan)
        self.turbo_scan_frame.setLayout(turbo_layout)
        layout.addWidget(self.turbo_scan_frame)

        group.setLayout(layout)
        self.container.addWidget(group)

    def valid(self):
        return (isinstance(self.device, VialKeyboard) and
                self.device.keyboard is not None and
                getattr(self.device.keyboard, 'is_svalboard', False))

    def rebuild(self, device):
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard
            # Connect to ChangeManager signals for undo/redo
            cm = ChangeManager.instance()
            try:
                cm.values_restored.disconnect(self._on_values_restored)
            except TypeError:
                pass
            try:
                cm.saved.disconnect(self._on_saved)
            except TypeError:
                pass
            cm.values_restored.connect(self._on_values_restored)
            cm.saved.connect(self._on_saved)
            self._update_layer_visibility()
            self._update_dpi_dropdowns()
            self._update_mh_timeout_dropdown()
            self._update_turbo_scan_dropdown()
            self.update_from_keyboard()

    def _on_values_restored(self, affected_keys):
        """Refresh UI when values are restored by undo/redo."""
        needs_refresh = False
        for key in affected_keys:
            if key[0] in ('svalboard', 'svalboard_layer_color'):
                needs_refresh = True
                break
        if needs_refresh:
            self.update_from_keyboard()

    def _on_saved(self):
        """Clear highlights after changes are pushed to device."""
        self._update_buttons()

    def _update_dpi_dropdowns(self):
        """Populate DPI dropdowns with values from firmware"""
        self.left_dpi.blockSignals(True)
        self.right_dpi.blockSignals(True)

        self.left_dpi.clear()
        self.right_dpi.clear()

        for dpi in self.keyboard.sval_dpi_levels:
            self.left_dpi.addItem(str(dpi))
            self.right_dpi.addItem(str(dpi))

        self.left_dpi.blockSignals(False)
        self.right_dpi.blockSignals(False)

    def _update_mh_timeout_dropdown(self):
        """Populate mouse layer timeout dropdown with values from firmware"""
        self.mh_timeout.blockSignals(True)
        self.mh_timeout.clear()

        for timeout in self.keyboard.sval_mh_timers:
            if timeout < 0:
                self.mh_timeout.addItem("Infinite")
            else:
                self.mh_timeout.addItem(f"{timeout} ms")

        self.mh_timeout.blockSignals(False)

    def _update_turbo_scan_dropdown(self):
        """Populate turbo scan dropdown with levels from firmware"""
        self.turbo_scan.blockSignals(True)
        self.turbo_scan.clear()

        for level in range(self.keyboard.sval_turbo_scan_limit):
            self.turbo_scan.addItem(str(level))

        self.turbo_scan.blockSignals(False)

    def _update_layer_visibility(self):
        """Show/hide layer color widgets based on actual layer count"""
        layer_count = self.keyboard.sval_layer_count
        for i, (frame, color_btn, label) in enumerate(self.layer_color_widgets):
            if i < layer_count:
                frame.show()
            else:
                frame.hide()

    def update_from_keyboard(self):
        """Load current state from keyboard into widgets."""
        if not self.keyboard:
            return

        self._block_signals()

        # Load layer colors
        if self.keyboard.sval_layer_colors:
            self.pending_layer_colors = list(self.keyboard.sval_layer_colors)
            for i, (h, s, v) in enumerate(self.keyboard.sval_layer_colors):
                if i < len(self.layer_color_widgets):
                    # Firmware uses 0-255 for hue, Qt uses 0-359
                    qt_hue = int(h * 359 / 255) if h > 0 else 0
                    color = QColor.fromHsv(qt_hue, s, v)
                    self.layer_color_widgets[i][1].setStyleSheet(
                        f"background-color: {color.name()}; border: 1px solid gray;"
                    )

        # Load settings
        if self.keyboard.sval_settings:
            settings = self.keyboard.sval_settings
            self.pending_settings = settings.copy()

            self.left_dpi.setCurrentIndex(settings.get('left_dpi_index', 0))
            self.right_dpi.setCurrentIndex(settings.get('right_dpi_index', 0))
            self.left_scroll.setChecked(settings.get('left_scroll', False))
            self.right_scroll.setChecked(settings.get('right_scroll', False))
            self.axis_scroll_lock.setChecked(settings.get('axis_scroll_lock', False))
            self.natural_scroll.setChecked(settings.get('natural_scroll', False))
            self.auto_mouse.setChecked(settings.get('auto_mouse', False))
            self.mh_timeout.setCurrentIndex(settings.get('mh_timer_index', 0))
            self.turbo_scan.setCurrentIndex(settings.get('turbo_scan', 0))

        self._unblock_signals()
        self._update_buttons()
        self._update_settings_highlights()

    def _block_signals(self):
        self.left_dpi.blockSignals(True)
        self.right_dpi.blockSignals(True)
        self.left_scroll.blockSignals(True)
        self.right_scroll.blockSignals(True)
        self.axis_scroll_lock.blockSignals(True)
        self.natural_scroll.blockSignals(True)
        self.auto_mouse.blockSignals(True)
        self.mh_timeout.blockSignals(True)
        self.turbo_scan.blockSignals(True)

    def _unblock_signals(self):
        self.left_dpi.blockSignals(False)
        self.right_dpi.blockSignals(False)
        self.left_scroll.blockSignals(False)
        self.right_scroll.blockSignals(False)
        self.axis_scroll_lock.blockSignals(False)
        self.natural_scroll.blockSignals(False)
        self.auto_mouse.blockSignals(False)
        self.mh_timeout.blockSignals(False)
        self.turbo_scan.blockSignals(False)

    def on_layer_color_click(self, layer_idx):
        if not self.pending_layer_colors or layer_idx >= len(self.pending_layer_colors):
            return

        h, s, v = self.pending_layer_colors[layer_idx]
        # Firmware uses 0-255 for hue, Qt uses 0-359
        qt_hue = int(h * 359 / 255) if h > 0 else 0
        current_color = QColor.fromHsv(qt_hue, s, v)

        dlg = QColorDialog()
        dlg.setCurrentColor(current_color)

        def on_color_selected(color):
            qt_h = color.hue() if color.hue() >= 0 else 0
            # Convert Qt hue (0-359) back to firmware hue (0-255)
            fw_h = int(qt_h * 255 / 359) if qt_h > 0 else 0
            new_s = color.saturation()
            new_v = color.value()

            old_hsv = self.pending_layer_colors[layer_idx]
            new_hsv = (fw_h, new_s, new_v)
            if old_hsv != new_hsv:
                # Track change for undo/redo
                change = SvalboardLayerColorChange(layer_idx, old_hsv, new_hsv)
                ChangeManager.instance().add_change(change)
                self.pending_layer_colors[layer_idx] = new_hsv
                self.keyboard.sval_layer_colors[layer_idx] = new_hsv

            self.layer_color_widgets[layer_idx][1].setStyleSheet(
                f"background-color: {color.name()}; border: 1px solid gray;"
            )
            self._update_buttons()

        import sys
        if sys.platform == "emscripten":
            # On web, use non-blocking show() to avoid emscripten_sleep
            dlg.colorSelected.connect(on_color_selected)
            self._color_dialog = dlg  # prevent garbage collection
            dlg.show()
        else:
            if dlg.exec():
                on_color_selected(dlg.selectedColor())

    def on_setting_changed(self):
        if not self.pending_settings:
            return

        cm = ChangeManager.instance()

        # Map setting names to current widget values
        new_values = {
            'left_dpi_index': self.left_dpi.currentIndex(),
            'right_dpi_index': self.right_dpi.currentIndex(),
            'left_scroll': self.left_scroll.isChecked(),
            'right_scroll': self.right_scroll.isChecked(),
            'axis_scroll_lock': self.axis_scroll_lock.isChecked(),
            'natural_scroll': self.natural_scroll.isChecked(),
            'auto_mouse': self.auto_mouse.isChecked(),
            'mh_timer_index': self.mh_timeout.currentIndex(),
            'turbo_scan': self.turbo_scan.currentIndex(),
        }

        # Create individual changes for each setting that changed
        for name, new_value in new_values.items():
            old_value = self.pending_settings.get(name)
            if old_value != new_value:
                change = SvalboardSettingChange(name, old_value, new_value)
                cm.add_change(change)
                self.pending_settings[name] = new_value
                self.keyboard.sval_settings[name] = new_value

        self._update_buttons()

    def _update_buttons(self):
        cm = ChangeManager.instance()

        # Highlight just the frame around modified layer color+number
        for i in range(len(self.layer_color_widgets)):
            is_modified = cm.is_modified(('svalboard_layer_color', i))
            frame, color_btn, label = self.layer_color_widgets[i]
            if is_modified:
                frame.setStyleSheet("#layer_color_frame { border: 2px solid palette(link); }")
            else:
                frame.setStyleSheet("#layer_color_frame { border: 2px solid transparent; }")

        # Highlight individual changed settings widgets
        self._update_settings_highlights()

    def _update_settings_highlights(self):
        """Highlight individual widgets that have uncommitted changes."""
        if not self.pending_settings:
            return

        frame_highlight = "#setting_frame { border: 2px solid palette(link); }"
        frame_normal = "#setting_frame { border: 2px solid transparent; }"
        checkbox_highlight = "border: 2px solid palette(link);"
        checkbox_normal = "border: 2px solid transparent;"

        cm = ChangeManager.instance()

        # Map settings keys to (widget_or_frame, is_frame)
        widget_map = {
            'left_dpi_index': (self.left_dpi_frame, True),
            'right_dpi_index': (self.right_dpi_frame, True),
            'left_scroll': (self.left_scroll, False),
            'right_scroll': (self.right_scroll, False),
            'axis_scroll_lock': (self.axis_scroll_lock, False),
            'natural_scroll': (self.natural_scroll, False),
            'auto_mouse': (self.auto_mouse, False),
            'mh_timer_index': (self.mh_timeout_frame, True),
            'turbo_scan': (self.turbo_scan_frame, True),
        }

        # cm.is_modified() returns False in auto_commit mode
        for setting_name, (widget, is_frame) in widget_map.items():
            if cm.is_modified(('svalboard', setting_name)):
                widget.setStyleSheet(frame_highlight if is_frame else checkbox_highlight)
            else:
                widget.setStyleSheet(frame_normal if is_frame else checkbox_normal)

    def save_state(self):
        """Return current state as a dict for saving to file"""
        if not self.valid():
            return None

        # Save layer colors as list of dicts for readability
        layer_colors = []
        if self.pending_layer_colors:
            for h, s, v in self.pending_layer_colors:
                layer_colors.append({"h": h, "s": s, "v": v})

        return {
            "layer_colors": layer_colors,
            "settings": self.pending_settings.copy() if self.pending_settings else {}
        }

    def restore_state(self, data):
        """Restore state from saved data dict"""
        if not self.valid() or not data:
            return

        self._block_signals()

        cm = ChangeManager.instance()

        # Restore layer colors
        layer_colors = data.get("layer_colors", [])
        if layer_colors and self.pending_layer_colors:
            for i, color_data in enumerate(layer_colors):
                if i < len(self.pending_layer_colors):
                    h = color_data.get("h", 0)
                    s = color_data.get("s", 0)
                    v = color_data.get("v", 0)
                    new_hsv = (h, s, v)
                    old_hsv = self.pending_layer_colors[i]

                    if old_hsv != new_hsv:
                        # Register change with ChangeManager
                        change = SvalboardLayerColorChange(i, old_hsv, new_hsv)
                        cm.add_change(change)
                        self.pending_layer_colors[i] = new_hsv
                        self.keyboard.sval_layer_colors[i] = new_hsv

                    # Update widget display
                    qt_hue = int(h * 359 / 255) if h > 0 else 0
                    color = QColor.fromHsv(qt_hue, s, v)
                    self.layer_color_widgets[i][1].setStyleSheet(
                        f"background-color: {color.name()}; border: 1px solid gray;"
                    )

        # Restore settings - create individual changes for each setting
        settings = data.get("settings", {})
        if settings and self.pending_settings:
            for name, new_value in settings.items():
                old_value = self.pending_settings.get(name)
                if old_value != new_value:
                    change = SvalboardSettingChange(name, old_value, new_value)
                    cm.add_change(change)
                    self.pending_settings[name] = new_value
                    self.keyboard.sval_settings[name] = new_value

            self.left_dpi.setCurrentIndex(settings.get('left_dpi_index', 0))
            self.right_dpi.setCurrentIndex(settings.get('right_dpi_index', 0))
            self.left_scroll.setChecked(settings.get('left_scroll', False))
            self.right_scroll.setChecked(settings.get('right_scroll', False))
            self.axis_scroll_lock.setChecked(settings.get('axis_scroll_lock', False))
            self.natural_scroll.setChecked(settings.get('natural_scroll', False))
            self.auto_mouse.setChecked(settings.get('auto_mouse', False))
            self.mh_timeout.setCurrentIndex(settings.get('mh_timer_index', 0))
            self.turbo_scan.setCurrentIndex(settings.get('turbo_scan', 0))

        self._unblock_signals()

        # Push changes to firmware immediately
        if cm.has_pending_changes():
            cm.save()

        self._update_buttons()

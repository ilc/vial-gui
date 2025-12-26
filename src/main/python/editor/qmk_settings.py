# SPDX-License-Identifier: GPL-2.0-or-later
import json
from collections import defaultdict

from qtpy import QtCore
from qtpy.QtCore import Signal, QObject
from qtpy.QtWidgets import QVBoxLayout, QCheckBox, QGridLayout, QHBoxLayout, QLabel, QWidget, QSizePolicy, QTabWidget, QSpinBox, QFrame

from change_manager import ChangeManager, QmkSettingChange, QmkBitChange
from editor.basic_editor import BasicEditor
from protocol.constants import VIAL_PROTOCOL_QMK_SETTINGS
from vial_device import VialKeyboard


class GenericOption(QObject):

    changed = Signal()

    def __init__(self, option, container):
        super().__init__()

        self.row = container.rowCount()
        self.option = option
        self.qsid = self.option["qsid"]
        self.container = container

        # Create frame to hold label + widget for unified highlighting
        self.frame = QFrame()
        self.frame.setObjectName("option_frame")
        self.frame.setStyleSheet("#option_frame { border: 2px solid transparent; }")
        self.frame_layout = QHBoxLayout()
        self.frame_layout.setContentsMargins(2, 2, 2, 2)
        self.frame_layout.setSpacing(8)
        self.frame.setLayout(self.frame_layout)

        self.lbl = QLabel(option["title"])
        self.frame_layout.addWidget(self.lbl)
        self.frame_layout.addStretch()

        self.container.addWidget(self.frame, self.row, 0, 1, 2)

    def reload(self, keyboard):
        return keyboard.settings.get(self.qsid)

    def delete(self):
        self.frame.hide()
        self.frame.deleteLater()

    def on_change(self):
        self.changed.emit()


class BooleanOption(GenericOption):

    def __init__(self, option, container):
        super().__init__(option, container)

        self.qsid_bit = self.option.get("bit", 0)

        self.checkbox = QCheckBox()
        self.checkbox.stateChanged.connect(self.on_change)
        self.frame_layout.addWidget(self.checkbox)

    def reload(self, keyboard):
        value = super().reload(keyboard)
        checked = value & (1 << self.qsid_bit)

        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(checked != 0)
        self.checkbox.blockSignals(False)

    def bit_value(self):
        """Return 0 or 1 for this bit."""
        return int(self.checkbox.isChecked())

    def change_key(self):
        """Return the ChangeManager key for this option."""
        return ('qmk_setting_bit', self.qsid, self.qsid_bit)

    def set_modified(self, modified):
        if modified:
            self.frame.setStyleSheet("#option_frame { border: 2px solid palette(link); }")
        else:
            self.frame.setStyleSheet("#option_frame { border: 2px solid transparent; }")


class IntegerOption(GenericOption):

    def __init__(self, option, container):
        super().__init__(option, container)

        self.spinbox = QSpinBox()
        self.spinbox.setMinimum(option["min"])
        self.spinbox.setMaximum(option["max"])
        self.spinbox.valueChanged.connect(self.on_change)
        self.frame_layout.addWidget(self.spinbox)

    def reload(self, keyboard):
        value = super().reload(keyboard)
        self.spinbox.blockSignals(True)
        self.spinbox.setValue(value)
        self.spinbox.blockSignals(False)

    def value(self):
        return self.spinbox.value()

    def change_key(self):
        """Return the ChangeManager key for this option."""
        return ('qmk_setting', self.qsid)

    def set_modified(self, modified):
        if modified:
            self.frame.setStyleSheet("#option_frame { border: 2px solid palette(link); }")
        else:
            self.frame.setStyleSheet("#option_frame { border: 2px solid transparent; }")


class QmkSettings(BasicEditor):

    def __init__(self):
        super().__init__()
        self.keyboard = None

        self.tabs_widget = QTabWidget()
        self.addWidget(self.tabs_widget)

        self.tabs = []
        self.misc_widgets = []

    def populate_tab(self, tab, container):
        options = []
        for field in tab["fields"]:
            if field["qsid"] not in self.keyboard.supported_settings:
                continue
            if field["type"] == "boolean":
                opt = BooleanOption(field, container)
                options.append(opt)
                opt.changed.connect(self.on_change)
            elif field["type"] == "integer":
                opt = IntegerOption(field, container)
                options.append(opt)
                opt.changed.connect(self.on_change)
            else:
                raise RuntimeError("unsupported field type: {}".format(field))
        return options

    def recreate_gui(self):
        # delete old GUI
        for tab in self.tabs:
            for field in tab:
                field.delete()
        self.tabs.clear()
        for w in self.misc_widgets:
            w.hide()
            w.deleteLater()
        self.misc_widgets.clear()
        while self.tabs_widget.count() > 0:
            self.tabs_widget.removeTab(0)

        # create new GUI
        for tab in self.settings_defs["tabs"]:
            # don't bother creating tabs that would be empty - i.e. at least one qsid in a tab should be supported
            use_tab = False
            for field in tab["fields"]:
                if field["qsid"] in self.keyboard.supported_settings:
                    use_tab = True
                    break
            if not use_tab:
                continue

            w = QWidget()
            w.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
            container = QGridLayout()
            w.setLayout(container)
            l = QVBoxLayout()
            l.addWidget(w)
            l.setAlignment(w, QtCore.Qt.AlignHCenter)
            w2 = QWidget()
            w2.setLayout(l)
            self.misc_widgets += [w, w2]
            self.tabs_widget.addTab(w2, tab["name"])
            self.tabs.append(self.populate_tab(tab, container))

    def reload_settings(self):
        self.keyboard.reload_settings()
        self.recreate_gui()

        for tab in self.tabs:
            for field in tab:
                field.reload(self.keyboard)

        # Just update UI state, don't track changes (this is initial load)
        self._update_ui_state()

    def on_change(self):
        cm = ChangeManager.instance()

        # Track changes per-option
        for tab in self.tabs:
            for opt in tab:
                if isinstance(opt, BooleanOption):
                    # Per-bit changes for boolean options
                    new_bit = opt.bit_value()
                    current_full = self.keyboard.settings.get(opt.qsid, 0)
                    old_bit = (current_full >> opt.qsid_bit) & 1
                    if old_bit != new_bit:
                        change = QmkBitChange(opt.qsid, opt.qsid_bit, old_bit, new_bit)
                        cm.add_change(change)
                        # Update keyboard state
                        if new_bit:
                            self.keyboard.settings[opt.qsid] = current_full | (1 << opt.qsid_bit)
                        else:
                            self.keyboard.settings[opt.qsid] = current_full & ~(1 << opt.qsid_bit)
                elif isinstance(opt, IntegerOption):
                    # Per-qsid changes for integer options
                    new_value = opt.value()
                    old_value = self.keyboard.settings.get(opt.qsid, 0)
                    if old_value != new_value:
                        change = QmkSettingChange(opt.qsid, old_value, new_value)
                        cm.add_change(change)
                        self.keyboard.settings[opt.qsid] = new_value

        # Update visual state
        self._update_ui_state()

    def _update_ui_state(self):
        """Update UI highlights and button states without tracking changes."""
        # Get link color for highlighting
        from qtpy.QtWidgets import QApplication
        from qtpy.QtGui import QPalette
        link_color = QApplication.palette().color(QPalette.Link)
        default_color = QApplication.palette().color(QPalette.WindowText)

        cm = ChangeManager.instance()

        # Update tab titles and highlight individual changed widgets
        # cm.is_modified() returns False in auto_commit mode
        for x, tab in enumerate(self.tabs):
            tab_changed = False
            for opt in tab:
                is_opt_modified = cm.is_modified(opt.change_key())

                # Highlight the specific widget
                if hasattr(opt, 'set_modified'):
                    opt.set_modified(is_opt_modified)

                if is_opt_modified:
                    tab_changed = True

            if tab_changed:
                self.tabs_widget.tabBar().setTabTextColor(x, link_color)
            else:
                self.tabs_widget.tabBar().setTabTextColor(x, default_color)

        # Force repaint
        self.tabs_widget.tabBar().update()


    def rebuild(self, device):
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard
            # Connect to ChangeManager signals
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
            self.reload_settings()

    def _on_values_restored(self, affected_keys):
        """Refresh UI when settings are restored by undo/redo."""
        affected_qsid = None
        for key in affected_keys:
            if key[0] in ('qmk_setting', 'qmk_setting_bit'):
                affected_qsid = key[1]  # ('qmk_setting', qsid) or ('qmk_setting_bit', qsid, bit)
                break

        if affected_qsid is not None:
            # Reload UI from keyboard.settings
            for tab in self.tabs:
                for field in tab:
                    field.reload(self.keyboard)
            self._update_ui_state()

            # Switch to the tab containing the affected setting
            for tab_idx, tab in enumerate(self.tabs):
                for field in tab:
                    if field.qsid == affected_qsid:
                        self.tabs_widget.setCurrentIndex(tab_idx)
                        return

    def _on_saved(self):
        """Clear highlights after changes are pushed to device."""
        self._update_ui_state()

    def valid(self):
        return isinstance(self.device, VialKeyboard) and \
               (self.device.keyboard and self.device.keyboard.vial_protocol >= VIAL_PROTOCOL_QMK_SETTINGS
                and len(self.device.keyboard.supported_settings))

    @classmethod
    def initialize(cls, appctx):
        cls.qsid_fields = defaultdict(list)
        with open(appctx.get_resource("qmk_settings.json"), "r") as inf:
            cls.settings_defs = json.load(inf)
        for tab in cls.settings_defs["tabs"]:
            for field in tab["fields"]:
                cls.qsid_fields[field["qsid"]].append(field)

    @classmethod
    def is_qsid_supported(cls, qsid):
        """ Return whether this qsid is supported by the settings editor """
        return qsid in cls.qsid_fields

    @classmethod
    def qsid_serialize(cls, qsid, data):
        """ Serialize from internal representation into binary that can be sent to the firmware """
        fields = cls.qsid_fields[qsid]
        if fields[0]["type"] == "boolean":
            assert isinstance(data, int)
            return data.to_bytes(fields[0].get("width", 1), byteorder="little")
        elif fields[0]["type"] == "integer":
            assert isinstance(data, int)
            assert len(fields) == 1
            return data.to_bytes(fields[0]["width"], byteorder="little")

    @classmethod
    def qsid_deserialize(cls, qsid, data):
        """ Deserialize from binary received from firmware into internal representation """
        fields = cls.qsid_fields[qsid]
        if fields[0]["type"] == "boolean":
            return int.from_bytes(data[0:fields[0].get("width", 1)], byteorder="little")
        elif fields[0]["type"] == "integer":
            assert len(fields) == 1
            return int.from_bytes(data[0:fields[0]["width"]], byteorder="little")
        else:
            raise RuntimeError("unsupported field")

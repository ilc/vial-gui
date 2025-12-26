# SPDX-License-Identifier: GPL-2.0-or-later
import logging
import platform
from json import JSONDecodeError

from qtpy.QtCore import Qt, QSettings, QStandardPaths, QTimer, QRect, qVersion
from qtpy.QtGui import QPalette, QIcon, QPixmap, QPainter, QColor, QFont, QAction, QActionGroup
from qtpy.QtWidgets import QWidget, QComboBox, QToolButton, QHBoxLayout, QVBoxLayout, QMainWindow, \
    QFileDialog, QDialog, QTabWidget, QMessageBox, QLabel, QApplication, QSystemTrayIcon

import json
import os
import sys

from about_keyboard import AboutKeyboard
from autorefresh.autorefresh import Autorefresh
from change_manager import ChangeManager
from editor.alt_repeat_key import AltRepeatKey
from editor.combos import Combos
from constants import WINDOW_WIDTH, WINDOW_HEIGHT
from widgets.editor_container import EditorContainer
from editor.firmware_flasher import FirmwareFlasher
from editor.key_override import KeyOverride
from protocol.keyboard_comm import ProtocolError
from editor.keymap_editor import KeymapEditor
from keymaps import KEYMAPS
from editor.layout_editor import LayoutEditor
from editor.macro_recorder import MacroRecorder
from editor.qmk_settings import QmkSettings
from editor.rgb_configurator import RGBConfigurator
from editor.svalboard_editor import SvalboardEditor
from tabbed_keycodes import TabbedKeycodes
from editor.tap_dance import TapDance
from unlocker import Unlocker
from util import tr, EXAMPLE_KEYBOARDS, KeycodeDisplay, EXAMPLE_KEYBOARD_PREFIX
from vial_device import VialKeyboard
from editor.matrix_test import MatrixTest

import themes


class MainWindow(QMainWindow):

    def __init__(self, appctx, initial_tab=None):
        super().__init__()
        self.appctx = appctx
        self.initial_tab = initial_tab

        self.ui_lock_count = 0

        self.settings = QSettings("Vial", "Vial")
        if self.settings.value("size", None):
            self.resize(self.settings.value("size"))
        else:
            self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        _pos = self.settings.value("pos", None)
        # Check if saved position is on a visible screen
        if _pos and qApp.screenAt(_pos) and qApp.screenAt(_pos + self.rect().bottomRight()):
            self.move(self.settings.value("pos"))

        if self.settings.value("maximized", False, bool):
            self.showMaximized()

        themes.Theme.set_theme(self.get_theme())

        self.combobox_devices = QComboBox()
        self.combobox_devices.currentIndexChanged.connect(self.on_device_selected)

        self.btn_refresh_devices = QToolButton()
        self.btn_refresh_devices.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_refresh_devices.setText(tr("MainWindow", "Refresh"))
        self.btn_refresh_devices.clicked.connect(self.on_click_refresh)

        # Import here to avoid circular imports
        from widgets.change_controls import ChangeControls
        self.change_controls = ChangeControls()

        layout_combobox = QHBoxLayout()
        layout_combobox.addWidget(self.combobox_devices)
        if sys.platform != "emscripten":
            layout_combobox.addWidget(self.btn_refresh_devices)
        layout_combobox.addSpacing(20)
        layout_combobox.addWidget(self.change_controls)

        self.layout_editor = LayoutEditor()
        self.keymap_editor = KeymapEditor(self.layout_editor)
        self.firmware_flasher = FirmwareFlasher(self)
        self.macro_recorder = MacroRecorder()
        self.tap_dance = TapDance()
        self.combos = Combos()
        self.key_override = KeyOverride()
        self.alt_repeat_key = AltRepeatKey()
        QmkSettings.initialize(appctx)
        self.qmk_settings = QmkSettings()
        self.matrix_tester = MatrixTest(self.layout_editor)
        self.rgb_configurator = RGBConfigurator()
        self.svalboard_editor = SvalboardEditor()

        self.editors = [(self.keymap_editor, "Keymap"), (self.layout_editor, "Layout"), (self.macro_recorder, "Macros"),
                        (self.rgb_configurator, "Lighting"), (self.tap_dance, "Tap Dance"), (self.combos, "Combos"),
                        (self.key_override, "Key Overrides"), (self.alt_repeat_key, "Alt Repeat Key"),
                        (self.qmk_settings, "QMK Settings"), (self.svalboard_editor, "Svalboard"),
                        (self.matrix_tester, "Matrix tester"), (self.firmware_flasher, "Firmware updater")]

        Unlocker.global_layout_editor = self.layout_editor
        Unlocker.global_main_window = self

        self.current_tab = None
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.refresh_tabs()

        # Connect to ChangeManager to highlight tabs with pending changes
        cm = ChangeManager.instance()
        cm.changed.connect(self._update_tab_colors)

        no_devices = 'No devices detected. Connect a Vial-compatible device and press "Refresh"<br>' \
                     'or select "File" → "Download VIA definitions" in order to enable support for VIA keyboards.'
        if sys.platform.startswith("linux"):
            no_devices += '<br><br>On Linux you need to set up a custom udev rule for keyboards to be detected. ' \
                          'Follow the instructions linked below:<br>' \
                          '<a href="https://get.vial.today/manual/linux-udev.html">https://get.vial.today/manual/linux-udev.html</a>'
        self.lbl_no_devices = QLabel(tr("MainWindow", no_devices))
        self.lbl_no_devices.setTextFormat(Qt.RichText)
        self.lbl_no_devices.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout()
        layout.addLayout(layout_combobox)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.lbl_no_devices)
        layout.setAlignment(self.lbl_no_devices, Qt.AlignHCenter)
        self.tray_keycodes = TabbedKeycodes()
        self.tray_keycodes.make_tray()
        layout.addWidget(self.tray_keycodes, 1)
        self.tray_keycodes.hide()
        w = QWidget()
        w.setLayout(layout)
        self.setCentralWidget(w)

        # System tray icon for layer indicator (not on web)
        # Initialize before init_menu() since menu references tray_icon
        self.tray_icon = None
        self.tray_layer_icons = {}
        self.tray_current_layer = -1
        self.tray_icon_enabled = self.settings.value("tray_icon_enabled", True, bool)
        if sys.platform != "emscripten" and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = QSystemTrayIcon(self)
            self._init_layer_icons()
            # Poll for layer changes every 200ms
            self.layer_poll_timer = QTimer()
            self.layer_poll_timer.timeout.connect(self._poll_layer)
            self.layer_poll_timer.start(200)

        self.init_menu()

        self.autorefresh = Autorefresh()
        self.autorefresh.devices_updated.connect(self.on_devices_updated)

        # Connect to ChangeManager to navigate to affected editor on undo/redo
        ChangeManager.instance().values_restored.connect(self._on_values_restored)

        # cache for via definition files
        self.cache_path = QStandardPaths.writableLocation(QStandardPaths.CacheLocation)
        if not os.path.exists(self.cache_path):
            os.makedirs(self.cache_path)

        # check if the via defitions already exist
        if os.path.isfile(os.path.join(self.cache_path, "via_keyboards.json")):
            with open(os.path.join(self.cache_path, "via_keyboards.json")) as vf:
                data = vf.read()
            try:
                self.autorefresh.load_via_stack(data)
            except JSONDecodeError as e:
                # the saved file is invalid - just ignore this
                logging.warning("Failed to parse stored via_keyboards.json: {}".format(e))

        # make sure initial state is valid
        self.on_click_refresh()

        if sys.platform == "emscripten":
            import vialglue
            QTimer.singleShot(100, vialglue.notify_ready)

    def init_menu(self):
        layout_load_act = QAction(tr("MenuFile", "Load saved layout..."), self)
        layout_load_act.setShortcut("Ctrl+O")
        layout_load_act.triggered.connect(self.on_layout_load)

        layout_save_act = QAction(tr("MenuFile", "Save current layout..."), self)
        layout_save_act.setShortcut("Ctrl+Alt+S")
        layout_save_act.triggered.connect(self.on_layout_save)

        sideload_json_act = QAction(tr("MenuFile", "Sideload VIA JSON..."), self)
        sideload_json_act.triggered.connect(self.on_sideload_json)

        download_via_stack_act = QAction(tr("MenuFile", "Download VIA definitions"), self)
        download_via_stack_act.triggered.connect(self.load_via_stack_json)

        load_dummy_act = QAction(tr("MenuFile", "Load dummy JSON..."), self)
        load_dummy_act.triggered.connect(self.on_load_dummy)

        exit_act = QAction(tr("MenuFile", "Exit"), self)
        exit_act.setShortcut("Ctrl+Q")
        exit_act.triggered.connect(self.close)

        # Svalboard profile save/load (only visible when Svalboard connected)
        self.svalboard_load_act = QAction(tr("MenuFile", "Load Svalboard profile..."), self)
        self.svalboard_load_act.setShortcut("Ctrl+Shift+O")
        self.svalboard_load_act.triggered.connect(self.on_svalboard_load)
        self.svalboard_load_act.setVisible(False)

        self.svalboard_save_act = QAction(tr("MenuFile", "Save Svalboard profile..."), self)
        self.svalboard_save_act.setShortcut("Ctrl+Shift+S")
        self.svalboard_save_act.triggered.connect(self.on_svalboard_save)
        self.svalboard_save_act.setVisible(False)

        file_menu = self.menuBar().addMenu(tr("Menu", "File"))
        file_menu.addAction(layout_load_act)
        file_menu.addAction(layout_save_act)
        file_menu.addSeparator()
        file_menu.addAction(self.svalboard_load_act)
        file_menu.addAction(self.svalboard_save_act)

        if sys.platform != "emscripten":
            file_menu.addSeparator()
            file_menu.addAction(sideload_json_act)
            file_menu.addAction(download_via_stack_act)
            file_menu.addAction(load_dummy_act)
            if self.tray_icon is not None:
                file_menu.addSeparator()
                self.tray_icon_act = QAction(self._tray_icon_label(), self)
                self.tray_icon_act.triggered.connect(self.toggle_tray_icon)
                file_menu.addAction(self.tray_icon_act)
            file_menu.addSeparator()
            file_menu.addAction(exit_act)

        keyboard_unlock_act = QAction(tr("MenuSecurity", "Unlock"), self)
        keyboard_unlock_act.setShortcut("Ctrl+U")
        keyboard_unlock_act.triggered.connect(self.unlock_keyboard)

        keyboard_lock_act = QAction(tr("MenuSecurity", "Lock"), self)
        keyboard_lock_act.setShortcut("Ctrl+L")
        keyboard_lock_act.triggered.connect(self.lock_keyboard)

        keyboard_reset_act = QAction(tr("MenuSecurity", "Reboot to bootloader"), self)
        keyboard_reset_act.setShortcut("Ctrl+B")
        keyboard_reset_act.triggered.connect(self.reboot_to_bootloader)

        keyboard_layout_menu = self.menuBar().addMenu(tr("Menu", "Keyboard layout"))
        keymap_group = QActionGroup(self)
        selected_keymap = self.settings.value("keymap")
        for idx, keymap in enumerate(KEYMAPS):
            act = QAction(tr("KeyboardLayout", keymap[0]), self)
            act.triggered.connect(lambda checked, x=idx: self.change_keyboard_layout(x))
            act.setCheckable(True)
            if selected_keymap == keymap[0]:
                self.change_keyboard_layout(idx)
                act.setChecked(True)
            keymap_group.addAction(act)
            keyboard_layout_menu.addAction(act)
        # check "QWERTY" if nothing else is selected
        if keymap_group.checkedAction() is None:
            keymap_group.actions()[0].setChecked(True)

        self.security_menu = self.menuBar().addMenu(tr("Menu", "Security"))
        self.security_menu.addAction(keyboard_unlock_act)
        self.security_menu.addAction(keyboard_lock_act)
        self.security_menu.addSeparator()
        self.security_menu.addAction(keyboard_reset_act)

        self.theme_menu = self.menuBar().addMenu(tr("Menu", "Theme"))
        theme_group = QActionGroup(self)
        selected_theme = self.get_theme()
        # Skip "System" theme on web since there's no system theme in browser
        theme_list = themes.themes if sys.platform == "emscripten" else [("System", None)] + themes.themes
        for name, _ in theme_list:
            act = QAction(tr("MenuTheme", name), self)
            act.triggered.connect(lambda x,name=name: self.set_theme(name))
            act.setCheckable(True)
            act.setChecked(selected_theme == name)
            theme_group.addAction(act)
            self.theme_menu.addAction(act)
        # check first theme if nothing else is selected
        if theme_group.checkedAction() is None:
            theme_group.actions()[0].setChecked(True)

        about_vial_act = QAction(tr("MenuAbout", "About Vial..."), self)
        about_vial_act.triggered.connect(self.about_vial)
        self.about_keyboard_act = QAction("", self)
        self.about_keyboard_act.triggered.connect(self.about_keyboard)
        self.about_menu = self.menuBar().addMenu(tr("Menu", "About"))
        self.about_menu.addAction(self.about_keyboard_act)
        self.about_menu.addAction(about_vial_act)

    def on_layout_loaded(self, layout):
        """
        Receives a message from the JS bridge when a layout has
        been loaded via the JS File System API.
        Handles both .vil and .svil formats.
        """
        # Try to detect if this is a .svil profile or a .vil layout
        try:
            data = json.loads(layout.decode("utf-8"))
            if data.get("format") == "svil":
                # This is a Svalboard profile
                self._restore_svalboard_profile(layout)
                return
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        # Clear pending changes before loading - file load overwrites everything
        ChangeManager.instance().clear()
        # Standard .vil layout
        self.keymap_editor.restore_layout(layout)
        self.rebuild()

    def on_layout_load(self):
        if sys.platform == "emscripten":
            import vialglue
            # Tells the JS bridge to open a file selection dialog
            # so the user can load a layout.
            vialglue.load_layout()
        else:
            dialog = QFileDialog()
            dialog.setDefaultSuffix("vil")
            dialog.setAcceptMode(QFileDialog.AcceptOpen)
            dialog.setNameFilters(["Vial layout (*.vil)"])
            if dialog.exec() == QDialog.Accepted:
                with open(dialog.selectedFiles()[0], "rb") as inf:
                    data = inf.read()
                # Clear pending changes before loading - file load overwrites everything
                ChangeManager.instance().clear()
                self.keymap_editor.restore_layout(data)
                self.rebuild()

    def on_layout_save(self):
        if sys.platform == "emscripten":
            import vialglue
            layout = self.keymap_editor.save_layout()
            # Passes the current layout to the JS bridge so it can
            # open a file dialog and allow the user to save it to disk.
            vialglue.save_layout(layout)
        else:
            dialog = QFileDialog()
            dialog.setDefaultSuffix("vil")
            dialog.setAcceptMode(QFileDialog.AcceptSave)
            dialog.setNameFilters(["Vial layout (*.vil)"])
            if dialog.exec() == QDialog.Accepted:
                with open(dialog.selectedFiles()[0], "wb") as outf:
                    outf.write(self.keymap_editor.save_layout())

    def on_svalboard_save(self):
        """Save Svalboard profile (.svil) with layout and Svalboard settings"""
        if not self.svalboard_editor.valid():
            return

        # Build the combined profile data
        svalboard_state = self.svalboard_editor.save_state()
        vil_data = json.loads(self.keymap_editor.save_layout().decode("utf-8"))

        profile = {
            "version": 1,
            "format": "svil",
            "protocol_version": self.keymap_editor.keyboard.sval_protocol_version,
            "svalboard": svalboard_state,
            "vil": vil_data
        }

        profile_bytes = json.dumps(profile, indent=2).encode("utf-8")

        if sys.platform == "emscripten":
            import vialglue
            vialglue.save_svalboard_profile(profile_bytes)
        else:
            dialog = QFileDialog()
            dialog.setDefaultSuffix("svil")
            dialog.setAcceptMode(QFileDialog.AcceptSave)
            dialog.setNameFilters(["Svalboard profile (*.svil)"])
            if dialog.exec() == QDialog.Accepted:
                with open(dialog.selectedFiles()[0], "wb") as outf:
                    outf.write(profile_bytes)

    def on_svalboard_load(self):
        """Load Svalboard profile (.svil) with layout and Svalboard settings"""
        if sys.platform == "emscripten":
            import vialglue
            vialglue.load_svalboard_profile()
            # Note: The loaded data will come back through on_layout_loaded
        else:
            dialog = QFileDialog()
            dialog.setDefaultSuffix("svil")
            dialog.setAcceptMode(QFileDialog.AcceptOpen)
            dialog.setNameFilters(["Svalboard profile (*.svil)"])
            if dialog.exec() == QDialog.Accepted:
                with open(dialog.selectedFiles()[0], "rb") as inf:
                    data = inf.read()
                self._restore_svalboard_profile(data)

    def _restore_svalboard_profile(self, data):
        """Restore a Svalboard profile from bytes data"""
        try:
            profile = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            QMessageBox.warning(self, "", f"Failed to parse profile: {e}")
            return

        # Check format
        if profile.get("format") != "svil":
            QMessageBox.warning(self, "", "Invalid Svalboard profile format.")
            return

        # Clear pending changes before loading - don't keep state unrelated to loaded file
        ChangeManager.instance().clear()

        # Check keyboard UID matches
        vil_data = profile.get("vil", {})
        if vil_data.get("uid") != self.keymap_editor.keyboard.keyboard_id:
            ret = QMessageBox.question(
                self, "",
                tr("MainWindow", "Saved profile belongs to a different keyboard, "
                                 "are you sure you want to continue?"),
                QMessageBox.Yes | QMessageBox.No
            )
            if ret != QMessageBox.Yes:
                return

        # Restore the .vil layout data
        vil_bytes = json.dumps(vil_data).encode("utf-8")
        self.keymap_editor.restore_layout(vil_bytes)

        # Restore Svalboard settings
        svalboard_data = profile.get("svalboard", {})
        if svalboard_data:
            self.svalboard_editor.restore_state(svalboard_data)

        # Clear undo/redo stacks - load is a fresh start
        ChangeManager.instance().clear()

        self.rebuild()

    def on_click_refresh(self):
        self.autorefresh.update(quiet=False, hard=True)

    def on_devices_updated(self, devices, hard_refresh):
        self.combobox_devices.blockSignals(True)

        self.combobox_devices.clear()
        for dev in devices:
            self.combobox_devices.addItem(dev.title())
            if self.autorefresh.current_device and dev.desc["path"] == self.autorefresh.current_device.desc["path"]:
                self.combobox_devices.setCurrentIndex(self.combobox_devices.count() - 1)

        self.combobox_devices.blockSignals(False)

        if devices:
            self.lbl_no_devices.hide()
            self.tabs.show()
        else:
            self.lbl_no_devices.show()
            self.tabs.hide()

        if hard_refresh:
            self.on_device_selected()

    def on_device_selected(self):
        # Check for unsaved changes before switching devices
        cm = ChangeManager.instance()
        if cm.has_pending_changes():
            ret = QMessageBox.question(
                self, "",
                tr("MainWindow", "You have unsaved changes. Discard them?"),
                QMessageBox.Yes | QMessageBox.No
            )
            if ret != QMessageBox.Yes:
                return

        try:
            self.autorefresh.select_device(self.combobox_devices.currentIndex())
        except ProtocolError:
            QMessageBox.warning(self, "", "Unsupported protocol version!\n"
                                          "Please download latest Vial from https://get.vial.today/")

        # Set keyboard on ChangeManager
        if isinstance(self.autorefresh.current_device, VialKeyboard):
            cm.set_keyboard(self.autorefresh.current_device.keyboard)
            keyboard_id = self.autorefresh.current_device.keyboard.keyboard_id
            if (keyboard_id in EXAMPLE_KEYBOARDS) or ((keyboard_id & 0xFFFFFFFFFFFFFF) == EXAMPLE_KEYBOARD_PREFIX):
                QMessageBox.warning(self, "", "An example keyboard UID was detected.\n"
                                              "Please change your keyboard UID to be unique before you ship!")
            # Check for newer Svalboard firmware than GUI supports
            keyboard = self.autorefresh.current_device.keyboard
            if hasattr(keyboard, 'sval_protocol_too_new') and keyboard.sval_protocol_too_new:
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Warning)
                msg.setWindowTitle("")
                msg.setText("Your Svalboard firmware is newer than this GUI supports.<br>"
                            "Svalboard features are disabled.<br><br>"
                            "Please update the GUI from "
                            "<a href='https://github.com/svalboard/vial-gui'>github.com/svalboard/vial-gui</a>")
                msg.setTextFormat(Qt.RichText)
                msg.setTextInteractionFlags(Qt.TextBrowserInteraction)
                msg.exec()
        else:
            cm.set_keyboard(None)

        self.rebuild()
        self.refresh_tabs()

    def rebuild(self):
        # don't show "Security" menu for bootloader mode, as the bootloader is inherently insecure
        self.security_menu.menuAction().setVisible(isinstance(self.autorefresh.current_device, VialKeyboard))

        self.about_keyboard_act.setVisible(False)
        if isinstance(self.autorefresh.current_device, VialKeyboard):
            self.about_keyboard_act.setText("About {}...".format(self.autorefresh.current_device.title()))
            self.about_keyboard_act.setVisible(True)

        # if unlock process was interrupted, we must finish it first
        if isinstance(self.autorefresh.current_device, VialKeyboard) and self.autorefresh.current_device.keyboard.get_unlock_in_progress():
            Unlocker.unlock(self.autorefresh.current_device.keyboard)
            self.autorefresh.current_device.keyboard.reload()

        for e in [self.layout_editor, self.keymap_editor, self.firmware_flasher, self.macro_recorder,
                  self.tap_dance, self.combos, self.key_override, self.alt_repeat_key,
                  self.qmk_settings, self.matrix_tester, self.rgb_configurator, self.svalboard_editor]:
            e.rebuild(self.autorefresh.current_device)

        # Show Svalboard profile menu items only when a Svalboard is connected
        # (must be after editors are rebuilt so svalboard_editor.valid() works)
        is_svalboard = self.svalboard_editor.valid()
        self.svalboard_load_act.setVisible(is_svalboard)
        self.svalboard_save_act.setVisible(is_svalboard)

        # Update User tab label to "Svalboard" when Svalboard is connected
        TabbedKeycodes.update_user_tab_label(is_svalboard)

        # Update layer icons from keyboard colors (Svalboard or defaults)
        if self.tray_icon is not None:
            self._update_layer_icons_from_keyboard()
            self.tray_current_layer = -1  # Force icon update on next poll

    def refresh_tabs(self):
        self.tabs.clear()
        for container, lbl in self.editors:
            if not container.valid():
                continue

            c = EditorContainer(container)
            self.tabs.addTab(c, tr("MainWindow", lbl))

        # Switch to initial tab if specified via command line
        if self.initial_tab:
            for i in range(self.tabs.count()):
                if self.tabs.tabText(i) == self.initial_tab:
                    self.tabs.setCurrentIndex(i)
                    break

            # For Svalboard with --matrix-test, automatically select 2S layout
            if self.initial_tab == "Matrix tester" and self.svalboard_editor.valid():
                self.layout_editor.set_option_by_name("2S")

    def _update_tab_colors(self):
        """Update tab text colors based on which editors have pending changes."""
        cm = ChangeManager.instance()
        state = cm._get_state()
        if state is None:
            return

        # Map change key prefixes to editor labels
        editor_prefixes = {
            'Keymap': ('keymap', 'encoder'),
            'Macros': ('macro',),
            'Tap Dance': ('tap_dance',),
            'Combos': ('combo',),
            'Key Overrides': ('key_override',),
            'Alt Repeat Key': ('alt_repeat_key',),
            'QMK Settings': ('qmk_setting',),
            'Svalboard': ('svalboard_settings', 'svalboard_layer_color'),
        }

        # Find which editors have changes
        editors_with_changes = set()
        for key in state.pending.keys():
            prefix = key[0]
            for editor_label, prefixes in editor_prefixes.items():
                if prefix in prefixes:
                    editors_with_changes.add(editor_label)
                    break

        # Update tab colors
        link_color = QApplication.palette().color(QPalette.Link)
        default_color = QApplication.palette().color(QPalette.WindowText)

        for i in range(self.tabs.count()):
            tab_text = self.tabs.tabText(i)
            if tab_text in editors_with_changes:
                self.tabs.tabBar().setTabTextColor(i, link_color)
            else:
                self.tabs.tabBar().setTabTextColor(i, default_color)

    def load_via_stack_json(self):
        from urllib.request import urlopen

        with urlopen("https://github.com/vial-kb/via-keymap-precompiled/raw/main/via_keyboard_stack.json") as resp:
            data = resp.read()
        self.autorefresh.load_via_stack(data)
        # write to cache
        with open(os.path.join(self.cache_path, "via_keyboards.json"), "wb") as cf:
            cf.write(data)

    def on_sideload_json(self):
        dialog = QFileDialog()
        dialog.setDefaultSuffix("json")
        dialog.setAcceptMode(QFileDialog.AcceptOpen)
        dialog.setNameFilters(["VIA layout JSON (*.json)"])
        if dialog.exec() == QDialog.Accepted:
            with open(dialog.selectedFiles()[0], "rb") as inf:
                data = inf.read()
            self.autorefresh.sideload_via_json(data)

    def on_load_dummy(self):
        dialog = QFileDialog()
        dialog.setDefaultSuffix("json")
        dialog.setAcceptMode(QFileDialog.AcceptOpen)
        dialog.setNameFilters(["VIA layout JSON (*.json)"])
        if dialog.exec() == QDialog.Accepted:
            with open(dialog.selectedFiles()[0], "rb") as inf:
                data = inf.read()
            self.autorefresh.load_dummy(data)

    def lock_ui(self):
        self.ui_lock_count += 1
        if self.ui_lock_count == 1:
            self.autorefresh._lock()
            self.tabs.setEnabled(False)
            self.combobox_devices.setEnabled(False)
            self.btn_refresh_devices.setEnabled(False)

    def unlock_ui(self):
        self.ui_lock_count -= 1
        if self.ui_lock_count == 0:
            self.autorefresh._unlock()
            self.tabs.setEnabled(True)
            self.combobox_devices.setEnabled(True)
            self.btn_refresh_devices.setEnabled(True)

    def unlock_keyboard(self):
        if isinstance(self.autorefresh.current_device, VialKeyboard):
            Unlocker.unlock(self.autorefresh.current_device.keyboard)

    def lock_keyboard(self):
        if isinstance(self.autorefresh.current_device, VialKeyboard):
            self.autorefresh.current_device.keyboard.lock()

    def reboot_to_bootloader(self):
        if isinstance(self.autorefresh.current_device, VialKeyboard):
            Unlocker.unlock(self.autorefresh.current_device.keyboard)
            self.autorefresh.current_device.keyboard.reset()

    def change_keyboard_layout(self, index):
        self.settings.setValue("keymap", KEYMAPS[index][0])
        KeycodeDisplay.set_keymap_override(KEYMAPS[index][1])

    def get_theme(self):
        if sys.platform == "emscripten":
            # Theme is loaded from localStorage via JavaScript before app starts
            import webmain
            return webmain._web_theme
        return self.settings.value("theme", "Dark")

    def set_theme(self, theme):
        themes.Theme.set_theme(theme)
        if sys.platform == "emscripten":
            import vialglue
            vialglue.storage_set("theme", theme)
            # On web, use non-blocking show() instead of exec_() to avoid emscripten_sleep
            self.msg_theme = QMessageBox()
            self.msg_theme.setText(tr("MainWindow", "Theme saved. Refresh the page to fully apply."))
            self.msg_theme.setModal(True)
            self.msg_theme.show()
        else:
            self.settings.setValue("theme", theme)
            msg = QMessageBox()
            msg.setText(tr("MainWindow", "In order to fully apply the theme you should restart the application."))
            msg.exec()

    def on_tab_changed(self, index):
        TabbedKeycodes.close_tray()
        old_tab = self.current_tab
        new_tab = None
        if index >= 0:
            new_tab = self.tabs.widget(index)

        if old_tab is not None:
            old_tab.editor.deactivate()
        if new_tab is not None:
            new_tab.editor.activate()

        self.current_tab = new_tab

    def about_vial(self):
        title = "About Vial"
        text = 'Vial {}<br><br>Python {}<br>Qt {}<br><br>' \
               'Licensed under the terms of the<br>GNU General Public License (version 2 or later)<br><br>' \
               '<a href="https://get.vial.today/">https://get.vial.today/</a>' \
               .format(qApp.applicationVersion(),
                       platform.python_version(), qVersion())

        if sys.platform == "emscripten":
            self.msg_about = QMessageBox()
            self.msg_about.setWindowTitle(title)
            self.msg_about.setText(text)
            self.msg_about.setModal(True)
            self.msg_about.show()
        else:
            QMessageBox.about(self, title, text)

    def about_keyboard(self):
        self.about_dialog = AboutKeyboard(self.autorefresh.current_device)
        self.about_dialog.setModal(True)
        self.about_dialog.show()

    def navigate_to_macro(self, macro_index):
        """Navigate to the Macros tab and select the specified macro"""
        # Find the Macros tab
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == "Macros":
                self.tabs.setCurrentIndex(i)
                # Select the macro tab within the macro recorder
                if macro_index < self.macro_recorder.tabs.count():
                    self.macro_recorder.tabs.setCurrentIndex(macro_index)
                break

    def _on_values_restored(self, affected_keys):
        """Navigate to the appropriate editor when undo/redo restores values."""
        if not affected_keys:
            return

        # Map change types to tab names
        type_to_tab = {
            'keymap': 'Keymap',
            'encoder': 'Keymap',
            'macro': 'Macros',
            'tap_dance': 'Tap Dance',
            'combo': 'Combos',
            'key_override': 'Key Overrides',
            'alt_repeat_key': 'Alt Repeat Key',
            'qmk_setting': 'QMK Settings',
            'svalboard_settings': 'Svalboard',
            'svalboard_layer_color': 'Svalboard',
        }

        # Find the first affected change type and switch to that tab
        for key in affected_keys:
            change_type = key[0]
            tab_name = type_to_tab.get(change_type)
            if tab_name:
                for i in range(self.tabs.count()):
                    if self.tabs.tabText(i) == tab_name:
                        self.tabs.setCurrentIndex(i)

                        # For keymap/encoder changes, switch to the affected layer
                        if change_type in ('keymap', 'encoder') and len(key) >= 2:
                            layer = key[1]
                            if layer != self.keymap_editor.current_layer:
                                self.keymap_editor.switch_layer(layer)
                        return

    # Default layer colors (HSV) for non-Svalboard keyboards
    DEFAULT_LAYER_COLORS = [
        (85, 255, 255),   # Green
        (21, 255, 255),   # Orange
        (149, 255, 255),  # Azure
        (11, 176, 255),   # Coral
        (43, 255, 255),   # Yellow
        (128, 255, 128),  # Teal
        (0, 255, 255),    # Red
        (0, 255, 255),    # Red
        (234, 255, 255),  # Pink
        (191, 255, 128),  # Purple
        (11, 176, 255),   # Coral
        (106, 255, 255),  # Spring Green
        (128, 255, 128),  # Teal
        (128, 255, 255),  # Turquoise
        (43, 255, 255),   # Yellow
        (213, 255, 255),  # Magenta
    ]

    def _init_layer_icons(self):
        """Initialize default layer icons using default colors"""
        for layer in range(16):
            h, s, v = self.DEFAULT_LAYER_COLORS[layer]
            self.tray_layer_icons[layer] = self._create_layer_icon(layer, h, s, v)

    def _create_layer_icon(self, layer, h, s, v):
        """Create a 32x32 icon with layer number on colored background"""
        pixmap = QPixmap(32, 32)
        # Convert HSV to RGB
        color = QColor.fromHsv(h, s, v)
        pixmap.fill(color)

        painter = QPainter(pixmap)
        # Use contrasting text color
        brightness = (color.red() * 299 + color.green() * 587 + color.blue() * 114) / 1000
        text_color = Qt.black if brightness > 128 else Qt.white
        painter.setPen(text_color)
        font = QFont()
        font.setPixelSize(20)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, str(layer))
        painter.end()

        return QIcon(pixmap)

    def _update_layer_icons_from_keyboard(self):
        """Update layer icons using colors from connected keyboard"""
        if not isinstance(self.autorefresh.current_device, VialKeyboard):
            return
        keyboard = self.autorefresh.current_device.keyboard
        if hasattr(keyboard, 'sval_layer_colors') and keyboard.sval_layer_colors:
            for layer, (h, s, v) in enumerate(keyboard.sval_layer_colors):
                self.tray_layer_icons[layer] = self._create_layer_icon(layer, h, s, v)

    def _tray_icon_label(self):
        """Get menu label with checkbox indicator"""
        check = "☑ " if self.tray_icon_enabled else "☐ "
        return check + tr("Menu", "Show Tray Icon")

    def toggle_tray_icon(self):
        """Toggle tray icon visibility"""
        self.tray_icon_enabled = not self.tray_icon_enabled
        self.settings.setValue("tray_icon_enabled", self.tray_icon_enabled)
        self.tray_icon_act.setText(self._tray_icon_label())
        if not self.tray_icon_enabled and self.tray_icon is not None:
            self.tray_icon.hide()
            self.tray_current_layer = -1

    def _poll_layer(self):
        """Poll the keyboard for current layer and update tray icon"""
        if self.tray_icon is None or not self.tray_icon_enabled:
            return

        if not isinstance(self.autorefresh.current_device, VialKeyboard):
            # No keyboard connected - hide tray icon
            if self.tray_icon.isVisible():
                self.tray_icon.hide()
            self.tray_current_layer = -1
            return

        keyboard = self.autorefresh.current_device.keyboard
        if not hasattr(keyboard, 'sval_get_current_layer'):
            # Keyboard doesn't support layer query
            if self.tray_icon.isVisible():
                self.tray_icon.hide()
            return

        layer = keyboard.sval_get_current_layer()
        if layer is None:
            return

        if layer != self.tray_current_layer:
            self.tray_current_layer = layer
            if layer in self.tray_layer_icons:
                self.tray_icon.setIcon(self.tray_layer_icons[layer])
                self.tray_icon.setToolTip("Layer {}".format(layer))
            if not self.tray_icon.isVisible():
                self.tray_icon.show()

    def closeEvent(self, e):
        # Check for unsaved changes before closing
        cm = ChangeManager.instance()
        if cm.has_pending_changes():
            ret = QMessageBox.question(
                self, "",
                tr("MainWindow", "You have unsaved changes. Discard them and close?"),
                QMessageBox.Yes | QMessageBox.No
            )
            if ret != QMessageBox.Yes:
                e.ignore()
                return

        # Hide tray icon on close
        if self.tray_icon is not None:
            self.tray_icon.hide()

        self.settings.setValue("size", self.size())
        self.settings.setValue("pos", self.pos())
        self.settings.setValue("maximized", self.isMaximized())

        # Stop autorefresh thread before closing to prevent crash on exit
        self.autorefresh.thread.stop()

        e.accept()

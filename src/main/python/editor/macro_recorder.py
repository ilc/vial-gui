# SPDX-License-Identifier: GPL-2.0-or-later
import sys

from qtpy.QtWidgets import QHBoxLayout, QWidget, QLabel

from change_manager import ChangeManager, MacroChange
from editor.basic_editor import BasicEditor
from macro.macro_action import ActionText, ActionTap, ActionDown, ActionUp
from macro.macro_action_ui import ui_action
from macro.macro_key import KeyString, KeyDown, KeyUp, KeyTap
from macro.macro_optimizer import macro_optimize
from macro.macro_tab import MacroTab
from vial_device import VialKeyboard
from widgets.tab_widget_keycodes import TabWidgetWithKeycodes


class MacroRecorder(BasicEditor):

    def __init__(self):
        super().__init__()

        self.keyboard = None
        self.suppress_change = False

        self.keystrokes = []
        self.macro_tabs = []
        self.macro_tab_w = []

        self.recorder = None

        if sys.platform.startswith("linux"):
            from macro.macro_recorder_linux import LinuxRecorder

            self.recorder = LinuxRecorder()
        elif sys.platform.startswith("win"):
            from macro.macro_recorder_windows import WindowsRecorder

            self.recorder = WindowsRecorder()

        if self.recorder:
            self.recorder.keystroke.connect(self.on_keystroke)
            self.recorder.stopped.connect(self.on_stop)
        self.recording = False

        self.recording_tab = None
        self.recording_append = False

        self.tabs = TabWidgetWithKeycodes()
        # Reserve space for highlight border to prevent layout jump
        self.tabs.setStyleSheet("QTabWidget::pane { border: 2px solid transparent; }")

        self.lbl_memory = QLabel()

        # Memory usage label - Save/Undo handled by global toolbar
        buttons = QHBoxLayout()
        buttons.addWidget(self.lbl_memory)
        buttons.addStretch()

        self.addWidget(self.tabs)
        self.addLayout(buttons)

    def valid(self):
        return isinstance(self.device, VialKeyboard)

    def rebuild(self, device):
        super().rebuild(device)
        if not self.valid():
            return
        self.keyboard = self.device.keyboard

        for x in range(self.keyboard.macro_count - len(self.macro_tab_w)):
            tab = MacroTab(self, self.recorder is not None)
            tab.changed.connect(self.on_change)
            tab.record.connect(self.on_record)
            tab.record_stop.connect(self.on_tab_stop)
            self.macro_tabs.append(tab)
            w = QWidget()
            w.setLayout(tab)
            self.macro_tab_w.append(w)

        # only show the number of macro editors that keyboard supports
        while self.tabs.count() > 0:
            self.tabs.removeTab(0)
        for x, w in enumerate(self.macro_tab_w[:self.keyboard.macro_count]):
            self.tabs.addTab(w, "")

        # deserialize macros that came from keyboard
        self.deserialize(self.keyboard.macro)

        self.on_change()

    def update_tab_titles(self):
        any_modified = False

        # Get the link color for highlighting
        from qtpy.QtWidgets import QApplication
        from qtpy.QtGui import QPalette
        link_color = QApplication.palette().color(QPalette.Link)
        default_color = QApplication.palette().color(QPalette.WindowText)

        cm = ChangeManager.instance()

        # cm.is_modified() returns False in auto_commit mode
        for x in range(self.keyboard.macro_count):
            is_modified = cm.is_modified(('macro', x))
            if is_modified:
                any_modified = True
                self.tabs.tabBar().setTabTextColor(x, link_color)
            else:
                self.tabs.tabBar().setTabTextColor(x, default_color)
            self.tabs.setTabText(x, "M{}".format(x))

        # Force repaint
        self.tabs.tabBar().update()

        # Visual indicator for uncommitted changes on the pane border
        if any_modified:
            self.tabs.setStyleSheet("QTabWidget::pane { border: 2px solid palette(link); }")
        else:
            self.tabs.setStyleSheet("QTabWidget::pane { border: 2px solid transparent; }")

    def on_record(self, tab, append):
        self.recording_tab = tab
        self.recording_append = append

        self.recording_tab.pre_record()

        for x, w in enumerate(self.macro_tabs[:self.keyboard.macro_count]):
            if tab != w:
                self.tabs.tabBar().setTabEnabled(x, False)

        self.recording = True
        self.keystrokes = []
        self.recorder.start()

    def on_tab_stop(self):
        self.recorder.stop()

    def on_stop(self):
        for x in range(self.keyboard.macro_count):
            self.tabs.tabBar().setTabEnabled(x, True)

        if not self.recording_append:
            self.recording_tab.clear()

        self.recording_tab.post_record()

        self.keystrokes = macro_optimize(self.keystrokes)
        actions = []
        for k in self.keystrokes:
            if isinstance(k, KeyString):
                actions.append(ActionText(k.string))
            else:
                cls = {KeyDown: ActionDown, KeyUp: ActionUp, KeyTap: ActionTap}[type(k)]
                actions.append(cls([k.keycode.qmk_id]))

        # merge: i.e. replace multiple instances of KeyDown with a single multi-key ActionDown, etc
        actions = self.keyboard.macro_deserialize(self.keyboard.macro_serialize(actions))
        for act in actions:
            self.recording_tab.add_action(ui_action[type(act)](self.recording_tab.container, act))

    def on_keystroke(self, keystroke):
        self.keystrokes.append(keystroke)

    def on_change(self):
        if self.suppress_change:
            return

        data = self.serialize()
        memory = len(data)

        if memory <= self.keyboard.macro_memory:
            # Compare each macro to find which ones changed
            old_macros = self.keyboard.macro.split(b'\x00')
            new_macros = data.split(b'\x00')
            cm = ChangeManager.instance()

            for idx in range(self.keyboard.macro_count):
                old_macro = old_macros[idx] if idx < len(old_macros) else b''
                new_macro = new_macros[idx] if idx < len(new_macros) else b''
                if old_macro != new_macro:
                    change = MacroChange(idx, old_macro, new_macro)
                    cm.add_change(change)

            # Update local state
            self.keyboard.macro = data

        self.lbl_memory.setText("Memory used by macros: {}/{}".format(memory, self.keyboard.macro_memory))
        self.lbl_memory.setStyleSheet("QLabel { color: red; }" if memory > self.keyboard.macro_memory else "")
        self.update_tab_titles()

    def serialize(self):
        macros = []
        for x, t in enumerate(self.macro_tabs[:self.keyboard.macro_count]):
            macros.append(t.actions())
        return self.keyboard.macros_serialize(macros)

    def deserialize(self, data):
        self.suppress_change = True
        macros = self.keyboard.macros_deserialize(data)
        for macro, tab in zip(macros, self.macro_tabs[:self.keyboard.macro_count]):
            tab.clear()
            for act in macro:
                tab.add_action(ui_action[type(act)](tab.container, act))
        self.suppress_change = False

    def _on_values_restored(self, affected_keys):
        """Refresh UI when macro values are restored by undo/redo."""
        for key in affected_keys:
            if key[0] == 'macro':
                self.deserialize(self.keyboard.macro)
                self.update_tab_titles()
                return

    def _on_saved(self):
        """Refresh highlighting after changes are pushed."""
        self.update_tab_titles()

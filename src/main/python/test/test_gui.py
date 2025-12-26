import lzma
import os.path
import struct

import pytest
from qtpy.QtCore import QPoint
from qtpy.QtWidgets import QPushButton
from pytestqt.qt_compat import qt_api

from change_manager import ChangeManager
from main_window import MainWindow



from protocol.constants import CMD_VIA_GET_PROTOCOL_VERSION, CMD_VIA_VIAL_PREFIX, CMD_VIAL_GET_KEYBOARD_ID, \
    CMD_VIAL_GET_SIZE, CMD_VIAL_GET_DEFINITION, CMD_VIA_GET_LAYER_COUNT, CMD_VIA_MACRO_GET_COUNT, \
    CMD_VIA_MACRO_GET_BUFFER_SIZE, CMD_VIAL_QMK_SETTINGS_QUERY, CMD_VIAL_DYNAMIC_ENTRY_OP, \
    DYNAMIC_VIAL_GET_NUMBER_OF_ENTRIES, CMD_VIA_KEYMAP_GET_BUFFER, CMD_VIA_MACRO_GET_BUFFER, CMD_VIAL_GET_UNLOCK_STATUS, \
    CMD_VIA_SET_KEYCODE, DYNAMIC_VIAL_COMBO_GET, DYNAMIC_VIAL_COMBO_SET, DYNAMIC_VIAL_TAP_DANCE_GET, \
    DYNAMIC_VIAL_TAP_DANCE_SET
from widgets.square_button import SquareButton

FAKE_KEYBOARD = """
{
  "matrix": {
    "rows": 2,
    "cols": 2
  },
  "layouts": {
    "keymap": [
      [
        "0,0",
        "0,1"
      ],
      [
        "1,0",
        "1,1"
      ]
    ]
  }
}
"""


def mock_enumerate():
    return [{
        "vendor_id": 0xDEAD,
        "product_id": 0xBEEF,
        "serial_number": "vial:f64c2b3c",
        "usage_page": 0xFF60,
        "usage": 0x61,
        "path": "/magic/path/for/tests",
        "manufacturer_string": "Vial Testing Ltd",
        "product_string": "Test Keyboard",
    }]


class VirtualKeyboard:

    def __init__(self, kbjson, combos=None, tap_dance=None):
        if combos is None:
            combos = []
        if tap_dance is None:
            tap_dance = []

        self.keyboard_definition = lzma.compress(kbjson.encode("utf-8"))

        self.rows = 2
        self.cols = 2
        self.layers = 4
        self.keymap = []
        for layer in range(self.layers):
            self.keymap.append([])
            for row in range(self.rows):
                self.keymap[-1].append([0 for x in range(self.cols)])

        self.macro_count = 8
        self.macro_buffer = b"\x00" * 512

        self.combos = combos
        self.tap_dance = tap_dance

        self.key_override_entries = 0
        self.alt_repeat_key_entries = 0

    def get_keymap_buffer(self):
        output = b""
        for layer in range(self.layers):
            for row in range(self.rows):
                for col in range(self.cols):
                    output += struct.pack(">H", self.keymap[layer][row][col])
        return output

    def vial_cmd_dynamic(self, msg):
        if msg[2] == DYNAMIC_VIAL_GET_NUMBER_OF_ENTRIES:
            response = struct.pack("BBBB", len(self.tap_dance), len(self.combos),
                                   self.key_override_entries, self.alt_repeat_key_entries)
            # Zero pad to 31 bytes.
            response += (31 - len(response)) * b'\0'
            # Set last two bits, indicating Caps Word and Layer Lock.
            response += (0b00000011).to_bytes(1, "little")
            return response
        elif msg[2] == DYNAMIC_VIAL_COMBO_GET:
            idx = msg[3]
            assert idx < len(self.combos)
            return struct.pack("<BHHHHH", 0, *self.combos[idx])
        elif msg[2] == DYNAMIC_VIAL_COMBO_SET:
            idx = msg[3]
            keys = struct.unpack_from("<HHHHH", msg[4:])
            assert idx < len(self.combos)
            self.combos[idx] = keys
            return b""
        elif msg[2] == DYNAMIC_VIAL_TAP_DANCE_GET:
            idx = msg[3]
            assert idx < len(self.tap_dance)
            return struct.pack("<BHHHHH", 0, *self.tap_dance[idx])
        elif msg[2] == DYNAMIC_VIAL_TAP_DANCE_SET:
            idx = msg[3]
            values = struct.unpack_from("<HHHHH", msg[4:])
            assert idx < len(self.tap_dance)
            self.tap_dance[idx] = values
            return b""
        raise RuntimeError("unsupported dynamic submsg 0x{:02X}".format(msg[2]))

    def vial_cmd(self, msg):
        if msg[1] == CMD_VIAL_GET_KEYBOARD_ID:
            return struct.pack("<IQ", 6, 0xF00DFACEDEADBEEF)
        elif msg[1] == CMD_VIAL_GET_SIZE:
            return struct.pack("<I", len(self.keyboard_definition))
        elif msg[1] == CMD_VIAL_GET_DEFINITION:
            page = struct.unpack_from("<H", msg[2:])[0]
            return self.keyboard_definition[page*32:(page+1)*32]
        elif msg[1] == CMD_VIAL_GET_UNLOCK_STATUS:
            return struct.pack("<BB", 0, 0)  # TODO we want to test unlocking as well
        elif msg[1] == CMD_VIAL_QMK_SETTINGS_QUERY:
            return b"\xFF" * 32
        elif msg[1] == CMD_VIAL_DYNAMIC_ENTRY_OP:
            return self.vial_cmd_dynamic(msg)
        raise RuntimeError("unknown command for Vial protocol 0x{:02X}".format(msg[1]))

    def process(self, msg):
        if msg[0] == CMD_VIA_VIAL_PREFIX:
            return self.vial_cmd(msg)
        elif msg[0] == CMD_VIA_GET_PROTOCOL_VERSION:
            return struct.pack(">BH", msg[0], 9)
        elif msg[0] == CMD_VIA_SET_KEYCODE:
            layer, row, col, kc = struct.unpack_from(">BBBH", msg[1:])
            self.keymap[layer][row][col] = kc
            return b""
        elif msg[0] == CMD_VIA_MACRO_GET_COUNT:
            return struct.pack(">BB", msg[0], self.macro_count)
        elif msg[0] == CMD_VIA_MACRO_GET_BUFFER_SIZE:
            return struct.pack(">BH", msg[0], len(self.macro_buffer))
        elif msg[0] == CMD_VIA_MACRO_GET_BUFFER:
            offset, size = struct.unpack_from(">HB", msg[1:])
            return msg[0:1] + self.macro_buffer[offset:offset+size]
        elif msg[0] == CMD_VIA_GET_LAYER_COUNT:
            return struct.pack(">BB", msg[0], self.layers)
        elif msg[0] == CMD_VIA_KEYMAP_GET_BUFFER:
            offset, size = struct.unpack_from(">HB", msg[1:])
            return msg[0:1] + self.get_keymap_buffer()[offset:offset+size]
        raise RuntimeError("unknown command for VIA protocol 0x{:02X}".format(msg[0]))


class MockDevice:

    def open_path(self, path):
        assert path == "/magic/path/for/tests"

    def close(self):
        pass

    def write(self, data):
        assert len(data) == 33
        assert data[0] == 0
        self.msg = data[1:]

        return len(data)

    def read(self, sz, timeout_ms=None):
        assert sz == 32
        resp = self.vk.process(self.msg)
        assert len(resp) <= 32
        resp += b"\x00" * (32 - len(resp))
        return resp


class FakeAppctx:

    def get_resource(self, path):
        return os.path.join(os.path.dirname(os.path.realpath(__file__)), "../../resources/base/", path)


all_mw = []


@pytest.fixture(autouse=True)
def cleanup_threads():
    """Stop all autorefresh threads after each test."""
    yield
    # Stop and remove all MainWindow threads created during this test
    while all_mw:
        mw = all_mw.pop()
        if hasattr(mw, 'autorefresh') and hasattr(mw.autorefresh, 'thread'):
            mw.autorefresh.thread.stop()


def prepare(qtbot, keyboard_json, combos=None, tap_dance=None):
    import hidraw as hid

    vk = VirtualKeyboard(keyboard_json, combos=combos, tap_dance=tap_dance)
    MockDevice.vk = vk

    hid.enumerate = mock_enumerate
    hid.device = MockDevice

    # Reset ChangeManager state before creating window
    ChangeManager.reset()

    mw = MainWindow(FakeAppctx())

    # Enable auto_commit so keycode changes are immediately sent to the device
    # This matches the old behavior before ChangeManager integration
    ChangeManager.instance().auto_commit = True

    # Patch closeEvent to clear ChangeManager before checking for pending changes
    # This prevents the "unsaved changes" dialog from appearing during test cleanup
    original_close_event = mw.closeEvent
    def patched_close_event(e):
        ChangeManager.instance().clear()
        original_close_event(e)
    mw.closeEvent = patched_close_event

    original_on_device_selected = mw.on_device_selected
    def patched_on_device_selected():
        ChangeManager.instance().clear()
        original_on_device_selected()
    mw.on_device_selected = patched_on_device_selected

    qtbot.addWidget(mw)
    mw.show()
    # keep reference to MainWindow for the duration of tests
    # when MainWindow goes out of scope some KeyWidgets are still registered within KeycodeDisplay which causes UaF
    all_mw.append(mw)

    return mw, vk


def test_gui_startup(qtbot):
    mw, vk = prepare(qtbot, FAKE_KEYBOARD)
    assert mw.combobox_devices.currentText() == "Vial Testing Ltd Test Keyboard"
    assert mw.combobox_devices.count() == 1


def test_about_keyboard(qtbot):
    mw, vk = prepare(qtbot, FAKE_KEYBOARD)

    mw.about_menu.actions()[0].trigger()
    assert mw.about_dialog.windowTitle() == "About Vial Testing Ltd Test Keyboard"
    assert mw.about_dialog.textarea.toPlainText() == ('Manufacturer: Vial Testing Ltd\n'
         'Product: Test Keyboard\n'
         'VID: DEAD\n'
         'PID: BEEF\n'
         'Device: /magic/path/for/tests\n'
         '\n'
         'VIA protocol: 9\n'
         'Vial protocol: 6\n'
         'Vial keyboard ID: F00DFACEDEADBEEF\n'
         '\n'
         'Macro entries: 8\n'
         'Macro memory: 512 bytes\n'
         'Macro delays: yes\n'
         'Complex (2-byte) macro keycodes: yes\n'
         '\n'
         'Tap Dance entries: unsupported - disabled in firmware\n'
         'Combo entries: unsupported - disabled in firmware\n'
         'Key Override entries: unsupported - disabled in firmware\n'
         'Alt Repeat Key entries: unsupported - disabled in firmware\n'
         'Caps Word: yes\n'
         'Layer Lock: yes\n'
         '\n'
         'QMK Settings: disabled in firmware\n')
    mw.about_dialog.accept()


def test_key_change(qtbot):
    """ Tests changing keys in a keymap """
    mw, vk = prepare(qtbot, FAKE_KEYBOARD)

    # nothing should be selected yet in the keyboard display
    assert mw.keymap_editor.container.active_key is None

    # initial keycode must be KC_NO
    assert vk.keymap[0][0][0] == 0

    # clicking on first key must activate it
    point = mw.keymap_editor.container.widgets[0].bbox[0]
    qtbot.mouseClick(mw.keymap_editor.container, qt_api.QtCore.Qt.MouseButton.LeftButton,
                     pos=QPoint(int(point.x()), int(point.y())))

    assert mw.keymap_editor.container.active_key == mw.keymap_editor.container.widgets[0]

    ak = mw.keymap_editor.tabbed_keycodes.all_keycodes
    bk = mw.keymap_editor.tabbed_keycodes.basic_keycodes

    # at this point we can select all keycodes so basic should be hidden
    assert ak.isVisible()
    assert not bk.isVisible()

    def find_key_btn(start, text):
        for w in start.findChildren(SquareButton):
            if w.isVisible() and w.text == text:
                return w
        raise RuntimeError("cannot find a visible key button with text='{}'".format(text))

    # change current key to B
    assert ak.tab_widget.currentIndex() == 0
    assert ak.tab_widget.tabText(ak.tab_widget.currentIndex()) == "Basic"
    btn = find_key_btn(ak, "B")
    qtbot.mouseClick(btn, qt_api.QtCore.Qt.MouseButton.LeftButton)

    # check the new keycode is KC_B
    assert vk.keymap[0][0][0] == 5

    # check that we moved to the next key after setting the first key
    assert mw.keymap_editor.container.active_key == mw.keymap_editor.container.widgets[1]

    # Enable Ctrl modifier in ModsBar, then click C to get LCTL(KC_C)
    ctrl_btn = ak.mods_bar.mod_buttons['ctrl']
    qtbot.mouseClick(ctrl_btn, qt_api.QtCore.Qt.MouseButton.LeftButton)
    assert ak.mods_bar.mods['ctrl']

    # click C to set LCTL(KC_C)
    btn = find_key_btn(ak, "C")
    qtbot.mouseClick(btn, qt_api.QtCore.Qt.MouseButton.LeftButton)

    # check the new keycode is LCTL(KC_C) = 0x106
    assert vk.keymap[0][0][1] == 0x106

    # check that we moved to the next key after setting the second key
    assert mw.keymap_editor.container.active_key == mw.keymap_editor.container.widgets[2]

    # Disable Ctrl modifier
    qtbot.mouseClick(ctrl_btn, qt_api.QtCore.Qt.MouseButton.LeftButton)
    assert not ak.mods_bar.mods['ctrl']

    # set third key to D (unmodified)
    btn = find_key_btn(ak, "D")
    qtbot.mouseClick(btn, qt_api.QtCore.Qt.MouseButton.LeftButton)

    # check the new keycode is KC_D = 7
    assert vk.keymap[0][1][0] == 7

    # check that we moved to the fourth key
    assert mw.keymap_editor.container.active_key == mw.keymap_editor.container.widgets[3]


def test_keymap_zoom(qtbot):
    """ Tests zooming keymap in/out using +/- keys """
    mw, vk = prepare(qtbot, FAKE_KEYBOARD)

    btn_plus = mw.keymap_editor.layout_size.itemAt(0).widget()
    btn_minus = mw.keymap_editor.layout_size.itemAt(1).widget()
    # TODO: resolve this field collision, +/- are SquareButton which overrides text
    assert QPushButton.text(btn_plus) == "+"
    assert QPushButton.text(btn_minus) == "-"

    # grab area for first widget
    scale_initial = mw.keymap_editor.container.scale

    # click the plus button
    qtbot.mouseClick(btn_plus, qt_api.QtCore.Qt.MouseButton.LeftButton)
    # area got bigger
    assert mw.keymap_editor.container.scale > scale_initial

    # click the minus button
    qtbot.mouseClick(btn_minus, qt_api.QtCore.Qt.MouseButton.LeftButton)
    # area back to the initial
    assert abs(mw.keymap_editor.container.scale - scale_initial) < 0.01

    # click the minus button
    qtbot.mouseClick(btn_minus, qt_api.QtCore.Qt.MouseButton.LeftButton)
    # area got smaller
    assert mw.keymap_editor.container.scale < scale_initial


def find_key_btn(start, text):
    for w in start.findChildren(SquareButton):
        if w.isVisible() and w.text == text:
            return w
    raise RuntimeError("cannot find a visible key button with text='{}'".format(text))


def test_layer_switch(qtbot):
    """ Tests setting keycodes across different layers """
    mw, vk = prepare(qtbot, FAKE_KEYBOARD)

    ak = mw.keymap_editor.tabbed_keycodes.all_keycodes
    bk = mw.keymap_editor.tabbed_keycodes.basic_keycodes
    c = mw.keymap_editor.container

    # initial keycode must be KC_NO
    assert vk.keymap[0][0][0] == 0

    # clicking on first key must activate it
    point = c.widgets[0].bbox[0]
    qtbot.mouseClick(c, qt_api.QtCore.Qt.MouseButton.LeftButton,
                     pos=QPoint(int(point.x()), int(point.y())))
    assert c.active_key == c.widgets[0]

    # change current key to Z
    qtbot.mouseClick(find_key_btn(ak, "Z"), qt_api.QtCore.Qt.MouseButton.LeftButton)
    assert vk.keymap[0][0][0] == 0x1D
    assert vk.keymap[1][0][0] == 0

    # make sure display for the widget now says Z
    assert c.widgets[0].text == "Z"
    # and that the next key is selected
    assert c.active_key == c.widgets[1]
    assert not c.active_mask

    # go to layer 1
    btn_layer_0 = mw.keymap_editor.layer_buttons[0]
    btn_layer_1 = mw.keymap_editor.layer_buttons[1]
    # TODO: resolve this field collision, +/- are SquareButton which overrides text
    assert QPushButton.text(btn_layer_0) == "0"
    assert QPushButton.text(btn_layer_1) == "1"

    qtbot.mouseClick(btn_layer_1, qt_api.QtCore.Qt.MouseButton.LeftButton)
    # check the current key got deselected
    assert c.active_key is None
    assert not c.active_mask

    # check the widget now displays layer 1 data, i.e. empty string as it's not set yet
    assert c.widgets[0].text == ""

    # click the key again
    qtbot.mouseClick(c, qt_api.QtCore.Qt.MouseButton.LeftButton,
                     pos=QPoint(int(point.x()), int(point.y())))
    assert c.active_key == c.widgets[0]

    # change current key to Y
    qtbot.mouseClick(find_key_btn(ak, "Y"), qt_api.QtCore.Qt.MouseButton.LeftButton)
    assert vk.keymap[0][0][0] == 0x1D
    assert vk.keymap[1][0][0] == 0x1C

    # make sure display for the widget now says Y
    assert c.widgets[0].text == "Y"

    # go back to the layer 0 and make sure the button got redrawn to Z
    qtbot.mouseClick(btn_layer_0, qt_api.QtCore.Qt.MouseButton.LeftButton)
    assert c.widgets[0].text == "Z"


def test_combos(qtbot):
    """ Tests combo loading and display """
    mw, vk = prepare(qtbot, FAKE_KEYBOARD, combos=[[0, 0, 0, 0, 0], [4, 5, 6, 7, 8], [0, 0x106, 0, 0, 0]])

    combos = None
    for x in range(mw.tabs.count()):
        if mw.tabs.tabText(x) == "Combos":
            combos = mw.tabs.widget(x).editor

    assert combos is not None, "could not find the combos tab"

    # New UI uses combo_entries list with FlowLayout
    assert len(combos.combo_entries) == 3

    def check_entry(idx, keys):
        entry = combos.combo_entries[idx]
        for x in range(4):
            assert entry.kc_inputs[x].keycode == keys[x], \
                f"unexpected keycode at entry {idx} input {x}: {entry.kc_inputs[x].keycode} vs {keys[x]}"
        assert entry.kc_output.keycode == keys[4], \
            f"unexpected output keycode at entry {idx}: {entry.kc_output.keycode} vs {keys[4]}"

    check_entry(0, ["KC_NO", "KC_NO", "KC_NO", "KC_NO", "KC_NO"])
    check_entry(1, ["KC_A", "KC_B", "KC_C", "KC_D", "KC_E"])
    check_entry(2, ["KC_NO", "LCTL(KC_C)", "KC_NO", "KC_NO", "KC_NO"])

    # Test modifying a combo key via click interaction
    entry2 = combos.combo_entries[2]
    kc_widget = entry2.kc_inputs[0]  # First input key

    # Click on key widget to open tray
    bbox = kc_widget.widgets[0].bbox
    pos = QPoint(int(bbox[0].x()), int(bbox[0].y()))
    qtbot.mouseClick(kc_widget, qt_api.QtCore.Qt.MouseButton.LeftButton, pos=pos)
    assert mw.tray_keycodes.isVisible()

    # Set to "A"
    qtbot.mouseClick(find_key_btn(mw.tray_keycodes, "A"), qt_api.QtCore.Qt.MouseButton.LeftButton)
    assert vk.combos[2] == (4, 0x106, 0, 0, 0)

    # Test modifier + key using ModsBar
    ak = mw.tray_keycodes.all_keycodes
    kc_widget = entry2.kc_inputs[2]  # Third input key
    bbox = kc_widget.widgets[0].bbox
    pos = QPoint(int(bbox[0].x()), int(bbox[0].y()))
    qtbot.mouseClick(kc_widget, qt_api.QtCore.Qt.MouseButton.LeftButton, pos=pos)

    # Enable Shift modifier and click D to get LSFT(KC_D)
    shift_btn = ak.mods_bar.mod_buttons['shift']
    qtbot.mouseClick(shift_btn, qt_api.QtCore.Qt.MouseButton.LeftButton)
    qtbot.mouseClick(find_key_btn(mw.tray_keycodes, "D"), qt_api.QtCore.Qt.MouseButton.LeftButton)
    assert vk.combos[2] == (4, 0x106, 0x207, 0, 0)  # Third key is now LSFT(KC_D)

    # Disable shift
    qtbot.mouseClick(shift_btn, qt_api.QtCore.Qt.MouseButton.LeftButton)


def test_tap_dance(qtbot):
    """ Tests tap dance loading and display """
    mw, vk = prepare(qtbot, FAKE_KEYBOARD, tap_dance=[[0, 0, 0, 0, 200], [4, 5, 6, 7, 200], [0, 0x106, 0, 0, 500]])

    tde = None
    for x in range(mw.tabs.count()):
        if mw.tabs.tabText(x) == "Tap Dance":
            tde = mw.tabs.widget(x).editor

    assert tde is not None, "could not find the tap dance tab"

    # New UI uses tap_dance_entries list with FlowLayout
    assert len(tde.tap_dance_entries) == 3

    def check_entry(idx, keys, timeout):
        entry = tde.tap_dance_entries[idx]
        key_widgets = [entry.kc_on_tap, entry.kc_on_hold, entry.kc_on_double_tap, entry.kc_on_tap_hold]
        for x, kw in enumerate(key_widgets):
            assert kw.keycode == keys[x], \
                f"unexpected keycode at entry {idx} position {x}: {kw.keycode} vs {keys[x]}"
        assert entry.txt_tapping_term.value() == timeout, \
            f"unexpected timeout at entry {idx}: {entry.txt_tapping_term.value()} vs {timeout}"

    check_entry(0, ["KC_NO", "KC_NO", "KC_NO", "KC_NO"], 200)
    check_entry(1, ["KC_A", "KC_B", "KC_C", "KC_D"], 200)
    check_entry(2, ["KC_NO", "LCTL(KC_C)", "KC_NO", "KC_NO"], 500)

    # Test modifying a tap dance key via click interaction
    entry2 = tde.tap_dance_entries[2]
    kc_widget = entry2.kc_on_tap  # Tap key

    # Click on key widget to open tray
    bbox = kc_widget.widgets[0].bbox
    pos = QPoint(int(bbox[0].x()), int(bbox[0].y()))
    qtbot.mouseClick(kc_widget, qt_api.QtCore.Qt.MouseButton.LeftButton, pos=pos)
    assert mw.tray_keycodes.isVisible()

    # Set to "A"
    qtbot.mouseClick(find_key_btn(mw.tray_keycodes, "A"), qt_api.QtCore.Qt.MouseButton.LeftButton)
    assert vk.tap_dance[2] == (4, 0x106, 0, 0, 500)

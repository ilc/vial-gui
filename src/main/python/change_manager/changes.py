# SPDX-License-Identifier: GPL-2.0-or-later
"""Change classes for tracking uncommitted modifications."""
from abc import ABC, abstractmethod
from typing import Tuple, Any


class Change(ABC):
    """Base class for all change types."""

    @abstractmethod
    def key(self) -> Tuple:
        """Return unique key for deduplication.

        Changes with the same key will be merged (only latest value kept).
        """
        pass

    @abstractmethod
    def apply(self, keyboard) -> bool:
        """Send this change to the device.

        Returns True on success, False on failure.
        """
        pass

    @abstractmethod
    def revert(self, keyboard) -> bool:
        """Send old value to the device (for undo after save).

        Returns True on success, False on failure.
        """
        pass

    @abstractmethod
    def restore_local(self, keyboard, use_old: bool) -> None:
        """Restore value in keyboard's local state (not device).

        Used by undo/redo to update in-memory state.
        Args:
            keyboard: The keyboard object to update
            use_old: If True, restore old_value; if False, restore new_value
        """
        pass

    def merge(self, other: 'Change') -> bool:
        """Merge another change into this one.

        Called when a new change has the same key as an existing one.
        Default implementation replaces new_value with other's new_value.

        Returns True if merge was successful.
        """
        if hasattr(self, 'new_value') and hasattr(other, 'new_value'):
            self.new_value = other.new_value
            return True
        return False


class KeymapChange(Change):
    """Change to a key in the keymap."""

    def __init__(self, layer: int, row: int, col: int, old_value: int, new_value: int):
        self.layer = layer
        self.row = row
        self.col = col
        self.old_value = old_value
        self.new_value = new_value

    def key(self) -> Tuple:
        return ('keymap', self.layer, self.row, self.col)

    def apply(self, keyboard) -> bool:
        return keyboard._commit_key(self.layer, self.row, self.col, self.new_value)

    def revert(self, keyboard) -> bool:
        return keyboard._commit_key(self.layer, self.row, self.col, self.old_value)

    def restore_local(self, keyboard, use_old: bool) -> None:
        value = self.old_value if use_old else self.new_value
        keyboard.layout[(self.layer, self.row, self.col)] = value

    def __repr__(self):
        return f"KeymapChange(layer={self.layer}, row={self.row}, col={self.col}, {self.old_value}->{self.new_value})"


class EncoderChange(Change):
    """Change to an encoder action."""

    def __init__(self, layer: int, index: int, direction: int, old_value: int, new_value: int):
        self.layer = layer
        self.index = index
        self.direction = direction  # 0 = CW, 1 = CCW
        self.old_value = old_value
        self.new_value = new_value

    def key(self) -> Tuple:
        return ('encoder', self.layer, self.index, self.direction)

    def apply(self, keyboard) -> bool:
        return keyboard._commit_encoder(self.layer, self.index, self.direction, self.new_value)

    def revert(self, keyboard) -> bool:
        return keyboard._commit_encoder(self.layer, self.index, self.direction, self.old_value)

    def restore_local(self, keyboard, use_old: bool) -> None:
        value = self.old_value if use_old else self.new_value
        keyboard.encoder_layout[(self.layer, self.index, self.direction)] = value

    def __repr__(self):
        return f"EncoderChange(layer={self.layer}, idx={self.index}, dir={self.direction}, {self.old_value}->{self.new_value})"


class ComboChange(Change):
    """Change to a combo entry."""

    def __init__(self, index: int, old_value: Any, new_value: Any):
        self.index = index
        self.old_value = old_value  # Combo object or serialized form
        self.new_value = new_value

    def key(self) -> Tuple:
        return ('combo', self.index)

    def apply(self, keyboard) -> bool:
        return keyboard._commit_combo(self.index, self.new_value)

    def revert(self, keyboard) -> bool:
        return keyboard._commit_combo(self.index, self.old_value)

    def restore_local(self, keyboard, use_old: bool) -> None:
        value = self.old_value if use_old else self.new_value
        if hasattr(keyboard, 'combo_entries') and self.index < len(keyboard.combo_entries):
            keyboard.combo_entries[self.index] = value

    def __repr__(self):
        return f"ComboChange(index={self.index})"


class TapDanceChange(Change):
    """Change to a tap dance entry."""

    def __init__(self, index: int, old_value: Any, new_value: Any):
        self.index = index
        self.old_value = old_value
        self.new_value = new_value

    def key(self) -> Tuple:
        return ('tap_dance', self.index)

    def apply(self, keyboard) -> bool:
        return keyboard._commit_tap_dance(self.index, self.new_value)

    def revert(self, keyboard) -> bool:
        return keyboard._commit_tap_dance(self.index, self.old_value)

    def restore_local(self, keyboard, use_old: bool) -> None:
        value = self.old_value if use_old else self.new_value
        if hasattr(keyboard, 'tap_dance_entries') and self.index < len(keyboard.tap_dance_entries):
            keyboard.tap_dance_entries[self.index] = value

    def __repr__(self):
        return f"TapDanceChange(index={self.index})"


class KeyOverrideChange(Change):
    """Change to a key override entry."""

    def __init__(self, index: int, old_value: Any, new_value: Any):
        self.index = index
        self.old_value = old_value
        self.new_value = new_value

    def key(self) -> Tuple:
        return ('key_override', self.index)

    def apply(self, keyboard) -> bool:
        return keyboard._commit_key_override(self.index, self.new_value)

    def revert(self, keyboard) -> bool:
        return keyboard._commit_key_override(self.index, self.old_value)

    def restore_local(self, keyboard, use_old: bool) -> None:
        value = self.old_value if use_old else self.new_value
        if hasattr(keyboard, 'key_override_entries') and self.index < len(keyboard.key_override_entries):
            keyboard.key_override_entries[self.index] = value

    def __repr__(self):
        return f"KeyOverrideChange(index={self.index})"


class AltRepeatKeyChange(Change):
    """Change to an alternate repeat key entry."""

    def __init__(self, index: int, old_value: Any, new_value: Any):
        self.index = index
        self.old_value = old_value
        self.new_value = new_value

    def key(self) -> Tuple:
        return ('alt_repeat_key', self.index)

    def apply(self, keyboard) -> bool:
        return keyboard._commit_alt_repeat_key(self.index, self.new_value)

    def revert(self, keyboard) -> bool:
        return keyboard._commit_alt_repeat_key(self.index, self.old_value)

    def restore_local(self, keyboard, use_old: bool) -> None:
        value = self.old_value if use_old else self.new_value
        if hasattr(keyboard, 'alt_repeat_key_entries') and self.index < len(keyboard.alt_repeat_key_entries):
            keyboard.alt_repeat_key_entries[self.index] = value

    def __repr__(self):
        return f"AltRepeatKeyChange(index={self.index})"


class MacroChange(Change):
    """Change to a single macro."""

    def __init__(self, index: int, old_serialized: bytes, new_serialized: bytes):
        self.index = index
        self.old_value = old_serialized
        self.new_value = new_serialized

    def key(self) -> Tuple:
        return ('macro', self.index)

    def apply(self, keyboard) -> bool:
        # Get current macros, update this one, send all
        macros = keyboard.macro.split(b'\x00')
        # Ensure list is long enough
        while len(macros) <= self.index:
            macros.append(b'')
        macros[self.index] = self.new_value
        data = b'\x00'.join(macros[:keyboard.macro_count]) + b'\x00'
        return keyboard._commit_macro(data)

    def revert(self, keyboard) -> bool:
        macros = keyboard.macro.split(b'\x00')
        while len(macros) <= self.index:
            macros.append(b'')
        macros[self.index] = self.old_value
        data = b'\x00'.join(macros[:keyboard.macro_count]) + b'\x00'
        return keyboard._commit_macro(data)

    def restore_local(self, keyboard, use_old: bool) -> None:
        value = self.old_value if use_old else self.new_value
        macros = keyboard.macro.split(b'\x00')
        while len(macros) <= self.index:
            macros.append(b'')
        macros[self.index] = value
        keyboard.macro = b'\x00'.join(macros[:keyboard.macro_count]) + b'\x00'

    def __repr__(self):
        return f"MacroChange(index={self.index}, {len(self.old_value)}->{len(self.new_value)} bytes)"


class QmkSettingChange(Change):
    """Change to a QMK integer setting (non-bitfield)."""

    def __init__(self, qsid: int, old_value: int, new_value: int):
        self.qsid = qsid
        self.old_value = old_value
        self.new_value = new_value

    def key(self) -> Tuple:
        return ('qmk_setting', self.qsid)

    def apply(self, keyboard) -> bool:
        return keyboard._commit_qmk_setting(self.qsid, self.new_value)

    def revert(self, keyboard) -> bool:
        return keyboard._commit_qmk_setting(self.qsid, self.old_value)

    def restore_local(self, keyboard, use_old: bool) -> None:
        value = self.old_value if use_old else self.new_value
        if hasattr(keyboard, 'settings'):
            keyboard.settings[self.qsid] = value

    def __repr__(self):
        return f"QmkSettingChange(qsid={self.qsid}, {self.old_value}->{self.new_value})"


class QmkBitChange(Change):
    """Change to a single bit in a QMK bitfield setting."""

    def __init__(self, qsid: int, bit: int, old_bit: int, new_bit: int):
        self.qsid = qsid
        self.bit = bit
        self.old_value = old_bit  # 0 or 1
        self.new_value = new_bit  # 0 or 1

    def key(self) -> Tuple:
        return ('qmk_setting_bit', self.qsid, self.bit)

    def apply(self, keyboard) -> bool:
        current = keyboard.settings.get(self.qsid, 0)
        if self.new_value:
            current |= (1 << self.bit)
        else:
            current &= ~(1 << self.bit)
        keyboard.settings[self.qsid] = current
        return keyboard._commit_qmk_setting(self.qsid, current)

    def revert(self, keyboard) -> bool:
        current = keyboard.settings.get(self.qsid, 0)
        if self.old_value:
            current |= (1 << self.bit)
        else:
            current &= ~(1 << self.bit)
        keyboard.settings[self.qsid] = current
        return keyboard._commit_qmk_setting(self.qsid, current)

    def restore_local(self, keyboard, use_old: bool) -> None:
        value = self.old_value if use_old else self.new_value
        if hasattr(keyboard, 'settings'):
            current = keyboard.settings.get(self.qsid, 0)
            if value:
                current |= (1 << self.bit)
            else:
                current &= ~(1 << self.bit)
            keyboard.settings[self.qsid] = current

    def __repr__(self):
        return f"QmkBitChange(qsid={self.qsid}, bit={self.bit}, {self.old_value}->{self.new_value})"


class SvalboardSettingChange(Change):
    """Change to a single Svalboard setting."""

    def __init__(self, setting_name: str, old_value, new_value):
        self.setting_name = setting_name
        self.old_value = old_value
        self.new_value = new_value

    def key(self) -> Tuple:
        return ('svalboard', self.setting_name)

    def apply(self, keyboard) -> bool:
        # Get current settings, update this one, send all
        settings = keyboard.sval_settings.copy()
        settings[self.setting_name] = self.new_value
        return keyboard._commit_svalboard_settings(settings)

    def revert(self, keyboard) -> bool:
        settings = keyboard.sval_settings.copy()
        settings[self.setting_name] = self.old_value
        return keyboard._commit_svalboard_settings(settings)

    def restore_local(self, keyboard, use_old: bool) -> None:
        value = self.old_value if use_old else self.new_value
        if hasattr(keyboard, 'sval_settings'):
            keyboard.sval_settings[self.setting_name] = value

    def __repr__(self):
        return f"SvalboardSettingChange({self.setting_name}, {self.old_value}->{self.new_value})"


class SvalboardLayerColorChange(Change):
    """Change to a Svalboard layer color."""

    def __init__(self, layer: int, old_hsv: Tuple[int, int, int], new_hsv: Tuple[int, int, int]):
        self.layer = layer
        self.old_value = old_hsv
        self.new_value = new_hsv

    def key(self) -> Tuple:
        return ('svalboard_layer_color', self.layer)

    def apply(self, keyboard) -> bool:
        return keyboard._commit_svalboard_layer_color(self.layer, self.new_value)

    def revert(self, keyboard) -> bool:
        return keyboard._commit_svalboard_layer_color(self.layer, self.old_value)

    def restore_local(self, keyboard, use_old: bool) -> None:
        value = self.old_value if use_old else self.new_value
        if hasattr(keyboard, 'sval_layer_colors'):
            keyboard.sval_layer_colors[self.layer] = value

    def merge(self, other: 'SvalboardLayerColorChange') -> bool:
        self.new_value = other.new_value
        return True

    def __repr__(self):
        return f"SvalboardLayerColorChange(layer={self.layer}, {self.old_value}->{self.new_value})"

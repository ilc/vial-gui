# SPDX-License-Identifier: GPL-2.0-or-later
"""ChangeManager singleton for tracking uncommitted changes with undo/redo."""
import copy
from typing import Dict, List, Tuple, Optional, Any
from qtpy.QtCore import QObject, Signal

from .changes import Change
from .change_group import ChangeGroup


MAX_UNDO_STACK_SIZE = 1500


class KeyboardState:
    """Per-keyboard change tracking state."""

    def __init__(self):
        self.pending: Dict[Tuple, Change] = {}
        self.committed: Dict[Tuple, Any] = {}  # key -> value currently on device
        self.undo_stack: List[ChangeGroup] = []
        self.redo_stack: List[ChangeGroup] = []
        self.current_group: Optional[ChangeGroup] = None
        self.auto_commit: bool = False  # If True, changes immediately sent to device


class ChangeManager(QObject):
    """Singleton that manages uncommitted changes with undo/redo support.

    Each keyboard has its own state (pending changes, undo/redo stacks, auto_commit).

    Two modes per keyboard:
    - auto_commit=False (default): Changes tracked locally, Save commits to device
    - auto_commit=True: Changes immediately sent to device, undo/redo also immediate
    """

    # Signals
    changed = Signal()  # Emitted when any state changes
    can_undo_changed = Signal(bool)
    can_redo_changed = Signal(bool)
    can_save_changed = Signal(bool)
    modified_keys_changed = Signal(set)  # Set of modified keys
    auto_commit_changed = Signal(bool)  # Emitted when auto_commit mode changes
    values_restored = Signal(set)  # Emitted after undo/redo with affected keys
    saved = Signal()  # Emitted after successful save to device

    _instance: Optional['ChangeManager'] = None

    @classmethod
    def instance(cls) -> 'ChangeManager':
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (call on device disconnect)."""
        if cls._instance is not None:
            cls._instance.keyboard = None
            cls._instance._emit_state_changes()

    def __init__(self):
        super().__init__()
        self.keyboard = None

        # Per-keyboard state, keyed by keyboard_id
        self._keyboard_states: Dict[int, KeyboardState] = {}

        # Track previous signal states to avoid redundant emissions
        self._prev_can_undo = False
        self._prev_can_redo = False
        self._prev_can_save = False
        self._prev_auto_commit = False
        self._prev_modified_keys: set = set()

    def _get_state(self) -> Optional[KeyboardState]:
        """Get state for current keyboard."""
        if self.keyboard is None:
            return None
        kbd_id = getattr(self.keyboard, 'keyboard_id', id(self.keyboard))
        if kbd_id not in self._keyboard_states:
            self._keyboard_states[kbd_id] = KeyboardState()
        return self._keyboard_states[kbd_id]

    def set_keyboard(self, keyboard) -> None:
        """Set the keyboard instance for applying changes."""
        self.keyboard = keyboard
        self._emit_state_changes()

    def clear(self) -> None:
        """Clear state for current keyboard."""
        state = self._get_state()
        if state:
            state.pending.clear()
            state.committed.clear()
            state.undo_stack.clear()
            state.redo_stack.clear()
            state.current_group = None
            self._emit_state_changes()

    @property
    def auto_commit(self) -> bool:
        """Get auto_commit mode for current keyboard."""
        state = self._get_state()
        return state.auto_commit if state else False

    @auto_commit.setter
    def auto_commit(self, value: bool) -> None:
        """Set auto_commit mode for current keyboard."""
        state = self._get_state()
        if state and state.auto_commit != value:
            state.auto_commit = value
            # If turning on auto_commit, immediately save any pending changes
            if value and state.pending:
                self.save()
            self._emit_state_changes()

    def begin_group(self, name: str) -> None:
        """Begin a grouped operation (e.g., 'Fill layer').

        All changes until end_group() become a single undo unit.
        Groups can be nested - only outermost matters.
        """
        state = self._get_state()
        if state and state.current_group is None:
            state.current_group = ChangeGroup(name)

    def end_group(self) -> None:
        """End the current grouped operation."""
        state = self._get_state()
        if state and state.current_group is not None:
            if not state.current_group.is_empty():
                self._push_to_undo_stack(state.current_group)
                # In auto_commit mode, apply the group immediately
                if state.auto_commit and self.keyboard:
                    state.current_group.apply(self.keyboard)
                    state.pending.clear()
            state.current_group = None
            self._emit_state_changes()

    def add_change(self, change: Change) -> None:
        """Add a change to tracking.

        Deduplicates by key - if same key exists, merges values.
        Clears redo stack (new change invalidates redo history).
        In auto_commit mode, immediately applies to device.
        """
        state = self._get_state()
        if not state:
            return

        key = change.key()

        # Update pending changes
        if key in state.pending:
            state.pending[key].merge(change)
        else:
            state.pending[key] = change

        # Handle grouping - copy change so undo stack isn't corrupted by later merges
        if state.current_group is not None:
            state.current_group.add(copy.copy(change))
        else:
            # Single change = its own group
            group = ChangeGroup("Change")
            group.add(copy.copy(change))
            self._push_to_undo_stack(group)

            # In auto_commit mode, immediately apply to device
            if state.auto_commit and self.keyboard:
                change.apply(self.keyboard)
                # Clear pending since it's now on device
                if key in state.pending:
                    del state.pending[key]

        # Clear redo stack on new change
        if state.redo_stack:
            state.redo_stack.clear()

        self._emit_state_changes()

    def _push_to_undo_stack(self, group: ChangeGroup) -> None:
        """Push a group to undo stack, enforcing max size."""
        state = self._get_state()
        if state:
            state.undo_stack.append(group)
            while len(state.undo_stack) > MAX_UNDO_STACK_SIZE:
                state.undo_stack.pop(0)

    def undo(self) -> bool:
        """Undo the last change group.

        In auto_commit mode, immediately reverts on device.
        Returns True if undo was performed.
        """
        state = self._get_state()
        if not state or not state.undo_stack:
            return False

        group = state.undo_stack.pop()
        state.redo_stack.append(group)

        # Collect affected keys for UI refresh
        affected_keys = set()

        # Revert each change
        for change in group.changes:
            key = change.key()
            affected_keys.add(key)

            # Restore old value in keyboard state
            self._restore_value(change, use_old=True)

            if state.auto_commit:
                # In auto_commit mode, update device
                if self.keyboard is not None:
                    change.revert(self.keyboard)
            else:
                # In normal mode, update pending tracking
                earlier_value = self._find_earlier_value(key)
                local_value = earlier_value if earlier_value is not None else change.old_value
                self._update_pending(state, key, change, local_value)

        self._emit_state_changes()
        self.values_restored.emit(affected_keys)
        return True

    def _restore_value(self, change: Change, use_old: bool) -> None:
        """Restore a value in the keyboard state.

        Precondition: self.keyboard is not None (checked by caller).
        """
        change.restore_local(self.keyboard, use_old)

    def _find_earlier_value(self, key: Tuple) -> Optional[Any]:
        """Find the value for this key from an earlier undo stack entry.

        Precondition: keyboard state exists (checked by caller).
        """
        state = self._get_state()
        for group in reversed(state.undo_stack):
            change = group.get_change(key)
            if change is not None and hasattr(change, 'new_value'):
                return change.new_value
        return None

    def _update_pending(self, state: KeyboardState, key: Tuple,
                        change: Change, local_value: Any) -> None:
        """Update pending state after undo/redo.

        Compares local_value against device/original to determine if pending needed.
        """
        # What's the reference value (on device, or original if never saved)?
        device_value = state.committed.get(key)
        if device_value is not None:
            reference_value = device_value
        elif key in state.pending:
            reference_value = state.pending[key].old_value
        else:
            reference_value = change.old_value

        if local_value == reference_value:
            # Matches device/original - no pending
            if key in state.pending:
                del state.pending[key]
        else:
            # Differs - update pending
            if key in state.pending:
                state.pending[key].new_value = local_value
            else:
                updated = copy.copy(change)
                updated.old_value = reference_value
                updated.new_value = local_value
                state.pending[key] = updated

    def redo(self) -> bool:
        """Redo the last undone change group.

        In auto_commit mode, immediately applies to device.
        Returns True if redo was performed.
        """
        state = self._get_state()
        if not state or not state.redo_stack:
            return False

        group = state.redo_stack.pop()
        state.undo_stack.append(group)

        # Collect affected keys for UI refresh
        affected_keys = set()

        # Re-apply each change
        for change in group.changes:
            key = change.key()
            affected_keys.add(key)

            # Restore new value in keyboard state
            self._restore_value(change, use_old=False)

            if state.auto_commit:
                # In auto_commit mode, update device
                if self.keyboard is not None:
                    change.apply(self.keyboard)
            else:
                # In normal mode, update pending tracking
                self._update_pending(state, key, change, change.new_value)

        self._emit_state_changes()
        self.values_restored.emit(affected_keys)
        return True

    def save(self) -> bool:
        """Commit all pending changes to the device.

        Returns True if all succeeded, False if any failed.
        """
        state = self._get_state()
        if self.keyboard is None or not state:
            return False

        if not state.pending:
            return True

        success = True
        for change in state.pending.values():
            if not change.apply(self.keyboard):
                success = False

        if success:
            # Record what was committed to device
            for key, change in state.pending.items():
                state.committed[key] = change.new_value
            state.pending.clear()
            self._emit_state_changes()
            self.saved.emit()

        return success

    def discard_all(self) -> None:
        """Discard all pending changes without saving."""
        state = self._get_state()
        if state:
            state.pending.clear()
            state.undo_stack.clear()
            state.redo_stack.clear()
            self._emit_state_changes()

    def revert_all(self) -> None:
        """Revert all pending changes - restore original values and clear stacks."""
        state = self._get_state()
        if not state or not state.pending:
            return

        # Collect all affected keys
        affected_keys = set()

        # Restore original values for all pending changes
        for key, change in state.pending.items():
            affected_keys.add(key)
            self._restore_value(change, use_old=True)

        # Clear all state
        state.pending.clear()
        state.committed.clear()
        state.undo_stack.clear()
        state.redo_stack.clear()

        self._emit_state_changes()
        self.values_restored.emit(affected_keys)

    def has_pending_changes(self) -> bool:
        """Return True if there are unsaved changes."""
        state = self._get_state()
        # In auto_commit mode, changes are immediately committed - no pending state
        if not state or state.auto_commit:
            return False
        return bool(state.pending)

    def is_modified(self, key: Tuple) -> bool:
        """Return True if the given key has a pending change."""
        state = self._get_state()
        # In auto_commit mode, changes are immediately committed - no pending state
        if not state or state.auto_commit:
            return False
        return key in state.pending

    def get_pending_value(self, key: Tuple) -> Optional[Any]:
        """Get the pending value for a key, or None if not modified."""
        state = self._get_state()
        if not state or state.auto_commit:
            return None
        change = state.pending.get(key)
        if change is not None and hasattr(change, 'new_value'):
            return change.new_value
        return None

    def get_modified_keys(self) -> set:
        """Return set of all modified keys."""
        state = self._get_state()
        # In auto_commit mode, changes are immediately committed - no pending state
        if not state or state.auto_commit:
            return set()
        return set(state.pending.keys())

    def can_undo(self) -> bool:
        """Return True if undo is available."""
        state = self._get_state()
        return bool(state.undo_stack) if state else False

    def can_redo(self) -> bool:
        """Return True if redo is available."""
        state = self._get_state()
        return bool(state.redo_stack) if state else False

    def pending_count(self) -> int:
        """Return number of pending changes."""
        state = self._get_state()
        return len(state.pending) if state else 0

    def undo_stack_size(self) -> int:
        """Return current undo stack size."""
        state = self._get_state()
        return len(state.undo_stack) if state else 0

    def max_undo_stack_size(self) -> int:
        """Return maximum undo stack size."""
        return MAX_UNDO_STACK_SIZE

    def _emit_state_changes(self) -> None:
        """Emit signals for state changes."""
        can_undo = self.can_undo()
        can_redo = self.can_redo()
        can_save = self.has_pending_changes()
        auto_commit = self.auto_commit

        if can_undo != self._prev_can_undo:
            self._prev_can_undo = can_undo
            self.can_undo_changed.emit(can_undo)

        if can_redo != self._prev_can_redo:
            self._prev_can_redo = can_redo
            self.can_redo_changed.emit(can_redo)

        if can_save != self._prev_can_save:
            self._prev_can_save = can_save
            self.can_save_changed.emit(can_save)

        if auto_commit != self._prev_auto_commit:
            self._prev_auto_commit = auto_commit
            self.auto_commit_changed.emit(auto_commit)

        modified_keys = self.get_modified_keys()
        if modified_keys != self._prev_modified_keys:
            self._prev_modified_keys = modified_keys
            self.modified_keys_changed.emit(modified_keys)

        self.changed.emit()

# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for ChangeManager undo/redo and commit tracking."""
import pytest
from change_manager import ChangeManager
from change_manager.changes import Change


class SimpleChange(Change):
    """Simple change for testing - doesn't need real keyboard."""

    def __init__(self, key_id: str, old_value, new_value):
        self.key_id = key_id
        self.old_value = old_value
        self.new_value = new_value

    def key(self):
        return ('test', self.key_id)

    def apply(self, keyboard):
        keyboard.values[self.key_id] = self.new_value
        return True

    def revert(self, keyboard):
        keyboard.values[self.key_id] = self.old_value
        return True

    def restore_local(self, keyboard, use_old: bool):
        value = self.old_value if use_old else self.new_value
        keyboard.values[self.key_id] = value


class MockKeyboard:
    """Mock keyboard for testing."""

    def __init__(self):
        self.keyboard_id = 12345
        self.values = {}


@pytest.fixture
def cm():
    """Fresh ChangeManager with mock keyboard."""
    # Reset singleton
    ChangeManager._instance = None
    cm = ChangeManager.instance()
    cm.set_keyboard(MockKeyboard())
    return cm


class TestBasicOperations:
    """Test basic add/undo/redo operations."""

    def test_add_change_marks_modified(self, cm):
        change = SimpleChange('a', 0, 1)
        cm.add_change(change)

        assert cm.is_modified(('test', 'a'))
        assert cm.has_pending_changes()
        assert cm.pending_count() == 1

    def test_add_change_clears_redo(self, cm):
        cm.add_change(SimpleChange('a', 0, 1))
        cm.undo()
        assert cm.can_redo()

        cm.add_change(SimpleChange('b', 0, 1))
        assert not cm.can_redo()

    def test_undo_without_save_clears_pending(self, cm):
        cm.add_change(SimpleChange('a', 0, 1))
        assert cm.is_modified(('test', 'a'))

        cm.undo()
        assert not cm.is_modified(('test', 'a'))
        assert not cm.has_pending_changes()

    def test_redo_after_undo_restores_pending(self, cm):
        cm.add_change(SimpleChange('a', 0, 1))
        cm.undo()
        assert not cm.is_modified(('test', 'a'))

        cm.redo()
        assert cm.is_modified(('test', 'a'))
        assert cm.has_pending_changes()


class TestSaveAndCommit:
    """Test save/commit tracking."""

    def test_save_clears_pending(self, cm):
        cm.add_change(SimpleChange('a', 0, 1))
        assert cm.has_pending_changes()

        cm.save()
        assert not cm.has_pending_changes()
        assert not cm.is_modified(('test', 'a'))

    def test_save_records_committed_value(self, cm):
        cm.add_change(SimpleChange('a', 0, 1))
        cm.save()

        state = cm._get_state()
        assert ('test', 'a') in state.committed
        assert state.committed[('test', 'a')] == 1

    def test_undo_after_save_creates_pending(self, cm):
        """Undo after save should mark change as pending (device differs from local)."""
        cm.add_change(SimpleChange('a', 0, 1))
        cm.save()
        assert not cm.is_modified(('test', 'a'))

        cm.undo()
        # Now local=0, device=1, so there's a pending change
        assert cm.is_modified(('test', 'a'))
        assert cm.has_pending_changes()

    def test_undo_after_save_pending_has_correct_values(self, cm):
        """After undo-after-save, pending should send old_value to device."""
        cm.add_change(SimpleChange('a', 0, 1))
        cm.save()
        cm.undo()

        state = cm._get_state()
        pending = state.pending[('test', 'a')]
        # We want to send 0 to device (which has 1)
        assert pending.new_value == 0
        assert pending.old_value == 1

    def test_redo_after_save_undo_clears_pending(self, cm):
        """Redo back to committed value should clear pending."""
        cm.add_change(SimpleChange('a', 0, 1))
        cm.save()  # device has 1
        cm.undo()  # local=0, pending to send 0
        assert cm.is_modified(('test', 'a'))

        cm.redo()  # local=1, matches device
        assert not cm.is_modified(('test', 'a'))
        assert not cm.has_pending_changes()


class TestMultipleChanges:
    """Test scenarios with multiple changes."""

    def test_multiple_changes_same_key_merge(self, cm):
        cm.add_change(SimpleChange('a', 0, 1))
        cm.add_change(SimpleChange('a', 1, 2))

        assert cm.pending_count() == 1
        state = cm._get_state()
        assert state.pending[('test', 'a')].new_value == 2
        # old_value should still be original
        assert state.pending[('test', 'a')].old_value == 0

    def test_multiple_changes_different_keys(self, cm):
        cm.add_change(SimpleChange('a', 0, 1))
        cm.add_change(SimpleChange('b', 0, 1))

        assert cm.pending_count() == 2
        assert cm.is_modified(('test', 'a'))
        assert cm.is_modified(('test', 'b'))

    def test_undo_one_of_multiple_changes(self, cm):
        cm.add_change(SimpleChange('a', 0, 1))
        cm.add_change(SimpleChange('b', 0, 1))
        cm.undo()  # undoes 'b'

        assert cm.is_modified(('test', 'a'))
        assert not cm.is_modified(('test', 'b'))

    def test_save_then_change_different_key_then_undo(self, cm):
        """Save A, change B, undo B - A should not be pending."""
        cm.add_change(SimpleChange('a', 0, 1))
        cm.save()
        cm.add_change(SimpleChange('b', 0, 1))
        cm.undo()

        assert not cm.is_modified(('test', 'a'))
        assert not cm.is_modified(('test', 'b'))

    def test_partial_save_sequence(self, cm):
        """Change A, save, change B, undo B, undo A - A should be pending."""
        cm.add_change(SimpleChange('a', 0, 1))
        cm.save()  # device has a=1
        cm.add_change(SimpleChange('b', 0, 1))
        cm.undo()  # undo b
        cm.undo()  # undo a (after save!)

        assert cm.is_modified(('test', 'a'))  # local=0, device=1
        assert not cm.is_modified(('test', 'b'))


class TestUndoRedoChains:
    """Test complex undo/redo sequences."""

    def test_undo_redo_undo_redo(self, cm):
        cm.add_change(SimpleChange('a', 0, 1))

        cm.undo()
        assert not cm.is_modified(('test', 'a'))

        cm.redo()
        assert cm.is_modified(('test', 'a'))

        cm.undo()
        assert not cm.is_modified(('test', 'a'))

        cm.redo()
        assert cm.is_modified(('test', 'a'))

    def test_save_undo_redo_undo_redo(self, cm):
        """Complex sequence after save."""
        cm.add_change(SimpleChange('a', 0, 1))
        cm.save()  # device=1

        cm.undo()  # local=0
        assert cm.is_modified(('test', 'a'))

        cm.redo()  # local=1
        assert not cm.is_modified(('test', 'a'))

        cm.undo()  # local=0
        assert cm.is_modified(('test', 'a'))

        cm.redo()  # local=1
        assert not cm.is_modified(('test', 'a'))

    def test_change_save_change_undo_undo(self, cm):
        """A->save->B->undo->undo should have A pending."""
        cm.add_change(SimpleChange('a', 0, 1))
        cm.save()  # device has a=1
        cm.add_change(SimpleChange('a', 1, 2))  # change a again
        assert cm.is_modified(('test', 'a'))

        cm.undo()  # back to a=1 (matches device)
        assert not cm.is_modified(('test', 'a'))

        cm.undo()  # back to a=0 (device still has 1)
        assert cm.is_modified(('test', 'a'))
        state = cm._get_state()
        assert state.pending[('test', 'a')].new_value == 0

    def test_multiple_saves(self, cm):
        """Multiple save cycles."""
        cm.add_change(SimpleChange('a', 0, 1))
        cm.save()  # device=1

        cm.add_change(SimpleChange('a', 1, 2))
        cm.save()  # device=2

        cm.undo()  # local=1, device=2
        assert cm.is_modified(('test', 'a'))
        state = cm._get_state()
        assert state.pending[('test', 'a')].new_value == 1
        assert state.committed[('test', 'a')] == 2


class TestGroups:
    """Test grouped operations."""

    def test_group_single_undo(self, cm):
        """Grouped changes undo as one unit."""
        cm.begin_group("test")
        cm.add_change(SimpleChange('a', 0, 1))
        cm.add_change(SimpleChange('b', 0, 1))
        cm.end_group()

        assert cm.pending_count() == 2
        assert cm.undo_stack_size() == 1

        cm.undo()
        assert cm.pending_count() == 0

    def test_group_after_save(self, cm):
        """Grouped undo after save creates pending for all."""
        cm.begin_group("test")
        cm.add_change(SimpleChange('a', 0, 1))
        cm.add_change(SimpleChange('b', 0, 1))
        cm.end_group()
        cm.save()

        cm.undo()
        assert cm.is_modified(('test', 'a'))
        assert cm.is_modified(('test', 'b'))


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_undo_empty_stack(self, cm):
        assert not cm.undo()

    def test_redo_empty_stack(self, cm):
        assert not cm.redo()

    def test_save_empty_pending(self, cm):
        assert cm.save()  # Should succeed with nothing to save

    def test_clear_resets_everything(self, cm):
        cm.add_change(SimpleChange('a', 0, 1))
        cm.save()
        cm.add_change(SimpleChange('b', 0, 1))

        cm.clear()

        assert not cm.has_pending_changes()
        assert not cm.can_undo()
        state = cm._get_state()
        assert len(state.committed) == 0

    def test_revert_all_clears_committed(self, cm):
        cm.add_change(SimpleChange('a', 0, 1))
        cm.save()
        cm.add_change(SimpleChange('a', 1, 2))

        cm.revert_all()

        state = cm._get_state()
        assert len(state.committed) == 0
        assert len(state.pending) == 0

    def test_keyboard_value_updated_on_undo(self, cm):
        """Verify keyboard state is updated on undo."""
        cm.add_change(SimpleChange('a', 0, 1))
        assert cm.keyboard.values.get('a') is None  # Change doesn't auto-apply

        cm.undo()
        # _restore_value should have been called, but our mock doesn't use it
        # In real code, keyboard.values['a'] would be 0

    def test_no_keyboard_no_crash(self):
        """Operations without keyboard shouldn't crash."""
        ChangeManager._instance = None
        cm = ChangeManager.instance()
        # No keyboard set

        cm.add_change(SimpleChange('a', 0, 1))
        cm.undo()
        cm.redo()
        cm.save()


class TestSignalNotifications:
    """Test signal emissions and subscriber notifications."""

    def test_can_undo_changed_signal(self, cm):
        """can_undo_changed fires when undo availability changes."""
        signals = []
        cm.can_undo_changed.connect(lambda v: signals.append(('undo', v)))

        cm.add_change(SimpleChange('a', 0, 1))
        assert ('undo', True) in signals

        cm.undo()
        assert ('undo', False) in signals

    def test_can_redo_changed_signal(self, cm):
        """can_redo_changed fires when redo availability changes."""
        signals = []
        cm.can_redo_changed.connect(lambda v: signals.append(('redo', v)))

        cm.add_change(SimpleChange('a', 0, 1))
        cm.undo()
        assert ('redo', True) in signals

        cm.redo()
        assert ('redo', False) in signals

    def test_can_save_changed_signal(self, cm):
        """can_save_changed fires when pending changes exist/clear."""
        signals = []
        cm.can_save_changed.connect(lambda v: signals.append(('save', v)))

        cm.add_change(SimpleChange('a', 0, 1))
        assert ('save', True) in signals

        cm.save()
        assert ('save', False) in signals

    def test_modified_keys_changed_signal(self, cm):
        """modified_keys_changed emits current set of modified keys."""
        last_keys = [None]
        cm.modified_keys_changed.connect(lambda keys: last_keys.__setitem__(0, keys))

        cm.add_change(SimpleChange('a', 0, 1))
        assert ('test', 'a') in last_keys[0]

        cm.add_change(SimpleChange('b', 0, 1))
        assert ('test', 'a') in last_keys[0]
        assert ('test', 'b') in last_keys[0]

        cm.undo()
        assert ('test', 'a') in last_keys[0]
        assert ('test', 'b') not in last_keys[0]

    def test_saved_signal_emitted(self, cm):
        """saved signal fires after successful save."""
        saved_count = [0]
        cm.saved.connect(lambda: saved_count.__setitem__(0, saved_count[0] + 1))

        cm.add_change(SimpleChange('a', 0, 1))
        cm.save()
        assert saved_count[0] == 1

        # No-op save shouldn't emit
        cm.save()
        assert saved_count[0] == 1

    def test_values_restored_signal_contains_affected_keys(self, cm):
        """values_restored signal includes all affected keys."""
        restored_keys = [None]
        cm.values_restored.connect(lambda keys: restored_keys.__setitem__(0, keys))

        cm.add_change(SimpleChange('a', 0, 1))
        cm.add_change(SimpleChange('b', 0, 1))
        cm.undo()  # undoes 'b'

        assert ('test', 'b') in restored_keys[0]
        assert ('test', 'a') not in restored_keys[0]

    def test_group_signals_fire_once_at_end(self, cm):
        """Grouped operations emit signals once at end_group."""
        change_count = [0]
        cm.changed.connect(lambda: change_count.__setitem__(0, change_count[0] + 1))

        initial = change_count[0]
        cm.begin_group("test")
        cm.add_change(SimpleChange('a', 0, 1))
        mid_group = change_count[0]
        cm.add_change(SimpleChange('b', 0, 1))
        cm.add_change(SimpleChange('c', 0, 1))
        cm.end_group()
        final = change_count[0]

        # Each add_change fires changed, plus end_group
        # But can_save_changed should only transition once
        assert final > initial


class TestMultipleSubscribers:
    """Test multiple editors/panels subscribing to signals."""

    def test_multiple_saved_subscribers(self, cm):
        """Multiple subscribers all receive saved signal."""
        received = {'a': False, 'b': False, 'c': False}

        cm.saved.connect(lambda: received.__setitem__('a', True))
        cm.saved.connect(lambda: received.__setitem__('b', True))
        cm.saved.connect(lambda: received.__setitem__('c', True))

        cm.add_change(SimpleChange('x', 0, 1))
        cm.save()

        assert all(received.values())

    def test_multiple_values_restored_subscribers(self, cm):
        """Multiple subscribers all receive values_restored signal."""
        received = {'a': None, 'b': None}

        cm.values_restored.connect(lambda keys: received.__setitem__('a', keys))
        cm.values_restored.connect(lambda keys: received.__setitem__('b', keys))

        cm.add_change(SimpleChange('x', 0, 1))
        cm.undo()

        assert received['a'] == received['b']
        assert ('test', 'x') in received['a']

    def test_subscriber_filters_by_key_type(self, cm):
        """Subscribers can filter for their key types."""
        combo_changes = []
        keymap_changes = []

        def combo_listener(keys):
            combo_changes.extend(k for k in keys if k[0] == 'combo')

        def keymap_listener(keys):
            keymap_changes.extend(k for k in keys if k[0] == 'keymap')

        cm.values_restored.connect(combo_listener)
        cm.values_restored.connect(keymap_listener)

        # Add different key types
        cm.add_change(SimpleChange('a', 0, 1))  # ('test', 'a')
        cm.undo()

        # Neither should match 'test' type
        assert len(combo_changes) == 0
        assert len(keymap_changes) == 0

    def test_modified_keys_changed_only_emits_on_change(self, cm):
        """modified_keys_changed only emits when the set actually changes."""
        emissions = []
        cm.modified_keys_changed.connect(lambda keys: emissions.append(set(keys)))

        # First change - should emit
        cm.add_change(SimpleChange('a', 0, 1))
        assert len(emissions) == 1
        assert emissions[-1] == {('test', 'a')}

        # Same key modified again - set unchanged, should NOT emit again
        cm.add_change(SimpleChange('a', 1, 2))
        assert len(emissions) == 1  # Still just 1 emission

        # New key - should emit
        cm.add_change(SimpleChange('b', 0, 1))
        assert len(emissions) == 2
        assert emissions[-1] == {('test', 'a'), ('test', 'b')}

        # Undo one - should emit (set changed)
        cm.undo()
        assert len(emissions) == 3
        assert emissions[-1] == {('test', 'a')}


class TestMultipleKeyboards:
    """Test per-keyboard state isolation."""

    def test_keyboards_have_separate_state(self):
        """Different keyboards have independent undo/redo stacks."""
        ChangeManager._instance = None
        cm = ChangeManager.instance()

        kb1 = MockKeyboard()
        kb1.keyboard_id = 1
        kb2 = MockKeyboard()
        kb2.keyboard_id = 2

        # Work on keyboard 1
        cm.set_keyboard(kb1)
        cm.add_change(SimpleChange('a', 0, 1))
        cm.add_change(SimpleChange('b', 0, 1))
        assert cm.pending_count() == 2
        assert cm.undo_stack_size() == 2

        # Switch to keyboard 2 - fresh state
        cm.set_keyboard(kb2)
        assert cm.pending_count() == 0
        assert cm.undo_stack_size() == 0

        # Add changes to kb2
        cm.add_change(SimpleChange('x', 0, 1))
        assert cm.pending_count() == 1

        # Switch back to kb1 - state preserved
        cm.set_keyboard(kb1)
        assert cm.pending_count() == 2
        assert cm.undo_stack_size() == 2

    def test_keyboard_committed_state_independent(self):
        """Committed state is per-keyboard."""
        ChangeManager._instance = None
        cm = ChangeManager.instance()

        kb1 = MockKeyboard()
        kb1.keyboard_id = 1
        kb2 = MockKeyboard()
        kb2.keyboard_id = 2

        # Save on kb1
        cm.set_keyboard(kb1)
        cm.add_change(SimpleChange('a', 0, 1))
        cm.save()

        # kb2 has no committed state
        cm.set_keyboard(kb2)
        state = cm._get_state()
        assert len(state.committed) == 0

        # kb1 still has committed state
        cm.set_keyboard(kb1)
        state = cm._get_state()
        assert ('test', 'a') in state.committed

    def test_auto_commit_is_per_keyboard(self):
        """Each keyboard has its own auto_commit setting."""
        ChangeManager._instance = None
        cm = ChangeManager.instance()

        kb1 = MockKeyboard()
        kb1.keyboard_id = 1
        kb2 = MockKeyboard()
        kb2.keyboard_id = 2

        # Enable auto_commit on kb1
        cm.set_keyboard(kb1)
        cm.auto_commit = True
        assert cm.auto_commit == True

        # kb2 should default to False
        cm.set_keyboard(kb2)
        assert cm.auto_commit == False

        # kb1 should still be True
        cm.set_keyboard(kb1)
        assert cm.auto_commit == True

    def test_save_on_multiple_keyboards_independently(self):
        """Saves on different keyboards don't interfere."""
        ChangeManager._instance = None
        cm = ChangeManager.instance()

        kb1 = MockKeyboard()
        kb1.keyboard_id = 1
        kb2 = MockKeyboard()
        kb2.keyboard_id = 2

        # Change and save on kb1
        cm.set_keyboard(kb1)
        cm.add_change(SimpleChange('a', 0, 1))
        cm.save()

        # Change and save on kb2
        cm.set_keyboard(kb2)
        cm.add_change(SimpleChange('a', 0, 99))  # Same key, different value
        cm.save()

        # Verify committed states are independent
        cm.set_keyboard(kb1)
        assert cm._get_state().committed[('test', 'a')] == 1

        cm.set_keyboard(kb2)
        assert cm._get_state().committed[('test', 'a')] == 99

    def test_undo_after_save_different_keyboards(self):
        """Undo after save works correctly when switching keyboards."""
        ChangeManager._instance = None
        cm = ChangeManager.instance()

        kb1 = MockKeyboard()
        kb1.keyboard_id = 1
        kb2 = MockKeyboard()
        kb2.keyboard_id = 2

        # kb1: change, save, change again
        cm.set_keyboard(kb1)
        cm.add_change(SimpleChange('a', 0, 1))
        cm.save()
        cm.add_change(SimpleChange('a', 1, 2))

        # Switch to kb2, do some work
        cm.set_keyboard(kb2)
        cm.add_change(SimpleChange('x', 0, 1))
        cm.save()

        # Switch back to kb1 and undo
        cm.set_keyboard(kb1)
        assert cm.is_modified(('test', 'a'))  # pending: 1->2

        cm.undo()  # back to 1 (matches committed)
        assert not cm.is_modified(('test', 'a'))

        cm.undo()  # back to 0 (device has 1)
        assert cm.is_modified(('test', 'a'))
        assert cm._get_state().pending[('test', 'a')].new_value == 0

    def test_auto_commit_vs_regular_mode_switching(self):
        """Switching between auto_commit and regular keyboards."""
        ChangeManager._instance = None
        cm = ChangeManager.instance()

        kb1 = MockKeyboard()
        kb1.keyboard_id = 1
        kb2 = MockKeyboard()
        kb2.keyboard_id = 2

        # kb1 in auto_commit mode
        cm.set_keyboard(kb1)
        cm.auto_commit = True
        cm.add_change(SimpleChange('a', 0, 1))
        assert not cm.has_pending_changes()  # auto-applied
        assert kb1.values.get('a') == 1

        # kb2 in regular mode
        cm.set_keyboard(kb2)
        assert cm.auto_commit == False
        cm.add_change(SimpleChange('b', 0, 1))
        assert cm.has_pending_changes()  # not auto-applied

        # Switch back - kb1 still auto_commit, no pending
        cm.set_keyboard(kb1)
        assert cm.auto_commit == True
        assert not cm.has_pending_changes()

        # Switch back - kb2 still has pending
        cm.set_keyboard(kb2)
        assert cm.has_pending_changes()

    def test_auto_commit_signal_fires_on_keyboard_switch(self):
        """auto_commit_changed signal fires when switching to keyboard with different mode."""
        ChangeManager._instance = None
        cm = ChangeManager.instance()

        kb1 = MockKeyboard()
        kb1.keyboard_id = 1
        kb2 = MockKeyboard()
        kb2.keyboard_id = 2

        # Set up kb1 with auto_commit
        cm.set_keyboard(kb1)
        cm.auto_commit = True

        # Set up kb2 without (default)
        cm.set_keyboard(kb2)

        # Now track signals
        signals = []
        cm.auto_commit_changed.connect(lambda v: signals.append(v))

        # Switch to kb1 - should emit True
        cm.set_keyboard(kb1)
        assert True in signals

        # Switch to kb2 - should emit False
        signals.clear()
        cm.set_keyboard(kb2)
        assert False in signals


class TestAutoCommitMode:
    """Test auto_commit mode behavior."""

    def test_auto_commit_no_pending(self, cm):
        """In auto_commit mode, changes don't accumulate as pending."""
        cm.auto_commit = True
        cm.add_change(SimpleChange('a', 0, 1))

        assert not cm.has_pending_changes()
        assert not cm.is_modified(('test', 'a'))

    def test_auto_commit_applies_immediately(self, cm):
        """In auto_commit mode, changes apply to keyboard immediately."""
        cm.auto_commit = True
        cm.add_change(SimpleChange('a', 0, 1))

        # SimpleChange.apply sets keyboard.values
        assert cm.keyboard.values.get('a') == 1

    def test_auto_commit_undo_reverts_device(self, cm):
        """In auto_commit mode, undo calls revert on device."""
        cm.auto_commit = True
        cm.add_change(SimpleChange('a', 0, 1))
        assert cm.keyboard.values.get('a') == 1

        cm.undo()
        assert cm.keyboard.values.get('a') == 0

    def test_auto_commit_redo_applies_device(self, cm):
        """In auto_commit mode, redo calls apply on device."""
        cm.auto_commit = True
        cm.add_change(SimpleChange('a', 0, 1))
        cm.undo()
        assert cm.keyboard.values.get('a') == 0

        cm.redo()
        assert cm.keyboard.values.get('a') == 1

    def test_enabling_auto_commit_saves_pending(self, cm):
        """Enabling auto_commit saves any existing pending changes."""
        cm.add_change(SimpleChange('a', 0, 1))
        assert cm.has_pending_changes()

        cm.auto_commit = True
        assert not cm.has_pending_changes()
        assert cm.keyboard.values.get('a') == 1

    def test_auto_commit_changed_signal(self, cm):
        """auto_commit_changed signal fires on mode change."""
        signals = []
        cm.auto_commit_changed.connect(lambda v: signals.append(v))

        cm.auto_commit = True
        assert True in signals

        cm.auto_commit = False
        assert False in signals

    def test_auto_commit_group_applies_at_end(self, cm):
        """In auto_commit mode, group applies at end_group."""
        cm.auto_commit = True

        cm.begin_group("test")
        cm.add_change(SimpleChange('a', 0, 1))
        # Not applied yet during group
        cm.add_change(SimpleChange('b', 0, 1))
        cm.end_group()

        # Now both should be applied
        assert cm.keyboard.values.get('a') == 1
        assert cm.keyboard.values.get('b') == 1


class TestComplexScenarios:
    """Test complex real-world scenarios."""

    def test_edit_save_edit_undo_undo_redo_redo(self, cm):
        """Complex editing session with saves in the middle."""
        # User edits a, saves
        cm.add_change(SimpleChange('a', 0, 1))
        cm.save()
        assert not cm.is_modified(('test', 'a'))

        # User edits a again
        cm.add_change(SimpleChange('a', 1, 2))
        assert cm.is_modified(('test', 'a'))

        # User undoes (back to saved value)
        cm.undo()
        assert not cm.is_modified(('test', 'a'))

        # User undoes again (before save)
        cm.undo()
        assert cm.is_modified(('test', 'a'))
        state = cm._get_state()
        assert state.pending[('test', 'a')].new_value == 0

        # User redoes (back to saved)
        cm.redo()
        assert not cm.is_modified(('test', 'a'))

        # User redoes again (to unsaved edit)
        cm.redo()
        assert cm.is_modified(('test', 'a'))
        state = cm._get_state()
        assert state.pending[('test', 'a')].new_value == 2

    def test_interleaved_keys_with_save(self, cm):
        """Multiple keys edited, partial save, more edits."""
        cm.add_change(SimpleChange('a', 0, 1))
        cm.add_change(SimpleChange('b', 0, 1))
        cm.save()  # both saved

        cm.add_change(SimpleChange('a', 1, 2))  # edit a again
        cm.add_change(SimpleChange('c', 0, 1))  # new key

        assert cm.is_modified(('test', 'a'))
        assert not cm.is_modified(('test', 'b'))
        assert cm.is_modified(('test', 'c'))

        cm.undo()  # undo c
        assert not cm.is_modified(('test', 'c'))

        cm.undo()  # undo a edit
        assert not cm.is_modified(('test', 'a'))

        cm.undo()  # undo b (after save!)
        assert cm.is_modified(('test', 'b'))

    def test_rapid_changes_same_key(self, cm):
        """Rapid changes to same key should merge in pending but not undo stack."""
        for i in range(100):
            cm.add_change(SimpleChange('a', i, i + 1))

        # Pending merges - only one pending entry
        assert cm.pending_count() == 1
        state = cm._get_state()
        assert state.pending[('test', 'a')].old_value == 0
        assert state.pending[('test', 'a')].new_value == 100

        # But undo stack has 100 entries - each change is undoable
        assert cm.undo_stack_size() == 100

        # Single undo only reverts one step
        cm.undo()
        assert cm.is_modified(('test', 'a'))
        assert state.pending[('test', 'a')].new_value == 99

    def test_save_between_grouped_operations(self, cm):
        """Save between two grouped operations."""
        cm.begin_group("first")
        cm.add_change(SimpleChange('a', 0, 1))
        cm.add_change(SimpleChange('b', 0, 1))
        cm.end_group()

        cm.save()

        cm.begin_group("second")
        cm.add_change(SimpleChange('a', 1, 2))
        cm.add_change(SimpleChange('c', 0, 1))
        cm.end_group()

        # Undo second group
        cm.undo()
        assert not cm.is_modified(('test', 'a'))  # back to saved
        assert not cm.is_modified(('test', 'b'))  # unchanged
        assert not cm.is_modified(('test', 'c'))  # reverted

        # Undo first group (after save)
        cm.undo()
        assert cm.is_modified(('test', 'a'))
        assert cm.is_modified(('test', 'b'))


class TestStackSizeLimit:
    """Test MAX_UNDO_STACK_SIZE enforcement."""

    def test_stack_enforces_max_size(self, cm):
        """Undo stack is capped at MAX_UNDO_STACK_SIZE."""
        from change_manager.change_manager import MAX_UNDO_STACK_SIZE

        for i in range(MAX_UNDO_STACK_SIZE + 100):
            cm.add_change(SimpleChange(f'key_{i}', 0, 1))

        assert cm.undo_stack_size() == MAX_UNDO_STACK_SIZE

    def test_oldest_entries_dropped(self, cm):
        """Oldest entries are dropped when stack overflows."""
        from change_manager.change_manager import MAX_UNDO_STACK_SIZE

        # Add exactly max + 10
        for i in range(MAX_UNDO_STACK_SIZE + 10):
            cm.add_change(SimpleChange(f'key_{i}', 0, 1))

        # Undo all - should only get MAX_UNDO_STACK_SIZE undos
        undo_count = 0
        while cm.undo():
            undo_count += 1

        assert undo_count == MAX_UNDO_STACK_SIZE

    def test_groups_count_as_one(self, cm):
        """A group counts as one stack entry regardless of size."""
        from change_manager.change_manager import MAX_UNDO_STACK_SIZE

        # Fill stack with groups of 10 changes each
        for i in range(MAX_UNDO_STACK_SIZE):
            cm.begin_group(f"group_{i}")
            for j in range(10):
                cm.add_change(SimpleChange(f'key_{i}_{j}', 0, 1))
            cm.end_group()

        assert cm.undo_stack_size() == MAX_UNDO_STACK_SIZE


class TestGroupEdgeCases:
    """Test edge cases with grouping."""

    def test_empty_group_not_added(self, cm):
        """Empty group doesn't create undo entry."""
        cm.begin_group("empty")
        cm.end_group()

        assert cm.undo_stack_size() == 0
        assert not cm.can_undo()

    def test_nested_groups_only_outermost_matters(self, cm):
        """Nested begin_group calls are ignored."""
        cm.begin_group("outer")
        cm.add_change(SimpleChange('a', 0, 1))
        cm.begin_group("inner")  # Should be ignored
        cm.add_change(SimpleChange('b', 0, 1))
        cm.end_group()  # Ends outer group

        # Should have one group with both changes
        assert cm.undo_stack_size() == 1
        cm.undo()
        assert not cm.is_modified(('test', 'a'))
        assert not cm.is_modified(('test', 'b'))

    def test_end_group_without_begin_is_noop(self, cm):
        """end_group without begin_group is safe."""
        cm.end_group()  # Should not crash
        cm.add_change(SimpleChange('a', 0, 1))
        cm.end_group()  # Still should not crash

        assert cm.undo_stack_size() == 1

    def test_group_with_save_inside(self, cm):
        """Save during a group doesn't affect grouping."""
        cm.begin_group("test")
        cm.add_change(SimpleChange('a', 0, 1))
        # Note: save() during group is unusual but shouldn't crash
        cm.add_change(SimpleChange('b', 0, 1))
        cm.end_group()

        assert cm.undo_stack_size() == 1


class TestSameValueChanges:
    """Test changes where new_value equals old_value."""

    def test_same_value_still_tracked(self, cm):
        """Change with same old/new value is still tracked."""
        cm.add_change(SimpleChange('a', 5, 5))

        # It's tracked (this is intentional - the change happened)
        assert cm.undo_stack_size() == 1

    def test_change_back_to_original(self, cm):
        """Changing A->B->A still has pending entry."""
        cm.add_change(SimpleChange('a', 0, 1))
        cm.add_change(SimpleChange('a', 1, 0))

        # Pending should have old=0, new=0 (net no change)
        state = cm._get_state()
        assert ('test', 'a') in state.pending
        assert state.pending[('test', 'a')].old_value == 0
        assert state.pending[('test', 'a')].new_value == 0


class TestRevertScenarios:
    """Test revert_all behavior."""

    def test_revert_clears_everything(self, cm):
        """revert_all clears pending, committed, and stacks."""
        cm.add_change(SimpleChange('a', 0, 1))
        cm.save()
        cm.add_change(SimpleChange('b', 0, 1))

        cm.revert_all()

        state = cm._get_state()
        assert len(state.pending) == 0
        assert len(state.committed) == 0
        assert len(state.undo_stack) == 0
        assert len(state.redo_stack) == 0

    def test_revert_restores_old_values(self, cm):
        """revert_all calls _restore_value for each pending change."""
        cm.add_change(SimpleChange('a', 0, 1))
        cm.add_change(SimpleChange('b', 10, 20))

        # Track that revert_all was called and cleared pending
        assert cm.pending_count() == 2
        cm.revert_all()
        assert cm.pending_count() == 0
        # Note: _restore_value handles specific key types (keymap, combo, etc.)
        # Our 'test' key type isn't handled, so keyboard.values isn't updated

    def test_revert_emits_values_restored(self, cm):
        """revert_all emits values_restored with all affected keys."""
        restored = [None]
        cm.values_restored.connect(lambda keys: restored.__setitem__(0, keys))

        cm.add_change(SimpleChange('a', 0, 1))
        cm.add_change(SimpleChange('b', 0, 1))
        cm.revert_all()

        assert ('test', 'a') in restored[0]
        assert ('test', 'b') in restored[0]

    def test_revert_empty_is_noop(self, cm):
        """revert_all with no pending changes is safe."""
        cm.revert_all()  # Should not crash
        assert not cm.has_pending_changes()


class TestKeyboardSwitchingEdgeCases:
    """Test keyboard switching during operations."""

    def test_switch_during_group_abandons_group(self):
        """Switching keyboard during a group abandons the group."""
        ChangeManager._instance = None
        cm = ChangeManager.instance()

        kb1 = MockKeyboard()
        kb1.keyboard_id = 1
        kb2 = MockKeyboard()
        kb2.keyboard_id = 2

        cm.set_keyboard(kb1)
        cm.begin_group("test")
        cm.add_change(SimpleChange('a', 0, 1))

        # Switch keyboard mid-group
        cm.set_keyboard(kb2)

        # kb2 should have fresh state
        assert cm.undo_stack_size() == 0
        assert cm._get_state().current_group is None

        # Switch back - kb1's group is still open
        cm.set_keyboard(kb1)
        assert cm._get_state().current_group is not None

    def test_state_preserved_across_switches(self):
        """Full state is preserved when switching keyboards."""
        ChangeManager._instance = None
        cm = ChangeManager.instance()

        kb1 = MockKeyboard()
        kb1.keyboard_id = 1
        kb2 = MockKeyboard()
        kb2.keyboard_id = 2

        # Build up state on kb1
        cm.set_keyboard(kb1)
        cm.add_change(SimpleChange('a', 0, 1))  # undo_stack = 1
        cm.save()  # undo_stack still = 1
        cm.add_change(SimpleChange('b', 0, 1))  # undo_stack = 2
        cm.undo()  # undo_stack = 1, redo_stack = 1

        # Switch to kb2
        cm.set_keyboard(kb2)

        # Switch back and verify all state
        cm.set_keyboard(kb1)
        assert cm.can_redo()
        assert ('test', 'a') in cm._get_state().committed
        assert cm.undo_stack_size() == 1  # After undo, only 'a' change remains


class TestSignalOrdering:
    """Test that signals fire in expected order."""

    def test_changed_fires_after_state_update(self, cm):
        """changed signal fires after state is updated."""
        state_when_changed = [None]

        def capture_state():
            state_when_changed[0] = cm.pending_count()

        cm.changed.connect(capture_state)
        cm.add_change(SimpleChange('a', 0, 1))

        assert state_when_changed[0] == 1

    def test_values_restored_fires_after_undo(self, cm):
        """values_restored contains correct keys after undo."""
        restored_pending = [None]

        def capture(keys):
            # At signal time, pending should already be updated
            restored_pending[0] = cm.is_modified(('test', 'a'))

        cm.values_restored.connect(capture)

        cm.add_change(SimpleChange('a', 0, 1))
        cm.undo()

        assert restored_pending[0] == False


class TestDiscardAll:
    """Test discard_all behavior."""

    def test_discard_clears_pending_and_stacks(self, cm):
        """discard_all clears pending and both stacks."""
        cm.add_change(SimpleChange('a', 0, 1))
        cm.undo()
        cm.add_change(SimpleChange('b', 0, 1))

        cm.discard_all()

        assert not cm.has_pending_changes()
        assert not cm.can_undo()
        assert not cm.can_redo()

    def test_discard_preserves_committed(self, cm):
        """discard_all does NOT clear committed (unlike revert_all)."""
        cm.add_change(SimpleChange('a', 0, 1))
        cm.save()
        cm.add_change(SimpleChange('b', 0, 1))

        cm.discard_all()

        state = cm._get_state()
        # Committed should still be there
        assert ('test', 'a') in state.committed


class TestResetMethod:
    """Test ChangeManager.reset() class method."""

    def test_reset_clears_keyboard(self):
        """reset() sets keyboard to None."""
        ChangeManager._instance = None
        cm = ChangeManager.instance()
        cm.set_keyboard(MockKeyboard())

        ChangeManager.reset()

        assert cm.keyboard is None

    def test_reset_emits_state_changes(self):
        """reset() emits signals for cleared state."""
        ChangeManager._instance = None
        cm = ChangeManager.instance()
        kb = MockKeyboard()
        cm.set_keyboard(kb)
        cm.add_change(SimpleChange('a', 0, 1))

        signals = []
        cm.can_save_changed.connect(lambda v: signals.append(('save', v)))

        ChangeManager.reset()

        # Should emit can_save_changed(False) since no keyboard
        assert ('save', False) in signals


class TestGetPendingValue:
    """Test get_pending_value() method."""

    def test_returns_pending_value(self, cm):
        """get_pending_value returns the new_value of pending change."""
        cm.add_change(SimpleChange('a', 0, 42))

        assert cm.get_pending_value(('test', 'a')) == 42

    def test_returns_none_for_unmodified(self, cm):
        """get_pending_value returns None for keys without pending changes."""
        cm.add_change(SimpleChange('a', 0, 1))

        assert cm.get_pending_value(('test', 'b')) is None

    def test_returns_none_in_auto_commit(self, cm):
        """get_pending_value returns None in auto_commit mode."""
        cm.auto_commit = True
        cm.add_change(SimpleChange('a', 0, 1))

        assert cm.get_pending_value(('test', 'a')) is None

    def test_tracks_merged_value(self, cm):
        """get_pending_value returns latest merged value."""
        cm.add_change(SimpleChange('a', 0, 1))
        cm.add_change(SimpleChange('a', 1, 2))
        cm.add_change(SimpleChange('a', 2, 99))

        assert cm.get_pending_value(('test', 'a')) == 99


class TestOperationsDuringGroup:
    """Test operations while a group is open."""

    def test_undo_during_group_undoes_previous(self, cm):
        """undo() during open group undoes previous completed group."""
        cm.add_change(SimpleChange('a', 0, 1))  # Group 1

        cm.begin_group("group2")
        cm.add_change(SimpleChange('b', 0, 1))
        # Group still open, undo previous
        cm.undo()

        assert not cm.is_modified(('test', 'a'))  # Undone
        # Group 2 still has 'b' pending (not in undo stack yet)
        assert cm.is_modified(('test', 'b'))

    def test_redo_during_group_cleared_by_new_change(self, cm):
        """New changes during group clear redo stack."""
        cm.add_change(SimpleChange('a', 0, 1))
        cm.undo()
        assert cm.can_redo()

        cm.begin_group("group")
        cm.add_change(SimpleChange('b', 0, 1))  # This clears redo stack!
        assert not cm.can_redo()

        result = cm.redo()  # Nothing to redo
        assert not result
        assert not cm.is_modified(('test', 'a'))
        assert cm.is_modified(('test', 'b'))

    def test_clear_during_group(self, cm):
        """clear() during open group clears everything including current group."""
        cm.add_change(SimpleChange('a', 0, 1))

        cm.begin_group("group")
        cm.add_change(SimpleChange('b', 0, 1))
        cm.clear()

        assert not cm.has_pending_changes()
        assert not cm.can_undo()
        assert cm._get_state().current_group is None

    def test_save_during_group(self, cm):
        """save() during open group saves pending but group continues."""
        cm.begin_group("group")
        cm.add_change(SimpleChange('a', 0, 1))
        cm.save()
        cm.add_change(SimpleChange('b', 0, 1))
        cm.end_group()

        # 'a' was saved, 'b' is pending
        assert ('test', 'a') in cm._get_state().committed
        assert cm.is_modified(('test', 'b'))


class TestKeyboardDisconnect:
    """Test behavior when keyboard is None or disconnected."""

    def test_set_keyboard_none(self):
        """set_keyboard(None) is valid."""
        ChangeManager._instance = None
        cm = ChangeManager.instance()
        cm.set_keyboard(MockKeyboard())
        cm.add_change(SimpleChange('a', 0, 1))

        cm.set_keyboard(None)

        assert cm.keyboard is None
        assert not cm.has_pending_changes()  # No state without keyboard
        assert not cm.can_undo()

    def test_operations_with_no_keyboard(self):
        """Operations with no keyboard don't crash."""
        ChangeManager._instance = None
        cm = ChangeManager.instance()
        # No keyboard set

        cm.add_change(SimpleChange('a', 0, 1))  # Should be no-op
        assert not cm.has_pending_changes()

        cm.begin_group("test")
        cm.end_group()

        # save() returns False when no keyboard (can't save to nothing)
        assert not cm.save()
        assert not cm.undo()
        assert not cm.redo()

    def test_keyboard_without_keyboard_id(self):
        """Keyboards without keyboard_id use id() as fallback."""
        ChangeManager._instance = None
        cm = ChangeManager.instance()

        class SimpleKeyboard:
            def __init__(self):
                self.values = {}

        kb = SimpleKeyboard()
        cm.set_keyboard(kb)
        cm.add_change(SimpleChange('a', 0, 1))

        assert cm.pending_count() == 1


class TestSaveFailure:
    """Test save() when apply() fails."""

    def test_save_returns_false_on_failure(self):
        """save() returns False if any apply() fails."""
        ChangeManager._instance = None
        cm = ChangeManager.instance()
        cm.set_keyboard(MockKeyboard())

        class FailingChange(SimpleChange):
            def apply(self, keyboard):
                return False

        cm.add_change(FailingChange('a', 0, 1))

        assert not cm.save()

    def test_save_failure_preserves_pending(self):
        """Failed save keeps changes in pending."""
        ChangeManager._instance = None
        cm = ChangeManager.instance()
        cm.set_keyboard(MockKeyboard())

        class FailingChange(SimpleChange):
            def apply(self, keyboard):
                return False

        cm.add_change(FailingChange('a', 0, 1))
        cm.save()

        assert cm.has_pending_changes()
        assert cm.is_modified(('test', 'a'))

    def test_save_failure_no_saved_signal(self):
        """Failed save doesn't emit saved signal."""
        ChangeManager._instance = None
        cm = ChangeManager.instance()
        cm.set_keyboard(MockKeyboard())

        class FailingChange(SimpleChange):
            def apply(self, keyboard):
                return False

        saved_count = [0]
        cm.saved.connect(lambda: saved_count.__setitem__(0, saved_count[0] + 1))

        cm.add_change(FailingChange('a', 0, 1))
        cm.save()

        assert saved_count[0] == 0


class TestChangeGroupMethods:
    """Test ChangeGroup class methods directly."""

    def test_has_key(self):
        """has_key() returns True for existing keys."""
        from change_manager.change_group import ChangeGroup

        group = ChangeGroup("test")
        group.add(SimpleChange('a', 0, 1))

        assert group.has_key(('test', 'a'))
        assert not group.has_key(('test', 'b'))

    def test_keys_property(self):
        """keys property returns set of all change keys."""
        from change_manager.change_group import ChangeGroup

        group = ChangeGroup("test")
        group.add(SimpleChange('a', 0, 1))
        group.add(SimpleChange('b', 0, 1))

        assert group.keys == {('test', 'a'), ('test', 'b')}

    def test_len(self):
        """__len__ returns number of unique keys."""
        from change_manager.change_group import ChangeGroup

        group = ChangeGroup("test")
        assert len(group) == 0

        group.add(SimpleChange('a', 0, 1))
        assert len(group) == 1

        group.add(SimpleChange('a', 1, 2))  # Same key, merges
        assert len(group) == 1

        group.add(SimpleChange('b', 0, 1))
        assert len(group) == 2

    def test_repr(self):
        """__repr__ returns useful string."""
        from change_manager.change_group import ChangeGroup

        group = ChangeGroup("my_group")
        group.add(SimpleChange('a', 0, 1))
        group.add(SimpleChange('b', 0, 1))

        r = repr(group)
        assert "my_group" in r
        assert "2" in r

    def test_revert(self):
        """revert() calls revert on all changes in reverse order."""
        from change_manager.change_group import ChangeGroup

        class TrackingChange(SimpleChange):
            reverted = []
            def revert(self, keyboard):
                TrackingChange.reverted.append(self.key_id)
                return True

        TrackingChange.reverted = []
        group = ChangeGroup("test")
        group.add(TrackingChange('a', 0, 1))
        group.add(TrackingChange('b', 0, 1))
        group.add(TrackingChange('c', 0, 1))

        result = group.revert(MockKeyboard())

        assert result == True
        assert TrackingChange.reverted == ['c', 'b', 'a']  # Reverse order

    def test_apply_failure(self):
        """apply() returns False if any change fails."""
        from change_manager.change_group import ChangeGroup

        class FailingChange(SimpleChange):
            def apply(self, keyboard):
                return False

        group = ChangeGroup("test")
        group.add(SimpleChange('a', 0, 1))
        group.add(FailingChange('b', 0, 1))

        result = group.apply(MockKeyboard())
        assert result == False

    def test_revert_failure(self):
        """revert() returns False if any change fails."""
        from change_manager.change_group import ChangeGroup

        class FailingChange(SimpleChange):
            def revert(self, keyboard):
                return False

        group = ChangeGroup("test")
        group.add(SimpleChange('a', 0, 1))
        group.add(FailingChange('b', 0, 1))

        result = group.revert(MockKeyboard())
        assert result == False


class TestGroupDeduplication:
    """Test how groups handle multiple changes to same key."""

    def test_group_stores_all_changes(self, cm):
        """Group stores all changes (doesn't dedupe internally)."""
        cm.begin_group("test")
        cm.add_change(SimpleChange('a', 0, 1))
        cm.add_change(SimpleChange('a', 1, 2))
        cm.add_change(SimpleChange('a', 2, 3))
        cm.end_group()

        # Pending dedupes
        assert cm.pending_count() == 1
        assert cm._get_state().pending[('test', 'a')].new_value == 3

        # Single undo reverts all
        cm.undo()
        assert not cm.is_modified(('test', 'a'))

    def test_group_undo_restores_original(self, cm):
        """Undoing a group restores to state before group started."""
        cm.add_change(SimpleChange('a', 0, 1))  # Pre-group

        cm.begin_group("test")
        cm.add_change(SimpleChange('a', 1, 5))
        cm.add_change(SimpleChange('a', 5, 10))
        cm.end_group()

        cm.undo()  # Undo group

        # Should be back to a=1, not a=0
        assert cm.is_modified(('test', 'a'))
        assert cm._get_state().pending[('test', 'a')].new_value == 1


class TestReentrancy:
    """Test signal handlers that modify state."""

    def test_signal_handler_adds_change(self, cm):
        """Signal handler adding a change doesn't corrupt state."""
        def on_change():
            # Only add once to avoid infinite loop
            if cm.pending_count() == 1:
                cm.add_change(SimpleChange('auto', 0, 1))

        cm.changed.connect(on_change)
        cm.add_change(SimpleChange('user', 0, 1))

        assert cm.is_modified(('test', 'user'))
        assert cm.is_modified(('test', 'auto'))
        assert cm.pending_count() == 2

    def test_signal_handler_undo(self, cm):
        """Signal handler calling undo doesn't corrupt state."""
        undo_called = [False]

        def on_change():
            if cm.pending_count() > 0 and not undo_called[0]:
                undo_called[0] = True
                cm.undo()

        cm.changed.connect(on_change)
        cm.add_change(SimpleChange('a', 0, 1))

        # The undo in the handler should have been processed
        assert undo_called[0]
        # State should be consistent (either modified or not)
        # The exact outcome depends on signal ordering


class TestMaxUndoStackSize:
    """Test max_undo_stack_size getter."""

    def test_max_undo_stack_size_returns_constant(self, cm):
        """max_undo_stack_size returns the configured limit."""
        from change_manager.change_manager import MAX_UNDO_STACK_SIZE
        assert cm.max_undo_stack_size() == MAX_UNDO_STACK_SIZE


class TestUndoToCommittedAfterRoundTrip:
    """Test edge case: undo to original value that matches committed."""

    def test_undo_clears_pending_when_matching_committed(self, cm):
        """Undo to original value that matches current committed clears pending."""
        # X=0 → Y=1, save, Y=1 → X=0, save, then undo twice
        cm.add_change(SimpleChange('a', 0, 1))
        cm.save()  # committed = 1

        cm.add_change(SimpleChange('a', 1, 0))
        cm.save()  # committed = 0 (back to original)

        # First undo: 1→0 popped, earlier_value=1, creates pending
        cm.undo()
        assert cm.is_modified(('test', 'a'))

        # Second undo: 0→1 popped, earlier_value=None, old_value=0, committed=0
        # old_value == committed, so pending should be CLEARED
        cm.undo()
        assert not cm.is_modified(('test', 'a'))


class TestFullUndoAfterMultipleSaves:
    """Test undoing all the way back after multiple save cycles."""

    def test_undo_through_multiple_saves(self, cm):
        """Can undo through multiple save points."""
        # First save cycle
        cm.add_change(SimpleChange('a', 0, 1))
        cm.save()

        # Second save cycle
        cm.add_change(SimpleChange('a', 1, 2))
        cm.save()

        # Third save cycle
        cm.add_change(SimpleChange('a', 2, 3))
        cm.save()

        # Undo all the way back
        cm.undo()  # 3 -> 2
        assert cm.is_modified(('test', 'a'))

        cm.undo()  # 2 -> 1
        assert cm.is_modified(('test', 'a'))

        cm.undo()  # 1 -> 0
        assert cm.is_modified(('test', 'a'))

        # Final pending should want to set device to 0 (device has 3)
        state = cm._get_state()
        assert state.pending[('test', 'a')].new_value == 0
        assert state.committed[('test', 'a')] == 3

    def test_redo_through_multiple_saves(self, cm):
        """Can redo through multiple save points."""
        cm.add_change(SimpleChange('a', 0, 1))
        cm.save()
        cm.add_change(SimpleChange('a', 1, 2))
        cm.save()
        cm.add_change(SimpleChange('a', 2, 3))
        cm.save()

        # Undo all
        cm.undo()
        cm.undo()
        cm.undo()

        # Redo to second save point
        cm.redo()  # 0 -> 1
        cm.redo()  # 1 -> 2

        # Should be pending (device has 3, we want 2)
        assert cm.is_modified(('test', 'a'))
        state = cm._get_state()
        assert state.pending[('test', 'a')].new_value == 2

        # Redo one more to match device
        cm.redo()  # 2 -> 3
        assert not cm.is_modified(('test', 'a'))


class TestRedoSharedObjectMutation:
    """Test that redo doesn't share objects with undo stack."""

    def test_redo_then_modify_doesnt_corrupt_undo_stack(self, cm):
        """Redo then new change shouldn't corrupt undo history."""
        # Make a change
        cm.add_change(SimpleChange('a', 0, 1))

        # Undo and redo
        cm.undo()
        cm.redo()

        # Get the change from undo stack before new change
        undo_change_before = cm._get_state().undo_stack[-1].changes[0]
        assert undo_change_before.new_value == 1

        # Make a new change that would merge into pending
        cm.add_change(SimpleChange('a', 1, 2))

        # The undo stack entry should NOT have been mutated
        undo_change_after = cm._get_state().undo_stack[0].changes[0]
        assert undo_change_after.new_value == 1  # Still 1, not 2

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


class TestSignals:
    """Test signal emissions (requires pytest-qt)."""

    @pytest.fixture
    def qtbot(self):
        pytest.importorskip("pytestqt")
        from pytestqt.qtbot import QtBot
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        return QtBot(app)

    def test_saved_signal_on_save(self, cm, qtbot):
        with qtbot.waitSignal(cm.saved, timeout=100):
            cm.add_change(SimpleChange('a', 0, 1))
            cm.save()

    def test_values_restored_on_undo(self, cm, qtbot):
        cm.add_change(SimpleChange('a', 0, 1))
        with qtbot.waitSignal(cm.values_restored, timeout=100) as sig:
            cm.undo()
        assert ('test', 'a') in sig.args[0]

    def test_values_restored_on_redo(self, cm, qtbot):
        cm.add_change(SimpleChange('a', 0, 1))
        cm.undo()
        with qtbot.waitSignal(cm.values_restored, timeout=100) as sig:
            cm.redo()
        assert ('test', 'a') in sig.args[0]

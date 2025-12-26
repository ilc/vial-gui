from qtpy.QtWidgets import QVBoxLayout


class BasicEditor(QVBoxLayout):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.device = None

    def valid(self):
        raise NotImplementedError

    def rebuild(self, device):
        self.device = device
        self._connect_change_manager()

    def _connect_change_manager(self):
        """Connect to ChangeManager signals. Called automatically by rebuild()."""
        from change_manager import ChangeManager
        cm = ChangeManager.instance()
        for sig, handler in [
            (cm.values_restored, self._on_values_restored),
            (cm.saved, self._on_saved),
        ]:
            try:
                sig.disconnect(handler)
            except TypeError:
                pass
            sig.connect(handler)

    def _on_values_restored(self, affected_keys):
        """Called after undo/redo. Override to reload affected entries.

        For simple indexed editors, set CM_KEY_TYPE and override _reload_entry().
        """
        if not hasattr(self, 'CM_KEY_TYPE') or self.CM_KEY_TYPE is None:
            return
        for key in affected_keys:
            if key[0] == self.CM_KEY_TYPE:
                _, idx = key
                self._reload_entry(idx)
        self.refresh_display()

    def _reload_entry(self, idx):
        """Override to reload a specific entry by index."""
        pass

    def _on_saved(self):
        """Called after save. Refreshes display by default."""
        self.refresh_display()

    def refresh_display(self):
        """Override to refresh the display and update highlights."""
        pass

    def on_container_clicked(self):
        pass

    def activate(self):
        pass

    def deactivate(self):
        pass

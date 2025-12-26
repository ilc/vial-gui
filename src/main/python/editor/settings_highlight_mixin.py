# SPDX-License-Identifier: GPL-2.0-or-later
"""Mixin for per-field modified highlighting in settings editors (QMK Settings, Svalboard)."""


class SettingsHighlightMixin:
    """Mixin for settings editors with per-field modified highlighting.

    Unlike indexed-entry editors (combos, tap dance, etc.) that highlight entire entries,
    settings editors highlight individual fields/options when they have uncommitted changes.
    """

    def set_modified_style(self, widget, modified, object_name=None):
        """Apply modified/normal border style to a widget.

        Args:
            widget: The widget to style
            modified: True for highlight, False for normal
            object_name: If set, use #object_name { } selector (for QFrame etc.)
        """
        border_color = "palette(link)" if modified else "transparent"
        if object_name:
            widget.setStyleSheet(f"#{object_name} {{ border: 2px solid {border_color}; }}")
        else:
            widget.setStyleSheet(f"border: 2px solid {border_color};")

# SPDX-License-Identifier: GPL-2.0-or-later

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor

themes = [
    ("Light", {
        QPalette.ColorRole.Window: "#ffefebe7",
        QPalette.ColorRole.WindowText: "#ff000000",
        QPalette.ColorRole.Base: "#ffffffff",
        QPalette.ColorRole.AlternateBase: "#fff7f5f3",
        QPalette.ColorRole.ToolTipBase: "#ffffffdc",
        QPalette.ColorRole.ToolTipText: "#ff000000",
        QPalette.ColorRole.Text: "#ff000000",
        QPalette.ColorRole.Button: "#ffefebe7",
        QPalette.ColorRole.ButtonText: "#ff000000",
        QPalette.ColorRole.BrightText: "#ffffffff",
        QPalette.ColorRole.Link: "#ff0000ff",
        QPalette.ColorRole.Highlight: "#ff308cc6",
        QPalette.ColorRole.HighlightedText: "#ffffffff",
        (QPalette.ColorGroup.Active, QPalette.ColorRole.Button): "#ffefebe7",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText): "#ffbebebe",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText): "#ffbebebe",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text): "#ffbebebe",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.Light): "#ffffffff",
    }),
    ("Dark", {
        QPalette.ColorRole.Window: "#353535",
        QPalette.ColorRole.WindowText: "#ffffff",
        QPalette.ColorRole.Base: "#232323",
        QPalette.ColorRole.AlternateBase: "#353535",
        QPalette.ColorRole.ToolTipBase: "#191919",
        QPalette.ColorRole.ToolTipText: "#ffffff",
        QPalette.ColorRole.Text: "#ffffff",
        QPalette.ColorRole.Button: "#353535",
        QPalette.ColorRole.ButtonText: "#ffffff",
        QPalette.ColorRole.BrightText: "#ff0000",
        QPalette.ColorRole.Link: "#f7a948",
        QPalette.ColorRole.Highlight: "#bababa",
        QPalette.ColorRole.HighlightedText: "#232323",
        (QPalette.ColorGroup.Active, QPalette.ColorRole.Button): "#353535",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText): "#808080",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText): "#808080",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text): "#808080",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.Light): "#353535",
    }),
    ("Arc", {
        QPalette.ColorRole.Window: "#353945",
        QPalette.ColorRole.WindowText: "#d3dae3",
        QPalette.ColorRole.Base: "#353945",
        QPalette.ColorRole.AlternateBase: "#404552",
        QPalette.ColorRole.ToolTipBase: "#4B5162",
        QPalette.ColorRole.ToolTipText: "#d3dae3",
        QPalette.ColorRole.Text: "#d3dae3",
        QPalette.ColorRole.Button: "#353945",
        QPalette.ColorRole.ButtonText: "#d3dae3",
        QPalette.ColorRole.BrightText: "#5294e2",
        QPalette.ColorRole.Link: "#89b1e0",
        QPalette.ColorRole.Highlight: "#5294e2",
        QPalette.ColorRole.HighlightedText: "#d3dae3",
        (QPalette.ColorGroup.Active, QPalette.ColorRole.Button): "#353945",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText): "#d3dae3",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText): "#d3dae3",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text): "#d3dae3",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.Light): "#404552",
    }),
    ("Nord", {
        QPalette.ColorRole.Window: "#2e3440",
        QPalette.ColorRole.WindowText: "#eceff4",
        QPalette.ColorRole.Base: "#2e3440",
        QPalette.ColorRole.AlternateBase: "#434c5e",
        QPalette.ColorRole.ToolTipBase: "#4c566a",
        QPalette.ColorRole.ToolTipText: "#eceff4",
        QPalette.ColorRole.Text: "#eceff4",
        QPalette.ColorRole.Button: "#2e3440",
        QPalette.ColorRole.ButtonText: "#eceff4",
        QPalette.ColorRole.BrightText: "#88c0d0",
        QPalette.ColorRole.Link: "#88c0d0",
        QPalette.ColorRole.Highlight: "#88c0d0",
        QPalette.ColorRole.HighlightedText: "#eceff4",
        (QPalette.ColorGroup.Active, QPalette.ColorRole.Button): "#2e3440",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText): "#eceff4",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText): "#eceff4",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text): "#eceff4",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.Light): "#88c0d0",
    }),
    ("Olivia", {
        QPalette.ColorRole.Window: "#181818",
        QPalette.ColorRole.WindowText: "#d9d9d9",
        QPalette.ColorRole.Base: "#181818",
        QPalette.ColorRole.AlternateBase: "#2c2c2c",
        QPalette.ColorRole.ToolTipBase: "#363636 ",
        QPalette.ColorRole.ToolTipText: "#d9d9d9",
        QPalette.ColorRole.Text: "#d9d9d9",
        QPalette.ColorRole.Button: "#181818",
        QPalette.ColorRole.ButtonText: "#d9d9d9",
        QPalette.ColorRole.BrightText: "#fabcad",
        QPalette.ColorRole.Link: "#fabcad",
        QPalette.ColorRole.Highlight: "#fabcad",
        QPalette.ColorRole.HighlightedText: "#2c2c2c",
        (QPalette.ColorGroup.Active, QPalette.ColorRole.Button): "#181818",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText): "#d9d9d9",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText): "#d9d9d9",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text): "#d9d9d9",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.Light): "#fabcad",
    }),
    ("Dracula", {
        QPalette.ColorRole.Window: "#282a36",
        QPalette.ColorRole.WindowText: "#f8f8f2",
        QPalette.ColorRole.Base: "#282a36",
        QPalette.ColorRole.AlternateBase: "#44475a",
        QPalette.ColorRole.ToolTipBase: "#6272a4",
        QPalette.ColorRole.ToolTipText: "#f8f8f2",
        QPalette.ColorRole.Text: "#f8f8f2",
        QPalette.ColorRole.Button: "#282a36",
        QPalette.ColorRole.ButtonText: "#f8f8f2",
        QPalette.ColorRole.BrightText: "#8be9fd",
        QPalette.ColorRole.Link: "#8be9fd",
        QPalette.ColorRole.Highlight: "#8be9fd",
        QPalette.ColorRole.HighlightedText: "#f8f8f2",
        (QPalette.ColorGroup.Active, QPalette.ColorRole.Button): "#282a36",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText): "#f8f8f2",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText): "#f8f8f2",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text): "#f8f8f2",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.Light): "#8be9fd",
    }),
    ("Bliss", {
        QPalette.ColorRole.Window: "#343434",
        QPalette.ColorRole.WindowText: "#cbc8c9",
        QPalette.ColorRole.Base: "#343434",
        QPalette.ColorRole.AlternateBase: "#3b3b3b",
        QPalette.ColorRole.ToolTipBase: "#424242",
        QPalette.ColorRole.ToolTipText: "#cbc8c9",
        QPalette.ColorRole.Text: "#cbc8c9",
        QPalette.ColorRole.Button: "#343434",
        QPalette.ColorRole.ButtonText: "#cbc8c9",
        QPalette.ColorRole.BrightText: "#f5d1c8",
        QPalette.ColorRole.Link: "#f5d1c8",
        QPalette.ColorRole.Highlight: "#f5d1c8",
        QPalette.ColorRole.HighlightedText: "#424242",
        (QPalette.ColorGroup.Active, QPalette.ColorRole.Button): "#343434",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText): "#cbc8c9",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText): "#cbc8c9",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text): "#cbc8c9",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.Light): "#f5d1c8",
    }),
]

palettes = dict()

for name, colors in themes:
    palette = QPalette()
    for role, color in colors.items():
        if isinstance(role, tuple):
            (cg, cr) = role
            palette.setColor(cg, cr, QColor(color))
        else:
            palette.setColor(role, QColor(color))
    palettes[name] = palette


class Theme:

    theme = ""

    @classmethod
    def set_theme(cls, theme):
        cls.theme = theme
        if theme in palettes:
            QApplication.setPalette(palettes[theme])
            QApplication.setStyle("Fusion")
        # For default/system theme, do nothing
        # User will have to restart the application for it to be applied

    @classmethod
    def get_theme(cls):
        return cls.theme

    @classmethod
    def mask_light_factor(cls):
        if cls.theme == "Light":
            return 103
        return 150

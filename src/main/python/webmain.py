# SPDX-License-Identifier: GPL-2.0-or-later
import os

import traceback

from qtpy import QtWidgets, QtCore
from qtpy.QtCore import Signal, Qt

import sys
import json

from main_window import MainWindow
import storage


# http://timlehr.com/python-exception-hooks-with-qt-message-box/
from util import init_logger

window = None
_web_theme = "Dark"

def set_theme(theme):
    """Called from JavaScript to set the theme before main() is called"""
    global _web_theme
    _web_theme = theme

def init_storage(settings_json):
    """Called from JavaScript to initialize storage with localStorage values."""
    try:
        settings = json.loads(settings_json)
    except (json.JSONDecodeError, TypeError):
        settings = {}
    storage.init(settings)


def show_exception_box(log_msg):
    if QtWidgets.QApplication.instance() is not None:
        global errorbox

        errorbox = QtWidgets.QMessageBox()
        errorbox.setText(log_msg)
        errorbox.setModal(True)
        errorbox.show()


class UncaughtHook(QtCore.QObject):
    _exception_caught = Signal(object)

    def __init__(self, *args, **kwargs):
        super(UncaughtHook, self).__init__(*args, **kwargs)

        # this registers the exception_hook() function as hook with the Python interpreter
        sys._excepthook = sys.excepthook
        sys.excepthook = self.exception_hook

        # connect signal to execute the message box function always on main thread
        self._exception_caught.connect(show_exception_box)

    def exception_hook(self, exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            # ignore keyboard interrupt to support console applications
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
        else:
            log_msg = '\n'.join([''.join(traceback.format_tb(exc_traceback)),
                                 '{0}: {1}'.format(exc_type.__name__, exc_value)])

            # trigger message box show
            self._exception_caught.emit(log_msg)
        sys._excepthook(exc_type, exc_value, exc_traceback)


def web_get_resource(name):
    return "/usr/local/" + name


def main(app):
    font = app.font()
    font.setPointSize(10)
    app.setFont(font)

    app.get_resource = web_get_resource
    with open(app.get_resource("build_settings.json"), "r") as inf:
        app.build_settings = json.loads(inf.read())
    qt_exception_hook = UncaughtHook()

    global window
    window = MainWindow(app)
    # Fullscreen frameless for web
    window.setWindowFlags(Qt.FramelessWindowHint)
    window.setStyleSheet("QMainWindow { background-color: #2d2d2d; }")
    window.showFullScreen()
    app.processEvents()

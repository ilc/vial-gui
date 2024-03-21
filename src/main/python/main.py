# SPDX-License-Identifier: GPL-2.0-or-later
import ssl
import certifi
import os
if ssl.get_default_verify_paths().cafile is None:
    os.environ['SSL_CERT_FILE'] = certifi.where()

import traceback

from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtCore import pyqtSignal
#import qdarktheme
#qdarktheme.enable_hi_dpi()

from functools import cached_property
#from fbs_runtime.application_context.PyQt6 import ApplicationContext

import sys

from main_window import MainWindow


# http://timlehr.com/python-exception-hooks-with-qt-message-box/
from util import init_logger

class SimpleApplicationContext:
    def __init__(self):
        # Determine if the application is frozen (compiled with Nuitka)
        self.is_frozen = hasattr(sys, 'frozen') and sys.frozen

        # Set the base path depending on the state (frozen or not)
        if self.is_frozen:
            # If the application is compiled, the base path is the folder containing the executable
            self.base_path = os.path.dirname(sys.executable)
        else:
            # If running from source, the base path is the directory of this script
            self.base_path = os.path.dirname(os.path.abspath(__file__))

    def get_resource(self, relative_path):
        """
        Constructs an absolute path to a resource.
        """
        return os.path.join(self.base_path, relative_path)

def show_exception_box(log_msg):
    if QtWidgets.QApplication.instance() is not None:
        errorbox = QtWidgets.QMessageBox()
        errorbox.setText(log_msg)
        errorbox.exec()


class UncaughtHook(QtCore.QObject):
    _exception_caught = pyqtSignal(object)

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

class VialApplicationContext(SimpleApplicationContext):
    @cached_property
    def app(self):
        # Override the app definition in order to set WM_CLASS.
        result = QtWidgets.QApplication(sys.argv)
        result.setApplicationName("Vial")
        result.setOrganizationDomain("vial.today")

        #TODO: Qt sets applicationVersion on non-Linux platforms if the exe/pkg metadata is correctly configured.
        # https://doc.qt.io/qt-5/qcoreapplication.html#applicationVersion-prop
        # Verify it is, and only set manually on Linux.
        #if sys.platform.startswith("linux"):
        result.setApplicationVersion("0.7.x-ilc")
        return result

if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == "--linux-recorder":
        from linux_keystroke_recorder import linux_keystroke_recorder

        linux_keystroke_recorder()
    else:
        appctxt = VialApplicationContext()       # 1. Instantiate ApplicationContext
        q = appctxt.app
        init_logger()
        qt_exception_hook = UncaughtHook()
        window = MainWindow(appctxt)
        window.setWindowIcon(QtGui.QIcon(appctxt.get_resource("icons/icon.ico")))
        window.show()
#        apply_stylesheet(appctxt.app, theme="dark_yellow.xml")
#        qdarktheme.enable_hi_dpi()
        exit_code = appctxt.app.exec()      # 2. Invoke appctxt.app.exec()
        sys.exit(exit_code)

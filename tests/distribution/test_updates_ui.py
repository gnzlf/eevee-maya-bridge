"""Exercise the actual update button in an offscreen Qt event loop when Qt is installed."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys
import threading
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
try:
    from PySide2 import QtCore,QtWidgets
    from eevee_maya import updates_ui
except ImportError:
    QtWidgets=None


@unittest.skipIf(QtWidgets is None,'Requires Maya Python and PySide2')
class UpdateButton(unittest.TestCase):
    def test_click_downloads_on_worker_and_launches_on_ui_thread(self):
        app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        main_thread=threading.get_ident();workers=[];launched=[]
        update={'version':'0.6.2','notes':'Test release'}
        def download(value,callback):
            workers.append(threading.get_ident());callback(100);return Path('verified-installer.exe')
        def launch(path):launched.append((path,threading.get_ident()))
        with mock.patch.object(updates_ui.updates,'download',download),mock.patch.object(updates_ui.updates,'launch',launch):
            updates_ui.show(update)
            button=updates_ui._dialog.findChild(QtWidgets.QPushButton)
            self.assertIn('0.6.2',button.text());button.click()
            loop=QtCore.QEventLoop();timer=QtCore.QTimer();timer.setInterval(10)
            timer.timeout.connect(lambda:loop.quit() if launched else None);timer.start()
            QtCore.QTimer.singleShot(5000,loop.quit);loop.exec_();timer.stop()
            self.assertEqual(len(launched),1);self.assertEqual(launched[0][1],main_thread)
            self.assertNotEqual(workers[0],main_thread)
            self.assertEqual(updates_ui._dialog.findChild(QtWidgets.QProgressBar).value(),100)
            updates_ui._dialog.close();app.processEvents()


if __name__=='__main__':unittest.main()

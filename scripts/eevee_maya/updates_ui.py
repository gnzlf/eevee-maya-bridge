"""Nonblocking Maya menu and one-click release installation."""
import maya.cmds as cmds
import threading
try:
    from PySide6 import QtCore,QtWidgets
except ImportError:
    from PySide2 import QtCore,QtWidgets
from . import updates,__version__

_menu=None
_worker=None
_dialog=None
_available=None


class Job(QtCore.QObject):
    completed=QtCore.Signal(object)
    failed=QtCore.Signal(str)
    progress=QtCore.Signal(int)
    def __init__(self,function):
        super().__init__();self.function=function;self.thread=None
    def isRunning(self):return self.thread is not None and self.thread.is_alive()
    def start(self):
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def run(self):
        try:self.completed.emit(self.function(self.progress.emit))
        except Exception as error:self.failed.emit(str(error))


def install_menu(parent):
    global _menu
    cmds.menuItem(divider=True,parent=parent)
    _menu=cmds.menuItem(parent=parent,label='Buscar actualizaciones… ('+__version__+')',command=lambda *_:check(True))
    QtCore.QTimer.singleShot(5000,lambda:check(False))


def set_menu(label):
    if _menu and cmds.menuItem(_menu,exists=True):cmds.menuItem(_menu,edit=True,label=label)


def check(show_dialog=True):
    global _worker,_available
    if _worker and _worker.isRunning():return
    def done(value):
        global _available
        _available=value
        set_menu('Nueva versión '+value['version']+' disponible…' if value else 'Buscar actualizaciones… ('+__version__+')')
        if show_dialog:show(value)
    def error(message):
        set_menu('Buscar actualizaciones… ('+__version__+')')
        if show_dialog:QtWidgets.QMessageBox.warning(None,'Actualizaciones de Eevee','No se pudo consultar GitHub.\n'+message)
    set_menu('Buscando actualizaciones…')
    # Read Maya state on the UI thread before dispatching HTTP work.
    cmds_maya_version=cmds.about(version=True).split('.')[0]
    _worker=Job(lambda _:updates.check(maya_version=cmds_maya_version))
    _worker.completed.connect(done);_worker.failed.connect(error);_worker.start()


def show(value):
    global _dialog
    if not value:
        QtWidgets.QMessageBox.information(None,'Eevee Maya Bridge','Tienes la versión '+__version__+'. No hay una versión nueva publicada.');return
    if _dialog:_dialog.close()
    dialog=_dialog=QtWidgets.QDialog();dialog.setWindowTitle('Eevee · Nueva versión disponible');dialog.resize(520,350)
    layout=QtWidgets.QVBoxLayout(dialog)
    heading=QtWidgets.QLabel('Eevee Maya Bridge '+value['version']+' disponible');layout.addWidget(heading)
    notes=QtWidgets.QTextBrowser();notes.setPlainText(value['notes']);layout.addWidget(notes)
    layout.addWidget(QtWidgets.QLabel('Se instalará en una carpeta nueva. Se activará al reiniciar Maya.'))
    progress=QtWidgets.QProgressBar();progress.hide();layout.addWidget(progress)
    status=QtWidgets.QLabel('');status.setWordWrap(True);layout.addWidget(status)
    button=QtWidgets.QPushButton('Descargar e instalar '+value['version']);layout.addWidget(button)
    def install():
        global _worker
        if _worker and _worker.isRunning():return
        button.setEnabled(False);progress.show();status.setText('Descargando instalador verificado…')
        def done(path):
            try:updates.launch(path);status.setText('Instalador abierto. Completa la instalación y reinicia Maya cuando termines de trabajar.')
            except Exception as error:failed(str(error))
        def failed(message):status.setText(message);button.setEnabled(True)
        _worker=Job(lambda callback:updates.download(value,callback))
        _worker.progress.connect(progress.setValue);_worker.completed.connect(done);_worker.failed.connect(failed);_worker.start()
    button.clicked.connect(install);dialog.show()

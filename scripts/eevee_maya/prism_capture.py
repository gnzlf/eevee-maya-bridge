"""Optional Prism adapter; scope command routing to its playblast operation."""
from contextlib import contextmanager
from pathlib import Path
import functools
import os
import subprocess
import sys
import tempfile

_binding = None
_timer = None


def validate_frames(records, frame_range, error=None):
    if error:
        raise RuntimeError('Playblast Eevee incompleto: ' + error)
    expected = list(range(int(frame_range[0]), int(frame_range[1]) + 1))
    if [item['maya_frame'] for item in records] != expected:
        raise RuntimeError('Prism no capturó todos los fotogramas de Eevee. No publiques ese archivo.')


def quicktime(command, options, ffmpeg):
    """Capture Maya's audio/video timing, then encode a MOV without legacy QT."""
    target = Path(options['filename']).with_suffix('.mov')
    if target.exists() and not options.get('forceOverwrite', False):
        raise RuntimeError('Ya existe el archivo QuickTime: ' + str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = None
    try:
        with tempfile.TemporaryDirectory(prefix='Eevee-Prism-video-') as folder:
            intermediate = Path(folder) / 'capture.avi'
            native = dict(options, format='avi', compression='iyuv',
                          filename=str(intermediate), viewer=False)
            width = options.get('width', options.get('widthHeight', (0, 0))[0])
            height = options.get('height', options.get('widthHeight', (0, 0))[1])
            if max(width, height) > 2048:
                native['compression'] = 'none'
            command(**native)
            if not intermediate.is_file():
                raise RuntimeError('Maya no generó el vídeo temporal para QuickTime.')
            with tempfile.NamedTemporaryFile(prefix=target.stem + '.eevee-', suffix='.mov',
                                             dir=str(target.parent), delete=False) as stream:
                temporary_output = Path(stream.name)
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            result = subprocess.run([
                str(ffmpeg), '-hide_banner', '-nostdin', '-v', 'error', '-i', str(intermediate),
                '-map', '0:v:0', '-map', '0:a?', '-c:v', 'libx264', '-crf', '18',
                '-pix_fmt', 'yuv420p', '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2',
                '-c:a', 'aac', '-movflags', '+faststart', '-y', str(temporary_output)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startup)
            if result.returncode or not temporary_output.stat().st_size:
                raise RuntimeError('No se pudo convertir el playblast a MOV: ' +
                                   result.stderr.decode('utf-8', 'replace')[-2000:])
            os.replace(temporary_output, target)
            temporary_output = None
        return str(target)
    finally:
        if temporary_output is not None:
            temporary_output.unlink(missing_ok=True)


@contextmanager
def routed_playblast(panel, core):
    import maya.cmds as cmds
    original = cmds.playblast
    failures = []

    @functools.wraps(original)
    def routed(*args, **options):
        # Prism queries, if any, retain Maya's original semantics.
        if options.get('query') or options.get('q') or options.get('activeEditor') or options.get('ae'):
            return original(*args, **options)
        options = dict(options)
        options.setdefault('editorPanelName', panel)
        try:
            if options.get('format') == 'qt':
                ffmpeg = core.media.getFFmpeg(validate=True)
                if not ffmpeg or not Path(ffmpeg).is_file():
                    raise RuntimeError('Prism no encuentra FFmpeg para generar QuickTime con Eevee.')
                if args:
                    raise RuntimeError('La captura QuickTime de Prism requiere argumentos con nombre.')
                return quicktime(original, options, ffmpeg)
            return original(*args, **options)
        except Exception as exc:
            # Prism's Maya function logs native exceptions and can continue.
            # Surface them after it returns, before publish/master succeeds.
            failures.append(exc)
            raise

    cmds.playblast = routed
    try:
        yield
        if failures:
            raise RuntimeError('Falló la captura Eevee de Prism: ' + str(failures[0]))
    finally:
        if cmds.playblast is routed:
            cmds.playblast = original


def bind(core):
    """Wrap a loaded Prism Maya plugin, retaining its paths and state workflow."""
    global _binding
    plugin = getattr(core, 'appPlugin', None)
    original = getattr(plugin, 'sm_playblast_createPlayblast', None)
    if original is None:
        return False
    if _binding and _binding[0] is plugin and original is _binding[2]:
        return True
    unbind()

    @functools.wraps(original)
    def create(origin, jobFrames, outputName, *args, **kwargs):
        import maya.cmds as cmds
        from . import ui, viewport
        controller = ui._controller
        if controller is None or not cmds.modelPanel(controller.panel, exists=True) or cmds.modelEditor(
                controller.panel, query=True, rendererOverrideName=True) != viewport.NAME:
            return original(origin, jobFrames, outputName, *args, **kwargs)
        focus = cmds.getPanel(withFocus=True)
        # Prism's lookThru uses the active view. Select Eevee's panel before it
        # applies the chosen camera, and also name the panel on the command.
        cmds.setFocus(controller.panel)
        controller.capture_records = []
        controller.capture_error = None
        try:
            with routed_playblast(controller.panel, core):
                result = original(origin, jobFrames, outputName, *args, **kwargs)
            validate_frames(controller.capture_records, jobFrames, controller.capture_error)
            return result
        finally:
            if focus and cmds.control(focus, exists=True):
                cmds.setFocus(focus)

    plugin.sm_playblast_createPlayblast = create
    _binding = (plugin, original, create)
    return True


def unbind():
    global _binding
    if _binding:
        plugin, original, wrapper = _binding
        if getattr(plugin, 'sm_playblast_createPlayblast', None) is wrapper:
            plugin.sm_playblast_createPlayblast = original
        _binding = None


def install():
    """Prism and Eevee can initialize in either order during Maya startup."""
    global _timer
    from PySide2 import QtCore
    attempts = [0]

    def check():
        attempts[0] += 1
        module = sys.modules.get('PrismInit')
        core = getattr(module, 'pcore', None)
        if (core and bind(core)) or attempts[0] >= 60:
            _timer.stop()

    uninstall()
    _timer = QtCore.QTimer()
    _timer.timeout.connect(check)
    _timer.start(2000)
    check()


def uninstall():
    global _timer
    if _timer is not None:
        _timer.stop()
        _timer = None
    unbind()

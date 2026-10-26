"""Native playblast lifecycle and bounded waiting for an exact Eevee frame."""
import time

_callback = None


def active():
    import maya.api.OpenMaya as om
    try:
        return om.MConditionMessage.getConditionState('playblasting')
    except RuntimeError:
        return False


def wait_until(engine, predicate, accept, timeout=120):
    deadline = time.monotonic() + timeout
    while True:
        received = engine.poll()
        if engine.last_response.get('error'):
            raise RuntimeError('Playblast Eevee: ' + engine.last_response['error'])
        if received:
            accept()
        if predicate():
            return
        if engine.process is None or engine.process.poll() is not None:
            raise RuntimeError('Blender terminó antes de completar el fotograma del playblast.')
        if time.monotonic() >= deadline:
            raise TimeoutError('Eevee no completó el fotograma del playblast en %.0f segundos.' % timeout)
        time.sleep(.001)


def _changed(playing, *args):
    from . import ui, viewport
    import maya.cmds as cmds
    if playing and ui._controller is None:
        # Selecting Eevee from Maya's renderer menu is also an activation.
        panels = cmds.getPanel(type='modelPanel') or []
        focused = cmds.getPanel(withFocus=True)
        panels.sort(key=lambda panel: panel != focused)
        for panel in panels:
            if cmds.modelEditor(panel, query=True, rendererOverrideName=True) == viewport.NAME:
                ui.attach(panel)
                break
    if ui._controller is not None:
        ui._controller.capture_changed(bool(playing))


def install():
    global _callback
    if _callback is None:
        import maya.api.OpenMaya as om
        _callback = om.MConditionMessage.addConditionCallback('playblasting', _changed)


def uninstall():
    global _callback
    if _callback is not None:
        import maya.api.OpenMaya as om
        om.MMessage.removeCallback(_callback)
        _callback = None


def playblast(**options):
    """Python automation variant: also raise if Maya swallowed a draw error."""
    import maya.cmds as cmds
    from . import ui
    result = cmds.playblast(**options)
    if ui._controller is not None and ui._controller.capture_error:
        raise RuntimeError('Playblast Eevee incompleto: ' + ui._controller.capture_error)
    return result

"""Drag this file into Maya to collect startup details without opening a scene."""
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback


def onMayaDroppedPythonFile(*args):
    return diagnose()


def diagnose():
    import maya.cmds as cmds
    root = Path(__file__).resolve().parent
    result = {'plugin_root': str(root), 'python': sys.version}
    for label, query in (
        ('maya_version', lambda: cmds.about(version=True)),
        ('maya_api_version', lambda: cmds.about(apiVersion=True)),
        ('gpu', lambda: cmds.ogs(query=True, deviceInformation=True)),
        ('rendering_engine_preference', lambda: cmds.optionVar(query='vp2RenderingEngine')),
        ('loaded_plugins', lambda: cmds.pluginInfo(query=True, listPlugins=True)),
    ):
        try:
            result[label] = query()
        except Exception as exc:
            result[label] = str(exc)
    try:
        plugin = str(root / 'plug-ins' / 'eeveeBridge.py')
        if not cmds.pluginInfo(plugin, query=True, loaded=True):
            cmds.loadPlugin(plugin)
        result['plugin_loaded'] = True
    except Exception:
        result['plugin_loaded'] = False
        result['error'] = traceback.format_exc()
    base = Path(os.environ.get('LOCALAPPDATA') or tempfile.gettempdir()) / 'EeveeMayaBridge' / 'diagnostics'
    base.mkdir(parents=True, exist_ok=True)
    previous = base / ('plugin_load.%d.json' % os.getpid())
    if not previous.exists():
        previous = base / 'plugin_load.json'
    if previous.exists():
        try:
            result['last_startup'] = json.loads(previous.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            pass
    report = base / 'installation_report.json'
    report.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding='utf-8')
    print(json.dumps(result, indent=2, ensure_ascii=True))
    cmds.confirmDialog(title='Diagnóstico de Eevee Maya Bridge',
                       message='Informe guardado en:\n' + str(report) + '\n\nPuedes enviar este archivo para revisar el fallo.',
                       button=['Aceptar'])
    return str(report)


if __name__ == '__main__':
    diagnose()

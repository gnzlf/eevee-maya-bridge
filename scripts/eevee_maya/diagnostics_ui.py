"""Manual diagnostics commands. No timers, scene writes or renderer activation."""
from datetime import datetime, timezone
import maya.cmds as cmds

from . import __version__
from . import diagnostics, material_audit
from .protocol import write_json

WINDOW = 'eeveeMaterialDiagnostics'
MESSAGES = {
    'unsupported_shader': 'Familia de shader sin traducción específica.',
    'texture_not_readable': 'El exportador no puede leer el archivo de textura configurado.',
    'texture_channel_approximated': 'Se usa el color de la textura; el canal conectado no se reproduce exactamente.',
    'untranslated_connection': 'Conexión sin traducción específica en este atributo.',
    'normal_without_file_texture': 'Normal/bump sin textura file directa traducible.',
    'unsupported_normal_connection': 'Red de normal/bump sin traducción específica.',
    'material_read_failed': 'No se pudo terminar la lectura de este material.',
}


def _metadata():
    return {'bridge_version': __version__, 'maya_version': cmds.about(version=True),
            'generated_utc': datetime.now(timezone.utc).isoformat()}


def _save(report, caption, filename):
    paths = cmds.fileDialog2(caption=caption, fileMode=0, dialogStyle=2,
                             fileFilter='JSON (*.json)', startingDirectory=filename)
    if not paths:
        return None
    try:
        write_json(paths[0], report)
    except (OSError, ValueError) as exc:
        cmds.warning('No se pudo guardar el diagnóstico de Eevee: ' + str(exc))
        return None
    print('Diagnóstico Eevee guardado: ' + paths[0])
    return paths[0]


def collect_performance(controller, override):
    engine = controller.engine
    image = override.gpu_image if override is not None else None
    report = diagnostics.performance_report(engine.request_history, engine.history,
                                             image.presentations if image is not None and engine.gpu else [])
    report.update(_metadata())
    report['gpu_transport'] = bool(engine.gpu)
    report['latest_main_thread_ms'] = {key: value for key, value in controller.timings.items()
        if key in ('export_ms', 'submit_ms', 'tick_ms', 'response_age_ms', 'refresh_ms')
        and diagnostics.number(value) and value >= 0}
    latest = engine.last_response
    report['latest_scene_counts'] = {key: latest[key] for key in
        ('meshes', 'scene_rebuilds', 'incremental_updates') if diagnostics.number(latest.get(key))}
    report['notes'].append('Los tiempos del hilo principal son la última muestra, no percentiles de toda la ventana.')
    report['notes'].append('Sin transporte GPU no se mide presentación; no se deducen FPS a partir de respuestas del worker.')
    return report


def save_performance(*args):
    from . import ui, viewport
    if ui._controller is None:
        cmds.warning('Activa Eevee para registrar imágenes antes de guardar el diagnóstico.')
        return None
    # Snapshot before the file dialog: time spent choosing a path is not render latency.
    report = collect_performance(ui._controller, viewport._override)
    return _save(report, 'Guardar diagnóstico de rendimiento Eevee', 'eevee-rendimiento.json')


def show_materials(*args):
    report = material_audit.audit(cmds, include_names=True)
    report.update(_metadata())
    lines = ['%d materiales; %d con incidencias; %d sin traductor específico.' %
             (report['material_count'], report['materials_with_issues'], report['unsupported_count']),
             'Incluye materiales sin asignar. No modifica la escena.',
             'Sin incidencias detectadas no significa equivalencia visual completa.', '']
    for item in report['materials']:
        lines.append('%s · %s · %s' % (item['material_id'], item.get('name', ''), item['kind']))
        for issue in item['issues']:
            detail = ' [%s]' % issue['attribute'] if 'attribute' in issue else ''
            lines.append('  - ' + MESSAGES[issue['code']] + detail)
        if not item['issues']:
            lines.append('  Sin incidencias detectadas en esta revisión limitada.')
        lines.append('')
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)
    window = cmds.window(WINDOW, title='Eevee · Revisión de materiales', widthHeight=(680, 530))
    form = cmds.formLayout()
    text = cmds.scrollField(editable=False, wordWrap=True, text='\n'.join(lines))
    button = cmds.button(label='Guardar informe sin nombres ni rutas…',
        command=lambda *_: _save(material_audit.anonymized(report),
            'Guardar revisión de materiales Eevee', 'eevee-materiales.json'))
    cmds.formLayout(form, edit=True, attachForm=[(text, 'top', 8), (text, 'left', 8),
        (text, 'right', 8), (button, 'bottom', 8), (button, 'left', 8), (button, 'right', 8)],
        attachControl=[(text, 'bottom', 8, button)])
    cmds.showWindow(window)
    return report

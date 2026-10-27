"""Run with mayapy in its own process; never attaches to an open Maya session."""
import json
import os
from pathlib import Path
import sys
import tempfile

root = Path(__file__).resolve().parents[2]
profile = tempfile.TemporaryDirectory(prefix='Eevee-audit-probe-', ignore_cleanup_errors=True)
os.environ['MAYA_APP_DIR'] = profile.name
os.environ['MAYA_SKIP_USERSETUP_PY'] = '1'
sys.path.insert(0, str(root / 'scripts'))
import maya.standalone
maya.standalone.initialize(name='python')
import maya.cmds as cmds
from eevee_maya import material_audit

try:
    mat = cmds.shadingNode('standardSurface', asShader=True, name='AuditSurface')
    texture = cmds.shadingNode('file', asTexture=True, name='AuditTexture')
    cmds.setAttr(texture + '.fileTextureName', str(Path(profile.name) / 'missing.png'), type='string')
    cmds.connectAttr(texture + '.outColor', mat + '.specularColor')
    remap = cmds.shadingNode('remapColor', asUtility=True, name='AuditRemap')
    cmds.connectAttr(remap + '.outColor', mat + '.baseColor')
    bump = cmds.shadingNode('bump2d', asUtility=True, name='AuditBump')
    cmds.connectAttr(texture + '.outAlpha', bump + '.bumpValue')
    cmds.connectAttr(bump + '.outNormal', mat + '.normalCamera')
    cmds.polyCube(name='AuditSelectedCube')
    cmds.currentTime(7)
    cmds.file(rename=str(Path(profile.name) / 'audit-fixture.ma'))
    cmds.file(save=True, type='mayaAscii', force=True)

    def state():
        return {'nodes': sorted(cmds.ls(long=True)), 'selection': cmds.ls(selection=True, long=True),
                'time': cmds.currentTime(query=True), 'modified': cmds.file(query=True, modified=True),
                'connections': cmds.listConnections(mat, source=True, destination=False, plugs=True, connections=True),
                'color': cmds.getAttr(mat + '.specularColor'), 'undo': cmds.undoInfo(query=True, undoName=True)}

    before = state()
    report = material_audit.audit(cmds, nodes=[mat], include_names=True)
    after = state()
    all_report = material_audit.audit(cmds)
    exported = material_audit.anonymized(report)
    issues = report['materials'][0]['issues']
    checks = {
        'scene_selection_time_and_undo_unchanged': before == after,
        'saved_fixture_stays_unmodified': not after['modified'],
        'actual_maya_pairs_detect_unsupported_network': any(item['code'] == 'untranslated_connection'
            and item.get('attribute') == 'baseColor' for item in issues),
        'missing_file_detected': any(item['code'] == 'texture_not_readable' for item in issues),
        'normal_alpha_approximation_detected': any(item['code'] == 'texture_channel_approximated'
            and item.get('attribute') == 'normalCamera' for item in issues),
        'names_visible_only_in_local_view': report['materials'][0]['name'] == mat
            and mat not in json.dumps(exported) and profile.name not in json.dumps(exported),
        'all_materials_scope_correct': all_report['scope'] == 'all_scene_materials_including_unused'
            and all_report['material_count'] >= 1,
    }
    result = {'checks': checks, 'passed': all(checks.values()), 'maya_version': cmds.about(version=True)}
    output = root / 'diagnostics' / 'material_audit_result.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    if not result['passed']:
        raise AssertionError('Material audit integration checks failed')
finally:
    maya.standalone.uninitialize()
    profile.cleanup()

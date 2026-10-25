"""Run with mayapy: verify DAG/name invalidation without touching an open Maya."""
import json
import os
from pathlib import Path
import sys
import tempfile

root = Path(__file__).resolve().parents[2]
profile = tempfile.TemporaryDirectory(prefix='Eevee-name-probe-', ignore_cleanup_errors=True)
os.environ['MAYA_APP_DIR'] = profile.name
os.environ['MAYA_SKIP_USERSETUP_PY'] = '1'
sys.path.insert(0, str(root / 'scripts'))
import maya.standalone
maya.standalone.initialize(name='python')
import maya.cmds as cmds
from eevee_maya.changes import SceneChanges

changes = None
try:
    geo = cmds.polyCube(name='IdentityCube')[0]
    parent = cmds.group(geo, name='IdentityParent')
    destination = cmds.group(empty=True, name='Destination')
    material = cmds.shadingNode('lambert', asShader=True)
    changes = SceneChanges()
    checks = {}
    def reset():
        changes.refresh_callbacks()
        changes.structural = changes.dirty = False
    reset(); geo = cmds.rename(geo, 'RenamedCube')
    checks['rename_mesh_rebuilds_paths'] = changes.structural and changes.watch_dirty
    reset(); parent = cmds.rename(parent, 'RenamedAncestor')
    checks['rename_ancestor_rebuilds_paths'] = changes.structural
    reset(); geo = cmds.parent(geo, destination)[0]
    checks['reparent_rebuilds_paths'] = changes.structural
    reset(); cmds.rename(material, 'RenamedMaterial')
    checks['rename_material_rebuilds_names'] = changes.structural
    reset(); cmds.setAttr(geo + '.translateX', 3)
    checks['transform_edit_keeps_geometry_resources'] = not changes.structural
    cmds.play(state=False)
    changes.playback_changed(True)
    changes.structural = False
    cmds.rename(destination, 'RenamedDuringPlayback')
    checks['identity_events_remain_watched_during_playback'] = changes.structural
    result = {'passed': all(checks.values()), 'checks': checks}
    print(json.dumps(result, indent=2))
    assert result['passed'], result
finally:
    if changes is not None:
        changes.close()
    maya.standalone.uninitialize()
    profile.cleanup()

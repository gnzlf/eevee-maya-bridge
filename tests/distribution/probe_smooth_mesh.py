"""Mayapy regression: native preview, material groups, UVs and skinned deltas."""
import array
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
profile = tempfile.TemporaryDirectory(prefix='Eevee-smooth-probe-', ignore_cleanup_errors=True)
os.environ['MAYA_APP_DIR'] = profile.name
os.environ['MAYA_SKIP_USERSETUP_PY'] = '1'
sys.path.insert(0, str(ROOT / 'scripts'))
import maya.standalone
maya.standalone.initialize(name='python')
import maya.cmds as cmds
import maya.mel as mel
import maya.api.OpenMaya as om
from eevee_maya import exporter
from eevee_maya.changes import SceneChanges
from eevee_maya.scene_stream import SceneStream
from eevee_maya.mesh_packet import records

checks = {}
stream = changes = None


def path_of(name):
    selection = om.MSelectionList()
    selection.add(cmds.listRelatives(name, shapes=True, noIntermediate=True, fullPath=True)[0])
    return selection.getDagPath(0)


def close(a, b):
    return len(a) == len(b) and all(abs(x-y) < 1e-5 for x, y in zip(a, b))


def packet_matches(path, initial):
    result = list(records(stream.update(initial)))
    reference = om.MFnMesh(path)
    if reference.findPlug('displaySmoothMesh', False).asInt():
        reference = om.MFnMesh(reference.findPlug('outSmoothMesh', False).asMObject())
    expected = [v for p in reference.getPoints() for v in (p.x, p.y, p.z)]
    points = next((r['points'].cast('f').tolist() for r in result if 'points' in r), None)
    return points is not None and close(points, expected)


try:
    cube = cmds.polyCube(name='PreviewCube')[0]
    path = path_of(cube)
    shape = path.fullPathName()
    material = cmds.shadingNode('lambert', asShader=True, name='FaceMaterial')
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
    cmds.connectAttr(material + '.outColor', group + '.surfaceShader')
    cmds.sets(cube + '.f[0:1]', edit=True, forceElement=group)
    cmds.select(cube)
    original_nodes = set(cmds.ls(long=True))
    changes = SceneChanges()
    changes.refresh_callbacks()
    for key, faces, vertices in ((1, 6, 8), (3, 96, 98), (2, 96, 98), (1, 6, 8)):
        changes.structural = changes.dirty = False
        mel.eval('setDisplaySmoothness %d' % key)
        label = 'key_%d_%d' % (key, len(checks))
        spec = exporter.mesh(path, {}, binary=False)
        checks[label + '_topology'] = len(spec['counts']) == faces and len(spec['points']) == vertices
        checks[label + '_uvs_and_normals'] = len(spec['uvs']) == len(spec['normals']) == sum(spec['counts'])
        checks[label + '_material_groups'] = spec['face_materials'].count(spec['materials'].index(material)) == faces // 3
        if stream:
            stream.close()
        stream = SceneStream([shape])
        checks[label + '_native_packet'] = packet_matches(path, True)
    checks['preview_does_not_add_nodes_or_subdivide_source'] = set(cmds.ls(long=True)) == original_nodes and cmds.polyEvaluate(cube, face=True) == 6
    mel.eval('setDisplaySmoothness 3')
    try:
        stream.update()
        checks['stream_rejects_stale_base_topology'] = False
    except RuntimeError:
        checks['stream_rejects_stale_base_topology'] = True
    stream.close()
    stream = SceneStream([shape])
    stream.update(True)
    for level in (1, 3):
        changes.structural = False
        cmds.setAttr(shape + '.smoothLevel', level)
        spec = exporter.mesh(path, {}, binary=True)
        counts = array.array('i'); counts.frombytes(spec['counts'])
        checks['level_%d_topology_and_uvs' % level] = len(counts) == 6 * 4 ** level and len(spec['uvs']) == sum(counts) * 8
        checks['level_%d_rebuilds_resources' % level] = changes.structural
    cmds.setAttr(shape + '.smoothLevel', 2)
    before = exporter.mesh(path, {}, binary=False)
    cmds.polyCrease(cube + '.e[0:3]', value=3)
    after = exporter.mesh(path, {}, binary=False)
    checks['crease_preserves_native_shape_and_uvs'] = before['points'] != after['points'] and len(after['uvs']) == 384
    stream.close(); stream = SceneStream([shape])
    checks['creases_match_native_packet'] = packet_matches(path, True)
    changes.structural = False
    cmds.setAttr(shape + '.osdFvarBoundary', 2)
    checks['uv_smoothing_rule_rebuilds_resources'] = changes.structural
    cmds.select(clear=True)
    joint = cmds.joint(name='PreviewJoint', position=(0, 0, 0))
    cmds.skinCluster(joint, cube, toSelectedBones=True)
    stream.close(); stream = SceneStream([shape])
    stream.update(True)
    changes.refresh_callbacks(); changes.structural = False
    cmds.setKeyframe(joint, attribute='rotateZ', time=1, value=0)
    cmds.setKeyframe(joint, attribute='rotateZ', time=2, value=35)
    changes.playback_changed(True)
    cmds.currentTime(2)
    checks['animated_skin_matches_maya_preview'] = packet_matches(path, False)
    checks['skin_animation_uses_delta_without_full_rebuild'] = not changes.structural
    changes.playback_changed(False); changes.refresh_callbacks()
    instance = cmds.instance(cube, name='PreviewInstance')[0]
    instance_path = path_of(instance)
    checks['instance_preview_keeps_materials'] = exporter.mesh(instance_path, {}, binary=False)['face_materials'] == exporter.mesh(path, {}, binary=False)['face_materials']
    instance_material = cmds.shadingNode('lambert', asShader=True)
    instance_group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
    cmds.connectAttr(instance_material + '.outColor', instance_group + '.surfaceShader')
    cmds.sets(instance + '.f[0]', edit=True, forceElement=instance_group)
    instance_spec = exporter.mesh(instance_path, {}, binary=False)
    checks['instance_specific_face_assignment'] = instance_spec['face_materials'].count(instance_spec['materials'].index(instance_material)) == 16
    cmds.setAttr(shape + '.useGlobalSmoothDrawType', False)
    cmds.setAttr(shape + '.smoothDrawType', 0)
    stream.close(); stream = SceneStream([shape])
    checks['maya_catmull_clark_native_packet'] = packet_matches(path, True)
    legacy = exporter.mesh(path, {}, binary=False)
    checks['maya_catmull_clark_material_groups'] = legacy['face_materials'].count(legacy['materials'].index(material)) == 32
    # A triangle and n-gon fixture exercises remapped component groups rather
    # than relying on four children per source face.
    ngon = cmds.polyCreateFacet(point=[(0,0,0),(2,0,0),(3,1,0),(2,2,0),(0,2,0)], name='PreviewNgon')[0]
    cmds.sets(ngon, edit=True, forceElement=group)
    np = path_of(ngon);cmds.setAttr(np.fullPathName() + '.displaySmoothMesh', 2)
    spec = exporter.mesh(np, {}, binary=False)
    checks['ngon_preview_and_material'] = len(spec['counts']) == 20 and spec['face_materials'] == [0] * 20
    result = {'passed': all(checks.values()), 'checks': checks}
    print(json.dumps(result, indent=2))
    assert result['passed'], result
finally:
    if stream: stream.close()
    if changes: changes.close()
    maya.standalone.uninitialize()
    profile.cleanup()

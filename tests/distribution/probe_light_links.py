"""Run with mayapy to validate cached links and Maya Undo/Redo invalidation."""
import json,os,sys,tempfile
from pathlib import Path
from unittest import mock
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'scripts'))
profile=tempfile.TemporaryDirectory(prefix='Eevee-links-',ignore_cleanup_errors=True)
os.environ['MAYA_APP_DIR']=profile.name;os.environ['MAYA_SKIP_USERSETUP_PY']='1'
import maya.standalone
maya.standalone.initialize(name='python')
import maya.cmds as cmds
from eevee_maya.light_links import LightLinks
cache=None
try:
    objects=[cmds.polyCube()[0] for _ in range(2)]
    meshes=[cmds.ls(obj,dag=True,type='mesh',long=True)[0] for obj in objects]
    light=cmds.pointLight();name=cmds.ls(light,long=True)[0]
    cache=LightLinks();initial=cache.read(meshes,[name]);checks={}
    checks['initial_receivers']=set(initial[name]['receivers'])==set(meshes)
    with mock.patch('eevee_maya.light_links.time.monotonic',return_value=cache.checked+10):
        checks['no_periodic_reparse']=cache.read(meshes,[name]) is initial
    cmds.lightlink(light=light,object=objects[1],b=True)
    checks['native_break_invalidates_cache']=meshes[1] not in cache.read(meshes,[name])[name]['receivers']
    cmds.undo()
    checks['undo_restores_links']=set(cache.read(meshes,[name])[name]['receivers'])==set(meshes)
    cmds.redo()
    checks['redo_updates_links']=meshes[1] not in cache.read(meshes,[name])[name]['receivers']
    print(json.dumps({'passed':all(checks.values()),'checks':checks},indent=2));assert all(checks.values())
finally:
    if cache:cache.close()
    maya.standalone.uninitialize();profile.cleanup()

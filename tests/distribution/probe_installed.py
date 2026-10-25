"""Run with mayapy to verify the packaged plugin without opening or changing a scene."""
import json
import os
from pathlib import Path
import sys
import tempfile

root=Path(os.environ['EEVEE_INSTALLED_ROOT']).resolve()
profile=tempfile.TemporaryDirectory(prefix='EeveeMayaBridge-package-probe-',ignore_cleanup_errors=True)
os.environ['MAYA_APP_DIR']=profile.name;os.environ['MAYA_SKIP_USERSETUP_PY']='1'
import maya.standalone
maya.standalone.initialize(name='python')
import maya.cmds as cmds
sys.path.insert(0,str(root/'scripts'))
from eevee_maya import __version__,engine,gpu_share,scene_stream
plugin=str(root/'plug-ins/eeveeBridge.py');loaded=cmds.loadPlugin(plugin)[0]
settings=engine.settings()
status=cmds.eeveeViewport('status')
checks={'package_version':__version__=='0.6.1','plugin_version':cmds.pluginInfo(plugin,query=True,version=True)==__version__,
        'native_command_registered':status in ('Detenido',['Detenido']),
        'portable_blender_selected':'runtime' in settings['blender'] and Path(settings['blender']).is_file(),
        'gpu_library_loaded':bool(gpu_share.library()),'maya_library_loaded':bool(scene_stream.library())}
result={'passed':all(checks.values()),'checks':checks,'status_result':repr(status),'loaded':cmds.pluginInfo(query=True,listPlugins=True),'batch':cmds.about(batch=True)}
print(json.dumps(result,indent=2))
cmds.unloadPlugin(loaded);maya.standalone.uninitialize();profile.cleanup()
assert result['passed']

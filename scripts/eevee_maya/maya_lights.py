"""Light shapes supported by the bridge, including Arnold's locator-based area."""
import maya.api.OpenMaya as om
import maya.cmds as cmds


def types():
    result = ['directionalLight', 'pointLight', 'spotLight', 'areaLight', 'ambientLight']
    try:
        if om.MNodeClass('aiAreaLight').typeId.id():
            result.append('aiAreaLight')
    except (RuntimeError, ValueError):
        pass
    return result


def selected():
    return cmds.ls(selection=True, dag=True, type=types(), long=True) or []

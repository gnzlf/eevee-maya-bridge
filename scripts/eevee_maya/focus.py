"""Focus on evaluated Maya surfaces, in world centimetres."""
import maya.cmds as cmds
import maya.api.OpenMaya as om


def camera_path(name):
    selected = om.MSelectionList(); selected.add(name)
    path = selected.getDagPath(0)
    if path.node().hasFn(om.MFn.kTransform): path.extendToShape()
    return path


def depth(path, point):
    matrix = path.inclusiveMatrix()
    forward = om.MVector(-matrix[8], -matrix[9], -matrix[10]).normal()
    return (point - om.MPoint(matrix[12], matrix[13], matrix[14])) * forward


def visible_meshes(objects=None):
    names = (cmds.ls(objects, dag=True, type='mesh', long=True) if objects else
             cmds.ls(type='mesh', long=True)) or []
    for name in dict.fromkeys(names):
        selected = om.MSelectionList(); selected.add(name)
        path = selected.getDagPath(0)
        if path.isVisible() and not om.MFnDagNode(path).isIntermediateObject:
            yield path


def ray_hit(origin, direction, meshes, maximum=1e10):
    direction = direction.normal()
    closest = None
    for path in meshes:
        fn = om.MFnMesh(path)
        hit = fn.closestIntersection(om.MFloatPoint(origin), om.MFloatVector(direction),
                                     om.MSpace.kWorld, maximum, False,
                                     accelParams=fn.autoUniformGridParams())
        if hit and hit[1] < maximum:
            closest, maximum = om.MPoint(hit[0]), hit[1]
    return closest


def selection_point(path, selected):
    bounds = cmds.exactWorldBoundingBox(selected)
    unit = om.MDistance.uiUnit()
    center = om.MPoint(*[om.MDistance((bounds[i]+bounds[i+3])*.5, unit).asCentimeters()
                         for i in range(3)])
    # Components already specify the intended depth; do not move a selected
    # vertex/face onto a different surface in front of it.
    if any('.' in name for name in selected): return center
    meshes = list(visible_meshes(selected))
    if not meshes: meshes = list(visible_meshes())  # e.g. a facial rig control
    matrix = path.inclusiveMatrix()
    origin = om.MPoint(matrix[12], matrix[13], matrix[14])
    direction = center-origin
    if om.MFnCamera(path).isOrtho():
        direction = om.MVector(-matrix[8], -matrix[9], -matrix[10]).normal()
        origin = center-direction*depth(path, center)
    return ray_hit(origin, direction, meshes) or center

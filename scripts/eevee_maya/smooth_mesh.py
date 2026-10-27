"""Read Maya's evaluated preview without adding nodes or changing the source mesh."""
import maya.api.OpenMaya as om


def evaluated(source):
    """Return the exact output used for Smooth Mesh Preview (keys 2 and 3)."""
    if source.findPlug("displaySmoothMesh", False).asInt() == 0:
        return source
    return om.MFnMesh(source.findPlug("outSmoothMesh", False).asMObject())


def face_materials(source, preview, shaders, original, instance):
    if preview is source:
        return original
    if len(shaders) <= 1:
        return [0 if shaders else -1] * preview.numPolygons
    # Maya remaps component groups during subdivision, including n-gons,
    # creases and UV boundaries. Use those groups rather than assuming face order.
    data = om.MFnGeometryData(source.findPlug("outSmoothMesh", False).asMObject())
    slots = {om.MObjectHandle(shader).hashCode(): i for i, shader in enumerate(shaders)}
    groups = source.findPlug("instObjGroups", False).elementByLogicalIndex(instance)
    groups = groups.child(source.attribute("objectGroups"))
    assignments = [-1] * preview.numPolygons
    for i in range(groups.numElements()):
        group = groups.elementByPhysicalIndex(i)
        group_id = group.child(source.attribute("objectGroupId")).asInt()
        if not data.hasObjectGroup(group_id):
            continue
        targets = group.connectedTo(False, True)
        slot = next((slots[om.MObjectHandle(p.node()).hashCode()] for p in targets
                     if om.MObjectHandle(p.node()).hashCode() in slots), None)
        if slot is None:
            continue
        component = data.objectGroupComponent(group_id)
        if not component.hasFn(om.MFn.kMeshPolygonComponent):
            continue
        fn = om.MFnSingleIndexedComponent(component)
        faces = range(preview.numPolygons) if fn.isComplete else fn.getElements()
        for face in faces:
            assignments[face] = slot
    return assignments

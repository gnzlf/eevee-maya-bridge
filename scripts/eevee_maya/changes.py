"""DG dirtiness tracking: camera navigation does not re-export the entire scene."""
import maya.api.OpenMaya as om
import maya.cmds as cmds


class SceneChanges:
    # These settings can change preview UVs/topology even when vertex counts
    # remain unchanged. Ordinary transforms and deformations keep the delta path.
    smooth_attributes = frozenset((
        "displaySmoothMesh", "smoothLevel", "smoothDrawType", "useGlobalSmoothDrawType",
        "smoothUVs", "keepMapBorders", "keepBorder", "keepHardEdge", "propagateEdgeHardness",
        "boundaryRule", "continuity", "osdVertBoundary", "osdFvarBoundary",
        "osdFvarPropagateCorners", "osdSmoothTriangles", "osdCreaseMethod",
        "useOsdBoundaryMethods", "osdIndependentUVChannels", "smoothOffset", "smoothTessLevel",
    ))

    def __init__(self):
        self.dirty = True
        self.reconnect = True
        self.structural = True
        self.material_dirty = False
        self.callbacks = []
        self.node_callbacks = []
        self.playing = False
        self.watch_dirty = True
        self.watches = []
        self.structural_events = []
        self.callbacks.append(om.MDGMessage.addNodeAddedCallback(self.structure_changed, "dependNode"))
        self.callbacks.append(om.MDGMessage.addNodeRemovedCallback(self.structure_changed, "dependNode"))
        self.callbacks.append(om.MNodeMessage.addNameChangedCallback(om.MObject(), self.name_changed))
        self.callbacks.append(om.MDagMessage.addAllDagChangesCallback(self.dag_changed))
        for event in ("timeChanged", "Undo", "Redo"):
            self.callbacks.append(om.MEventMessage.addEventCallback(event, self.mark))
        self.callbacks.append(om.MConditionMessage.addConditionCallback("playingBack", self.playback_changed))

    def playback_changed(self, playing, *args):
        self.playing = bool(playing)
        self.dirty = True
        if self.playing:
            for callback in self.node_callbacks:
                om.MMessage.removeCallback(callback)
            self.node_callbacks = []
        else:
            self.reconnect = True

    def mark(self, *args):
        self.dirty = True

    def name_changed(self, node, *args):
        # Exported identifiers are full DAG paths. Renaming a shape, ancestor,
        # or material invalidates the Python names and Blender's object keys.
        try:
            kind = om.MFnDependencyNode(node).typeName
            if not (node.hasFn(om.MFn.kMesh) or node.hasFn(om.MFn.kTransform)
                    or kind == "shadingEngine" or cmds.getClassification(kind, satisfies="shader")):
                return
        except RuntimeError:
            return
        self.paths_changed()

    def dag_changed(self, message, parent, child, *args):
        try:
            node = child.node()
            if not (node.hasFn(om.MFn.kMesh) or node.hasFn(om.MFn.kTransform)):
                return
        except RuntimeError:
            return
        self.paths_changed()

    def paths_changed(self):
        self.dirty = self.structural = self.reconnect = self.watch_dirty = True
        self.structural_events = (self.structural_events + [("identity", "DAG path or material name")])[-32:]

    def structure_changed(self, *args):
        self.dirty = True
        self.reconnect = True
        self.watch_dirty = True
        try:
            node = args[0]
            kind = om.MFnDependencyNode(node).typeName
            if node.hasFn(om.MFn.kMesh) or kind == "shadingEngine" or cmds.getClassification(kind, satisfies="shader"):
                self.structural = True
                self.structural_events = (self.structural_events + [("structure",kind)])[-32:]
        except (RuntimeError, IndexError):
            self.structural = True
            self.structural_events = (self.structural_events + [("structure", "unavailable node")])[-32:]

    def material_changed(self, *args):
        if args and args[0].hasFn(om.MFn.kLight):
            return  # Light data is polled separately; keep all mesh resources alive.
        self.dirty = True
        self.material_dirty = True
        fn = om.MFnDependencyNode(args[0])
        if fn.typeName == "shadingEngine":
            self.structural = True
        self.structural_events = (self.structural_events + [("material",fn.name())])[-32:]

    def mesh_attribute_changed(self, message, plug, other, *args):
        if message & (om.MNodeMessage.kAttributeSet | om.MNodeMessage.kConnectionMade
                      | om.MNodeMessage.kConnectionBroken):
            if om.MFnAttribute(plug.attribute()).name in self.smooth_attributes:
                self.dirty = self.structural = True

    def watch_node(self, node, dynamic):
        self.node_callbacks.append(om.MNodeMessage.addNodeDirtyCallback(
            node, self.mark if dynamic else self.material_changed))
        if node.hasFn(om.MFn.kMesh):
            self.node_callbacks.append(om.MNodeMessage.addAttributeChangedCallback(
                node, self.mesh_attribute_changed))

    def refresh_callbacks(self):
        for callback in self.node_callbacks:
            om.MMessage.removeCallback(callback)
        self.node_callbacks = []
        if self.playing:
            self.reconnect = False
            return
        if not self.watch_dirty:
            for handle, dynamic in self.watches:
                if handle.isValid() and handle.isAlive():
                    self.watch_node(handle.object(), dynamic)
            self.reconnect = False
            return
        self.watches = []
        classifications = {}
        iterator = om.MItDependencyNodes()
        while not iterator.isDone():
            node = iterator.thisNode()
            fn = om.MFnDependencyNode(node)
            kind = fn.typeName
            if kind not in classifications:
                classifications[kind] = bool(cmds.getClassification(kind, satisfies="shader"))
            watch = (node.hasFn(om.MFn.kMesh) or node.hasFn(om.MFn.kLight)
                     or node.hasFn(om.MFn.kTransform) or kind == "shadingEngine"
                     or classifications[kind])
            if watch and node.hasFn(om.MFn.kTransform):
                dag = om.MFnDagNode(node)
                watch = not any(dag.child(i).hasFn(om.MFn.kCamera) or dag.child(i).hasFn(om.MFn.kLight) for i in range(dag.childCount()))
            if watch:
                dynamic = node.hasFn(om.MFn.kMesh) or node.hasFn(om.MFn.kTransform)
                self.watch_node(node, dynamic)
                self.watches.append((om.MObjectHandle(node), dynamic))
            iterator.next()
        self.reconnect = False
        self.watch_dirty = False

    def close(self):
        for callback in self.callbacks + self.node_callbacks:
            om.MMessage.removeCallback(callback)
        self.callbacks = self.node_callbacks = []

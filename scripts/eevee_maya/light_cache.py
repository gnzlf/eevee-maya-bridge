"""Light export without re-reading ~50 Maya attributes per light on every frame.

World matrices and visibility are read fresh every call through the API (cheap).
Attribute values are cached per light shape and invalidated by that shape's
dirty notification, time changes, Undo/Redo and scene structure changes. This
keeps light drags and rig playback from issuing hundreds of cmds.getAttr calls
per submitted pose.
"""
import time

import maya.api.OpenMaya as om
import maya.cmds as cmds

from . import exporter, maya_lights


class LightCache:
    # Safety net for edits Maya reports without a dirty message on the shape.
    LIST_TTL = 2.0
    ATTRIBUTE_TTL = 1.0

    def __init__(self):
        self.list_dirty = True
        self.listed_at = 0
        self.kinds = None
        self.entries = []          # [(MDagPath, kind, key)]
        self.attributes = {}       # key -> attribute dict
        self.read_at = {}          # key -> monotonic time
        self.node_callbacks = []
        self.callbacks = []
        add = self.callbacks.append
        add(om.MDGMessage.addNodeAddedCallback(self.structure_changed, "dependNode"))
        add(om.MDGMessage.addNodeRemovedCallback(self.structure_changed, "dependNode"))
        add(om.MDagMessage.addAllDagChangesCallback(self.structure_changed))
        add(om.MNodeMessage.addNameChangedCallback(om.MObject(), self.structure_changed))
        for event in ("timeChanged", "Undo", "Redo", "SceneOpened", "NewSceneOpened"):
            add(om.MEventMessage.addEventCallback(event, self.invalidate))

    # -- invalidation -----------------------------------------------------
    def invalidate(self, *args):
        self.attributes.clear()

    def structure_changed(self, *args):
        self.list_dirty = True

    def _light_dirty(self, node, key):
        self.attributes.pop(key, None)

    def _clear_node_callbacks(self):
        for callback in self.node_callbacks:
            try:
                om.MMessage.removeCallback(callback)
            except RuntimeError:
                pass
        self.node_callbacks = []

    # -- listing ----------------------------------------------------------
    def _relist(self):
        self._clear_node_callbacks()
        self.kinds = maya_lights.types()
        entries = []
        for name in cmds.ls(type=self.kinds, long=True) or []:
            selection = om.MSelectionList()
            try:
                selection.add(name)
                path = selection.getDagPath(0)
            except RuntimeError:
                continue
            kind = cmds.nodeType(name)
            if kind not in self.kinds:
                continue
            node = path.node()
            key = om.MObjectHandle(node).hashCode()
            try:
                self.node_callbacks.append(om.MNodeMessage.addNodeDirtyCallback(
                    node, lambda obj, *rest, k=key: self._light_dirty(obj, k)))
            except RuntimeError:
                pass
            entries.append((path, kind, key))
        self.entries = entries
        alive = {key for _, _, key in entries}
        for key in list(self.attributes):
            if key not in alive:
                self.attributes.pop(key, None)
                self.read_at.pop(key, None)
        self.list_dirty = False
        self.listed_at = time.monotonic()

    # -- export -----------------------------------------------------------
    def lights(self):
        now = time.monotonic()
        if self.list_dirty or now - self.listed_at > self.LIST_TTL:
            self._relist()
        result = []
        for path, kind, key in self.entries:
            try:
                if not path.isValid() or not path.isVisible():
                    continue
                name = path.fullPathName()
                matrix = exporter.matrix_values(path.inclusiveMatrix())
            except RuntimeError:
                self.list_dirty = True
                continue
            attributes = self.attributes.get(key)
            if attributes is None or now - self.read_at.get(key, 0) > self.ATTRIBUTE_TTL:
                attributes = exporter.light_attributes(name, kind)
                self.attributes[key] = attributes
                self.read_at[key] = now
            result.append(exporter.light_record(name, matrix, attributes))
        return result

    def close(self):
        self._clear_node_callbacks()
        for callback in self.callbacks:
            try:
                om.MMessage.removeCallback(callback)
            except RuntimeError:
                pass
        self.callbacks = []

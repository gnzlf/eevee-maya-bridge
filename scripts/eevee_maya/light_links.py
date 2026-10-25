"""Read Maya's resolved object light links, including ignore and shadow links."""
import time
import maya.OpenMaya as om
import maya.OpenMayaRender as render


class LightLinks:
    def __init__(self):
        self.dirty=True
        self.key=None
        self.result={}
        self.checked=0
        self.callbacks=[om.MDGMessage.addConnectionCallback(self.connection_changed)]
        self.callbacks.append(om.MEventMessage.addEventCallback('lightLinkingChanged',self.mark))

    def mark(self,*args):
        self.dirty=True

    def connection_changed(self,source,destination,*args):
        for plug in (source,destination):
            node=plug.node()
            if node.hasFn(om.MFn.kSet) or om.MFnDependencyNode(node).typeName=='lightLinker':
                self.dirty=True
                break

    def read(self,mesh_names,light_names):
        key=(tuple(mesh_names),tuple(light_names))
        # The periodic refresh also covers renames and Undo/Redo of memberships.
        if not self.dirty and key==self.key and time.monotonic()-self.checked<2:
            return self.result
        links=render.MLightLinks()
        links.parseLinks(om.MObject(),False,None,True)
        result={name:{'receivers':[],'shadow_blockers':[]} for name in light_names}
        for name in mesh_names:
            selected=om.MSelectionList();selected.add(name)
            path=om.MDagPath();selected.getDagPath(0,path)
            for field,include,exclude in (
                    ('receivers','getLinkedLights','getIgnoredLights'),
                    ('shadow_blockers','getShadowLinkedLights','getShadowIgnoredLights')):
                positive=om.MDagPathArray();negative=om.MDagPathArray()
                getattr(links,include)(path,om.MObject(),positive)
                getattr(links,exclude)(path,om.MObject(),negative)
                ignored={negative[i].fullPathName() for i in range(negative.length())}
                for i in range(positive.length()):
                    light=positive[i].fullPathName()
                    if light in result and light not in ignored:result[light][field].append(name)
        for spec in result.values():
            for field in spec:spec[field].sort()
        self.result=result;self.key=key;self.dirty=False;self.checked=time.monotonic()
        return result

    def close(self):
        for callback in self.callbacks:om.MMessage.removeCallback(callback)
        self.callbacks=[]

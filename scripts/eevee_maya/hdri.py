"""HDRI controls operate on Maya's own Arnold SkyDome and texture nodes."""
import os
import maya.cmds as cmds
from . import maya_lights


def domes():
    if 'aiSkyDomeLight' not in maya_lights.types():
        return []
    return cmds.ls(type='aiSkyDomeLight', long=True) or []


def image_connection(shape):
    sources=cmds.listConnections(shape+'.color',source=True,destination=False) or []
    if not sources:return None
    node=sources[0]
    attribute={'file':'fileTextureName','aiImage':'filename'}.get(cmds.nodeType(node))
    return (node,attribute) if attribute else None


def load_image(shape,path):
    if shape not in domes():raise ValueError('Selecciona una SkyDome de Arnold')
    if not os.path.isfile(path):raise ValueError('No se encuentra el archivo HDRI')
    cmds.undoInfo(openChunk=True,chunkName='Eevee HDRI image')
    try:
        connection=image_connection(shape)
        if connection:
            pairs=cmds.listConnections(connection[0],source=False,destination=True,connections=True,plugs=True) or []
            # Never change a shared texture on another light or material.
            destinations=[destination for source,destination in zip(pairs[::2],pairs[1::2])
                          if cmds.getAttr(source,type=True)!='message']
            only_this=all((cmds.ls(p.split('.')[0],long=True) or [''])[0]==shape and p.split('.')[-1]=='color' for p in destinations)
            if not only_this:connection=None
        if connection is None:
            node=cmds.shadingNode('file',asTexture=True,isColorManaged=True,name='eeveeHDRIImage')
            connection=(node,'fileTextureName')
            cmds.connectAttr(node+'.outColor',shape+'.color',force=True)
        node,attribute=connection
        cmds.setAttr(node+'.'+attribute,path,type='string')
        if cmds.nodeType(node)=='file':
            space=cmds.colorManagementFileRules(evaluate=path)
            if space:cmds.setAttr(node+'.colorSpace',space,type='string')
        return node
    finally:cmds.undoInfo(closeChunk=True)


def create(path):
    if not os.path.isfile(path):raise ValueError('No se encuentra el archivo HDRI')
    cmds.loadPlugin('mtoa',quiet=True)
    cmds.undoInfo(openChunk=True,chunkName='Eevee HDRI SkyDome')
    try:
        parent=cmds.shadingNode('aiSkyDomeLight',asLight=True,name='eeveeHDRI')
        shape=cmds.listRelatives(parent,shapes=True,fullPath=True)[0]
        load_image(shape,path)
        cmds.select(parent,replace=True)
        return shape
    finally:cmds.undoInfo(closeChunk=True)

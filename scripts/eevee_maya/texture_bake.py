"""Read-only UV sampling of supported Maya 2D texture networks.

Only texture outputs are sampled, never lit surfaces. Cached float EXRs retain
HDR values and Maya's working space without adding nodes or changing Undo.
"""
import array
import hashlib
import json
from pathlib import Path
import struct
import tempfile

SUPPORTED = frozenset(('file', 'place2dTexture', 'layeredTexture', 'ramp', 'noise',
                       'checker', 'fractal', 'reverse', 'multiplyDivide',
                       'plusMinusAverage', 'blendColors', 'gammaCorrect', 'clamp',
                       'remapColor', 'remapValue', 'luminance', 'contrast', 'hsvToRgb', 'rgbToHsv'))
_directory = None
_bakes = 0


def fingerprint(cmds, plug):
    """Return None for unsupported/object-dependent graphs; don't guess."""
    pending = [plug.split('.')[0]]; seen = set(); records = []
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        kind = cmds.nodeType(node)
        if kind not in SUPPORTED:
            return None
        values = {}
        for name in cmds.listAttr(node, read=True, write=True, scalar=True, multi=True, settable=True) or []:
            try:
                value = cmds.getAttr(node+'.'+name)
                if isinstance(value, (str, int, float, bool, tuple, list)):
                    values[name] = value
            except (RuntimeError, ValueError):
                pass
        links = []
        pairs = cmds.listConnections(node, source=True, destination=False, connections=True, plugs=True) or []
        for dst, src in zip(pairs[::2], pairs[1::2]):
            attribute = dst.split('.', 1)[1]
            if attribute in ('message', 'colorManagementEnabled', 'colorManagementConfigFileEnabled',
                             'colorManagementConfigFilePath', 'workingSpace'):
                continue
            if cmds.getAttr(dst, type=True) == 'message':
                continue
            links.append((dst, src)); pending.append(src.split('.')[0])
        if kind == 'file':
            path = Path(cmds.getAttr(node+'.fileTextureName'))
            if not path.is_absolute():
                path = Path(cmds.workspace(expandName=str(path)))
            # UV baking is restricted to a single 0..1 tile. UDIM direct files
            # use the existing tiled-image path instead.
            if cmds.getAttr(node+'.uvTilingMode') or cmds.getAttr(node+'.useFrameExtension') or not path.is_file():
                return None
            values['_file'] = (str(path), path.stat().st_mtime_ns, path.stat().st_size)
        records.append((node, kind, values, sorted(links)))
    records.sort(key=lambda r: r[0])
    color = [cmds.colorManagementPrefs(query=True, **{flag: True})
             for flag in ('renderingSpaceName', 'configFilePath', 'cmEnabled')]
    return hashlib.sha256(json.dumps((plug, records, color), sort_keys=True).encode('utf-8')).hexdigest()


def write_exr(path, width, height, rows):
    """Small uncompressed RGB float scanline EXR writer; no third-party runtime."""
    def field(name, kind, data):
        return name.encode()+b'\0'+kind.encode()+b'\0'+struct.pack('<I',len(data))+data
    channels = b''.join(c+b'\0'+struct.pack('<iB3xii',2,0,1,1) for c in (b'B',b'G',b'R'))+b'\0'
    box = struct.pack('<4i',0,0,width-1,height-1)
    header = struct.pack('<II',20000630,2)+field('channels','chlist',channels)+field('compression','compression',b'\0')
    header += field('dataWindow','box2i',box)+field('displayWindow','box2i',box)+field('lineOrder','lineOrder',b'\0')
    header += field('pixelAspectRatio','float',struct.pack('<f',1))+field('screenWindowCenter','v2f',struct.pack('<2f',0,0))
    header += field('screenWindowWidth','float',struct.pack('<f',1))+b'\0'
    row_size = 8+width*12; offset = len(header)+height*8
    with open(path,'wb') as stream:
        stream.write(header)
        stream.write(b''.join(struct.pack('<Q',offset+y*row_size) for y in range(height)))
        for y, values in enumerate(rows):
            stream.write(struct.pack('<iI',y,width*12))
            for c in (2,1,0):
                data=array.array('f', (pixel[c] for pixel in values))
                stream.write(data.tobytes())


def bake(cmds, plug, resolution=1024):
    global _directory, _bakes
    signature = fingerprint(cmds, plug)
    if signature is None:
        return None
    if _directory is None:
        _directory = tempfile.TemporaryDirectory(prefix='Eevee-material-textures-', ignore_cleanup_errors=True)
    path = Path(_directory.name)/(signature+'-'+str(resolution)+'.exr')
    if not path.is_file():
        import maya.OpenMaya as om
        import maya.OpenMayaRender as render
        def rows():
            # EXR scanlines run from top to bottom, UV V runs bottom to top.
            for y0 in range(0,resolution,16):
                count=min(16,resolution-y0)*resolution
                u=om.MFloatArray();v=om.MFloatArray();sizes=om.MFloatArray()
                for y in range(y0,min(y0+16,resolution)):
                    for x in range(resolution):
                        u.append((x+.5)/resolution);v.append(1-(y+.5)/resolution);sizes.append(1/resolution)
                colors=om.MFloatVectorArray();transparency=om.MFloatVectorArray()
                render.MRenderUtil.sampleShadingNetwork(plug,count,False,False,om.MFloatMatrix(),
                    None,u,v,None,None,None,None,sizes,colors,transparency)
                if colors.length()!=count:
                    raise RuntimeError('Maya returned an incomplete texture sample')
                for row in range(count//resolution):
                    yield [(colors[i].x,colors[i].y,colors[i].z) for i in range(row*resolution,(row+1)*resolution)]
        temporary=path.with_suffix('.part')
        try:
            write_exr(temporary,resolution,resolution,rows());temporary.replace(path);_bakes+=1
        finally:
            if temporary.exists():temporary.unlink()
    return {'path':str(path),'color_space':cmds.colorManagementPrefs(query=True,renderingSpaceName=True),
            'baked':True,'resolution':resolution,'source_kind':cmds.nodeType(plug.split('.')[0])}

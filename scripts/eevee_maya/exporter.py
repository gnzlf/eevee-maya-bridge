"""Read evaluated Maya DAG geometry on the Maya main thread."""
import math
import os
import array

import maya.api.OpenMaya as om
import maya.cmds as cmds


def matrix_values(matrix):
    return list(matrix)


def attr(node, name, default):
    plug = node + "." + name
    if not cmds.objExists(plug):
        return default
    value = cmds.getAttr(plug)
    if isinstance(value, list) and len(value) == 1:
        return value[0]
    return value


def texture(node, attribute, resolution=2048):
    """Direct image channels or cached read-only sampling of Maya 2D networks."""
    from .texture_paths import resolve
    sources = cmds.listConnections(node + "." + attribute, source=True,
                                   destination=False, plugs=True) or []
    if not sources:
        return None
    source=sources[0];file,channel=source.split('.',1)
    file_kind=cmds.nodeType(file)
    if file_kind not in ('file','aiImage'):
        from .texture_bake import bake
        return bake(cmds,source,resolution=resolution)
    # Maya's sampler also preserves placement and color-balance operations for
    # ordinary 0..1 images. UDIMs retain the dedicated tiled-image route.
    adjusted = (attr(file,'repeatUV',(1,1)) != (1,1) or attr(file,'offset',(0,0)) != (0,0)
                or attr(file,'rotateUV',0) != 0 or attr(file,'rotateFrame',0) != 0
                or attr(file,'coverage',(1,1)) != (1,1) or attr(file,'translateFrame',(0,0)) != (0,0)
                or attr(file,'colorGain',(1,1,1)) != (1,1,1) or attr(file,'colorOffset',(0,0,0)) != (0,0,0)
                or attr(file,'invert',False) or attr(file,'alphaGain',1) != 1 or attr(file,'alphaOffset',0) != 0
                or attr(file,'mirrorU',False) or attr(file,'mirrorV',False) or attr(file,'stagger',False)
                or not attr(file,'wrapU',True) or not attr(file,'wrapV',True) or attr(file,'noiseUV',(0,0))!=(0,0)
                or channel=='outAlpha' and attr(file,'alphaIsLuminance',False))
    if adjusted and attr(file,'uvTilingMode',0)==0:
        from .texture_bake import bake
        return bake(cmds,source,resolution=resolution)
    path = attr(file, "fileTextureName" if file_kind=='file' else 'filename', "")
    if not os.path.isabs(path):
        path = cmds.workspace(expandName=path)
    pattern = attr(file, 'computedFileTextureNamePattern', '') or ''
    if pattern and not os.path.isabs(pattern):
        pattern = cmds.workspace(expandName=pattern)
    result = resolve(path, attr(file, 'uvTilingMode', 0) == 3, pattern)
    if result is None:
        return None
    result['color_space'] = attr(file, 'colorSpace', 'sRGB')
    result['channel'] = channel
    result['alpha_is_luminance'] = bool(attr(file,'alphaIsLuminance',False))
    return result


def normal_texture(node):
    if not cmds.objExists(node + ".normalCamera"):
        return None
    sources = cmds.listConnections(node + ".normalCamera", source=True, destination=False) or []
    if not sources:
        return None
    source = sources[0]
    kind = cmds.nodeType(source)
    if kind in ("bump2d", "aiBump2d"):
        spec = texture(source, "bumpValue" if kind == "bump2d" else "bumpMap",resolution=1024)
        if spec:
            normal = attr(source, "bumpInterp", 0) == 1
            depth=attr(source,'bumpDepth',1)
            # Strength and Distance previously both received bumpDepth, which
            # squared small values. Blender world units equal Maya centimeters.
            return {"texture": spec, "kind": "normal" if normal else "bump",
                    "strength": depth if normal else 1, "distance": abs(depth), "invert": depth<0}
    if kind == "aiNormalMap":
        spec = texture(source, "input")
        if spec:
            return {"texture": spec, "kind": "normal", "strength": attr(source, "strength", 1)}
    return None


def color_management():
    result = {'enabled': bool(cmds.colorManagementPrefs(query=True, cmEnabled=True)),
            'rendering_space': cmds.colorManagementPrefs(query=True, renderingSpaceName=True),
            'view': cmds.colorManagementPrefs(query=True, viewTransformName=True)}
    result['display'] = cmds.colorManagementPrefs(query=True, displayName=True)
    result['native_view'] = cmds.colorManagementPrefs(query=True, viewName=True)
    path = cmds.colorManagementPrefs(query=True, configFilePath=True) or ''
    location = os.environ.get('MAYA_LOCATION', '')
    path = path.replace('<MAYA_RESOURCES>', os.path.join(location, 'resources'))
    result['config_path'] = os.path.expandvars(path)
    result['native_ocio'] = bool(cmds.colorManagementPrefs(query=True, ociov2Enabled=True) and os.path.isfile(result['config_path']))
    if result['native_ocio']:
        info=os.stat(result['config_path']);result['config_signature']=(info.st_mtime_ns,info.st_size)
    return result


def material(node):
    kind = cmds.nodeType(node)
    if kind == "aiStandardVolume":
        return {"name": node, "kind": kind, "density": attr(node, "density", 0.1),
                "scatter": list(attr(node, "scatterColor", (1, 1, 1))),
                "anisotropy": attr(node, "scatterAnisotropy", 0),
                "emission": list(attr(node, "emissionColor", (0, 0, 0))),
                "emission_strength": attr(node, "emission", 0)}
    standard = kind in ("standardSurface", "aiStandardSurface")
    classic=kind in ('lambert','blinn','phong')
    color_attr = "baseColor" if standard else "color"
    if kind == "blinn":
        roughness = math.sqrt(max(0.001, attr(node, "eccentricity", 0.3)))
    elif kind == "phong":
        roughness = math.sqrt(2.0 / (max(0, attr(node, "cosinePower", 20)) + 2))
    else:
        roughness = attr(node, "specularRoughness", 0.5) if standard else 0.65
    return {
        "name": node, "kind": kind,
        "color": list(attr(node, color_attr, (0.5, 0.5, 0.5))),
        "metallic": attr(node, "metalness", 0.0), "roughness": roughness,
        "color_texture": texture(node, color_attr),
        "metallic_texture": texture(node, "metalness") if standard else None,
        "roughness_texture": texture(node, "specularRoughness") if standard else None,
        "specular_texture": texture(node, "specular") if standard else None,
        "base_texture": texture(node, "base") if standard else None,
        "coat_texture": texture(node, "coat") if standard else None,
        "coat_roughness_texture": texture(node, "coatRoughness") if standard else None,
        "transmission_texture": texture(node, "transmission") if standard else None,
        "transmission_color_texture": texture(node, "transmissionColor") if standard else None,
        "emission": list(attr(node, "emissionColor", (0, 0, 0))),
        "emission_strength": attr(node, "emission", 0.0),
        "ambient_color": list(attr(node,'ambientColor',(0,0,0))) if classic else None,
        "ambient_texture": texture(node,'ambientColor') if classic else None,
        "incandescence": list(attr(node,'incandescence',(0,0,0))) if classic else None,
        "incandescence_texture": texture(node,'incandescence') if classic else None,
        "transmission": attr(node, "transmission", 0.0),
        "base_weight": attr(node, "base", 1.0) if standard else attr(node, "diffuse", 1),
        "ior": attr(node, "specularIOR", 1.5),
        "specular_weight": attr(node, "specular", 1) if standard else (0 if kind == 'lambert' else .5),
        "specular_color": list(attr(node, "specularColor", (1, 1, 1))),
        "specular_color_texture": texture(node, "specularColor") if standard or kind in ('blinn','phong') else None,
        "transmission_color": list(attr(node, "transmissionColor", (1, 1, 1))),
        "coat": attr(node, "coat", 0), "coat_roughness": attr(node, "coatRoughness", .1),
        "coat_color": list(attr(node, "coatColor", (1, 1, 1))),
        "sheen": attr(node, "sheen", 0), "sheen_color": list(attr(node, "sheenColor", (1, 1, 1))),
        "subsurface": attr(node, "subsurface", 0),
        "subsurface_radius": list(attr(node, "subsurfaceRadius", (1, 1, 1))),
        "opacity": list(attr(node, "opacity", (1, 1, 1))) if standard else [1-v for v in attr(node, "transparency", (0, 0, 0))],
        "normal_map": normal_texture(node),
        "opacity_texture": texture(node, "opacity") if standard else None,
        "emission_texture": texture(node, "emissionColor") if standard else None,
    }


def mesh(path, materials, binary=False):
    from . import smooth_mesh
    source = om.MFnMesh(path)
    # Hidden objects retain a lightweight base resource. Revealing a smoothed
    # object makes the native stream request its current preview topology.
    fn = smooth_mesh.evaluated(source) if path.isVisible() else source
    counts, indices = fn.getVertices()
    shaders, face_materials = source.getConnectedShaders(path.instanceNumber())
    face_materials = smooth_mesh.face_materials(source, fn, shaders, face_materials, path.instanceNumber())
    slots = []
    for shader in shaders:
        group = om.MFnDependencyNode(shader).name()
        connections = cmds.listConnections(group + ".surfaceShader", source=True,
                                           destination=False) or []
        volume = cmds.listConnections(group + ".volumeShader", source=True, destination=False) or []
        if volume and cmds.nodeType(volume[0]) == "aiStandardVolume":
            connections = volume
        name = connections[0] if connections else "lambert1"
        if name not in materials:
            materials[name] = material(name)
        slots.append(name)
    uvs = []
    try:
        us, vs = fn.getUVs()
        uv_counts, uv_ids = fn.getAssignedUVs()
        # Unmapped faces cannot be represented as a complete loop UV layer.
        if list(uv_counts) == list(counts):
            uvs = (array.array("f", (v for i in uv_ids for v in (us[i], vs[i]))).tobytes()
                   if binary else [[us[i], vs[i]] for i in uv_ids])
    except RuntimeError:
        pass
    normals = []
    try:
        if binary:
            raise RuntimeError("Native stream supplies normals")
        values = fn.getNormals(om.MSpace.kObject)
        _, normal_ids = fn.getNormalIds()
        normals = [[values[i].x, values[i].y, values[i].z] for i in normal_ids]
    except RuntimeError:
        pass
    return {
        "name": path.fullPathName(),
        "matrix": matrix_values(path.inclusiveMatrix()),
        "points": [] if binary else [[p.x, p.y, p.z] for p in fn.getPoints(om.MSpace.kObject)],
        "counts": array.array("i", counts).tobytes() if binary else list(counts),
        "indices": array.array("i", indices).tobytes() if binary else list(indices), "uvs": uvs,
        "normals": normals, "materials": slots,
        "face_materials": array.array("i", face_materials).tobytes() if binary else list(face_materials),
        "binary_geometry": binary,
    }


def camera(camera_name, width, height):
    selection = om.MSelectionList()
    selection.add(camera_name)
    path = selection.getDagPath(0)
    if path.node().hasFn(om.MFn.kTransform):
        path.extendToShape()
    fn = om.MFnCamera(path)
    # Fallback for callers outside a VP2 draw. Native viewports supply their
    # complete frame-context projection, including gates and film transforms.
    left, right, bottom, top = fn.getViewingFrustum(float(width) / height, True, True, True)
    return {
        "path": path.fullPathName(),
        "matrix": matrix_values(path.inclusiveMatrix()),
        "orthographic": fn.isOrtho(),
        "ortho_width": right - left if fn.isOrtho() else fn.orthoWidth,
        "fov_x": 2.0 * math.atan((right - left) / (2.0 * fn.nearClippingPlane)),
        "shift_x": (right + left) / (2.0 * (right - left)),
        "shift_y": (top + bottom) / (2.0 * (right - left)),
        "near": max(0.001, fn.nearClippingPlane), "far": fn.farClippingPlane,
        "dof": fn.isDepthOfField, "focus_distance": fn.focusDistance,
        "fstop": fn.fStop, "focal_length": fn.focalLength,
        "sensor_width_cm": fn.horizontalFilmAperture * 2.54,
        "focus_region_scale": attr(path.fullPathName(), "focusRegionScale", 1.0),
    }


def environment_texture(node):
    """Direct file/aiImage environment sources; never sample an unsupported graph."""
    sources = cmds.listConnections(node + '.color', source=True, destination=False) or []
    if not sources:
        return None, None
    source = sources[0]
    kind = cmds.nodeType(source)
    if kind not in ('file', 'aiImage'):
        return None, 'HDRI: solo se admiten conexiones directas file o aiImage en Color'
    path = attr(source, 'fileTextureName' if kind == 'file' else 'filename', '')
    if not os.path.isabs(path):
        path = cmds.workspace(expandName=path)
    if not os.path.isfile(path):
        return None, 'HDRI: archivo de entorno no disponible'
    return {'path': path, 'color_space': attr(source, 'colorSpace', 'sRGB')}, None


def lights():
    from . import maya_lights
    result = []
    kinds = maya_lights.types()
    for name in cmds.ls(type=kinds, long=True) or []:
        selection = om.MSelectionList(); selection.add(name)
        path = selection.getDagPath(0)
        if path.isVisible():
            name = path.fullPathName()
            kind = cmds.nodeType(name)
            if kind in kinds:
                matrix = matrix_values(path.inclusiveMatrix())
                if kind == 'aiSkyDomeLight':
                    image, warning = environment_texture(name)
                    # A connected color is replaced by its texture, not multiplied
                    # by Maya's evaluated outColor (which can be black for aiImage).
                    result.append({'name': name, 'kind': kind, 'matrix': matrix,
                                   'color': list(attr(name, 'color', (1, 1, 1))) if not image and not warning else [1, 1, 1],
                                   'texture': image, 'warning': warning,
                                   'intensity': attr(name, 'intensity', 1),
                                   'exposure': attr(name, 'exposure', 0),
                                   'camera': attr(name, 'camera', 1),
                                   'format': attr(name, 'format', 2),
                                   'resolution': attr(name, 'resolution', 1000),
                                   'diffuse': attr(name, 'aiDiffuse', 1),
                                   'specular': attr(name, 'aiSpecular', 1)})
                    continue
                result.append({"name": name, "kind": kind, "matrix": matrix,
                               "color": list(attr(name, "color", (1, 1, 1))),
                               "intensity": attr(name, "intensity", 1), "exposure": attr(name, "aiExposure", 0),
                               "cone_angle": math.radians(attr(name, "coneAngle", 40)),
                               "penumbra": math.radians(attr(name, "penumbraAngle", 0)),
                               "dropoff": attr(name, "dropoff", 0), "decay": attr(name, "decayRate", 2 if kind == 'aiAreaLight' else 0),
                               "decay_reference": max(.001,attr(name,"centerOfIllumination",5)),
                               "diffuse": attr(name, "aiDiffuse", 1) if kind == 'aiAreaLight' else bool(attr(name, "emitDiffuse", True)),
                               "specular": attr(name, "aiSpecular", 1) if kind == 'aiAreaLight' else bool(attr(name, "emitSpecular", True)),
                               "volume": bool(attr(name, "eeveeVolume", True)), "volume_factor": attr(name, "eeveeVolumeFactor", 1),
                               "shadows": bool(attr(name, "aiCastShadows", True)) if kind == 'aiAreaLight' else bool(attr(name, "useDepthMapShadows", False) or attr(name, "useRayTraceShadows", False)),
                               "ambient_shade": attr(name, "ambientShade", .45),
                               "normalize": bool(attr(name, "normalize", True)),
                               "legacy_intensity": bool(attr(name, "legacyIntensity", False)),
                               "area_shape": attr(name, "aiTranslator", 'quad') or 'quad',
                               "spread": math.pi * attr(name, "aiSpread", 1),
                               "radius": attr(name, "lightRadius", 0),
                               "angle": math.radians(attr(name, "lightAngle", 0)),
                               "size_x": 2 * math.sqrt(sum(v*v for v in matrix[:3])),
                               "size_y": 2 * math.sqrt(sum(v*v for v in matrix[4:7]))})
    return result


def snapshot(camera_name, width=640, height=360, samples=16, studio=True, binary=False):
    materials, meshes, warnings = {}, [], []
    iterator = om.MItDag(om.MItDag.kDepthFirst, om.MFn.kInvalid)
    while not iterator.isDone():
        path = iterator.getPath()
        obj = path.node()
        if obj.hasFn(om.MFn.kMesh):
            fn = om.MFnDagNode(path)
            if not fn.isIntermediateObject and (binary or path.isVisible()):
                try:
                    meshes.append(mesh(path, materials, binary=binary))
                except (RuntimeError, ValueError) as exc:
                    warnings.append(path.fullPathName() + ": " + str(exc))
        iterator.next()
    return {"protocol": 1, "meshes": meshes, "materials": list(materials.values()),
            "lights": lights(), "camera": camera(camera_name, width, height),
            "width": width, "height": height, "samples": samples,
            "studio": studio, "warnings": warnings,
            "unit": cmds.currentUnit(query=True, linear=True), "effects": effects(),
            "color_management": color_management()}


def effects():
    node = "eeveeBridgeSettings"
    return {"fog": attr(node, "volumetrics", False), "fog_density": attr(node, "density", 0.015),
            "fog_distance": attr(node,"fogDistance",100),
            "fog_auto_range": bool(attr(node,'fogAutoRange',True)),
            "fog_color": list(attr(node, "fogColor", (0.8, 0.85, 1.0))),
            "anisotropy": attr(node, "anisotropy", 0.3),
            "bloom": attr(node, "bloom", False), "bloom_threshold": attr(node, "bloomThreshold", 1),
            "bloom_strength": attr(node, "bloomStrength", 0.5)}

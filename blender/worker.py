"""Persistent Eevee renderer. Run exclusively in Blender's bundled Python."""
import argparse
import math
import hashlib
import os
from pathlib import Path
import sys
import time
import traceback

import bpy
import numpy as np
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from eevee_maya.protocol import read_json, write_json
from eevee_maya.lighting import expand_spot_profiles
from eevee_maya import shadow_quality, color_management

# Maya and Blender cameras both look along local -Z. Rotate the world Y-up -> Z-up.
CONVERSION = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))


def transform(values):
    return CONVERSION @ Matrix([values[i:i + 4] for i in range(0, 16, 4)]).transposed()


def image_node(tree, specification, noncolor=False):
    if not specification:
        return None
    node = tree.nodes.new("ShaderNodeTexImage")
    node.image = bpy.data.images.load(specification["path"], check_existing=True)
    if specification.get("udim_pattern"):
        node.image.source = "TILED"
        node.image.filepath = specification["udim_pattern"]
        existing_tiles = {tile.number for tile in node.image.tiles}
        for number in specification.get("tiles", []):
            if number not in existing_tiles:
                node.image.tiles.new(number)
        node.image.reload()
    try:
        node.image.colorspace_settings.name = color_management.image_space(specification.get('color_space','sRGB'), noncolor)
    except TypeError:
        node.image.colorspace_settings.name = 'Non-Color' if noncolor else 'sRGB'
    return node


def set_normals(mesh, normals):
    """Blender 5.2 free corner normals accept bulk float data without fan conversion."""
    values = np.asarray(normals, dtype=np.float32).ravel()
    attribute = mesh.attributes.get("custom_normal")
    if attribute and (attribute.data_type != "FLOAT_VECTOR" or attribute.domain != "CORNER"):
        mesh.attributes.remove(attribute)
        attribute = None
    if attribute is None:
        attribute = mesh.attributes.new(name="custom_normal", type="FLOAT_VECTOR", domain="CORNER")
    attribute.data.foreach_set("vector", values)


def make_material(spec, transmission_preview=False):
    mat = bpy.data.materials.new(spec["name"])
    mat.use_nodes = True
    if spec["kind"] == "aiStandardVolume":
        mat.node_tree.nodes.clear()
        output = mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
        volume = mat.node_tree.nodes.new("ShaderNodeVolumePrincipled")
        volume.inputs["Density"].default_value = spec["density"]
        volume.inputs["Color"].default_value = (*spec["scatter"], 1)
        volume.inputs["Anisotropy"].default_value = spec["anisotropy"]
        volume.inputs["Emission Color"].default_value = (*spec["emission"], 1)
        volume.inputs["Emission Strength"].default_value = spec["emission_strength"]
        mat.node_tree.links.new(volume.outputs["Volume"], output.inputs["Volume"])
        return mat
    shader = mat.node_tree.nodes.get("Principled BSDF")
    mat['eevee_ambient_diffuse'] = max(0,spec.get('base_weight',1)) * (1-spec.get('metallic',0))
    shader.inputs["Base Color"].default_value = (*spec["color"], 1)
    shader.inputs["Metallic"].default_value = spec["metallic"]
    shader.inputs["Roughness"].default_value = spec["roughness"]
    shader.inputs["Emission Color"].default_value = (*spec["emission"], 1)
    shader.inputs["Emission Strength"].default_value = spec["emission_strength"]
    shader.inputs["Transmission Weight"].default_value = spec["transmission"]
    shader.inputs['Specular Tint'].default_value = (*spec.get('specular_color', (1, 1, 1)), 1)
    for key, socket, default in (("ior", "IOR", 1.5), ("specular_weight", "Specular IOR Level", .5),
                                 ("coat", "Coat Weight", 0), ("coat_roughness", "Coat Roughness", .1),
                                 ("sheen", "Sheen Weight", 0), ("subsurface", "Subsurface Weight", 0)):
        value = spec.get(key, default)
        if key == "specular_weight": value *= .5
        shader.inputs[socket].default_value = value
    for key, socket in (("coat_color", "Coat Tint"), ("sheen_color", "Sheen Tint")):
        shader.inputs[socket].default_value = (*spec.get(key, (1, 1, 1)), 1)
    shader.inputs["Subsurface Radius"].default_value = spec.get("subsurface_radius", (1, 1, 1))
    shader.inputs["Alpha"].default_value = min(spec.get("opacity", (1, 1, 1)))
    for key, socket, noncolor in (("color_texture", "Base Color", False),
                                  ("metallic_texture", "Metallic", True),
                                  ("roughness_texture", "Roughness", True),
                                  ("specular_color_texture", "Specular Tint", False),
                                  ("opacity_texture", "Alpha", True),
                                  ("emission_texture", "Emission Color", False)):
        node = image_node(mat.node_tree, spec.get(key), noncolor)
        if node:
            mat.node_tree.links.new(node.outputs["Color"], shader.inputs[socket])
    ambient=spec.get('ambient_color')
    incandescence=spec.get('incandescence')
    if ambient is not None and (any(ambient) or any(incandescence) or spec.get('ambient_texture') or spec.get('incandescence_texture')):
        # Maya classic shaders add color*ambientColor + incandescence even
        # without an illuminating light. This belongs to the material, not World.
        tree=mat.node_tree
        multiply=tree.nodes.new('ShaderNodeMixRGB');multiply.blend_type='MULTIPLY';multiply.inputs[0].default_value=1
        multiply.inputs[1].default_value=(*spec['color'],1);multiply.inputs[2].default_value=(*ambient,1)
        color_links=shader.inputs['Base Color'].links
        if color_links:tree.links.new(color_links[0].from_socket,multiply.inputs[1])
        ambient_image=image_node(tree,spec.get('ambient_texture'))
        if ambient_image:tree.links.new(ambient_image.outputs['Color'],multiply.inputs[2])
        addition=tree.nodes.new('ShaderNodeMixRGB');addition.blend_type='ADD';addition.inputs[0].default_value=1
        addition.inputs[2].default_value=(*incandescence,1)
        tree.links.new(multiply.outputs['Color'],addition.inputs[1])
        incandescent_image=image_node(tree,spec.get('incandescence_texture'))
        if incandescent_image:tree.links.new(incandescent_image.outputs['Color'],addition.inputs[2])
        tree.links.new(addition.outputs['Color'],shader.inputs['Emission Color'])
        shader.inputs['Emission Strength'].default_value=1
    normal = spec.get("normal_map")
    if normal:
        image = image_node(mat.node_tree, normal["texture"], True)
        if image:
            converter = mat.node_tree.nodes.new("ShaderNodeNormalMap" if normal["kind"] == "normal" else "ShaderNodeBump")
            converter.inputs["Strength"].default_value = normal.get("strength", 1)
            if normal["kind"] == "bump": converter.inputs["Distance"].default_value = normal.get("distance", .1)
            mat.node_tree.links.new(image.outputs["Color"], converter.inputs["Color" if normal["kind"] == "normal" else "Height"])
            mat.node_tree.links.new(converter.outputs["Normal"], shader.inputs["Normal"])
    if transmission_preview and spec.get('transmission', 0) > 0:
        # The fast viewport has no refraction trace behind eye shells. Mixing
        # transparent transmission with a Fresnel reflection keeps the iris
        # visible without enabling scene-wide ray tracing or altering Maya.
        tree = mat.node_tree
        shader.inputs['Transmission Weight'].default_value = 0
        transparent = tree.nodes.new('ShaderNodeBsdfTransparent')
        transparent.inputs['Color'].default_value = (*spec.get('transmission_color', (1, 1, 1)), 1)
        reflection = tree.nodes.new('ShaderNodeBsdfAnisotropic')
        reflection.inputs['Color'].default_value = (*spec.get('specular_color', (1, 1, 1)), 1)
        tint_links = shader.inputs['Specular Tint'].links
        if tint_links: tree.links.new(tint_links[0].from_socket, reflection.inputs['Color'])
        reflection.inputs['Roughness'].default_value = spec['roughness']
        roughness_links = shader.inputs['Roughness'].links
        if roughness_links: tree.links.new(roughness_links[0].from_socket, reflection.inputs['Roughness'])
        fresnel = tree.nodes.new('ShaderNodeFresnel')
        fresnel.inputs['IOR'].default_value = spec.get('ior', 1.5)
        normal_links = shader.inputs['Normal'].links
        if normal_links:
            for input_ in (reflection.inputs['Normal'], fresnel.inputs['Normal']):
                tree.links.new(normal_links[0].from_socket, input_)
        glass = tree.nodes.new('ShaderNodeMixShader')
        specular = tree.nodes.new('ShaderNodeMath');specular.operation = 'MULTIPLY';specular.use_clamp = True
        specular.inputs[1].default_value = spec.get('specular_weight', 1)
        tree.links.new(fresnel.outputs[0], specular.inputs[0])
        tree.links.new(specular.outputs[0], glass.inputs[0])
        tree.links.new(transparent.outputs[0], glass.inputs[1])
        tree.links.new(reflection.outputs[0], glass.inputs[2])
        surface = tree.nodes.new('ShaderNodeMixShader')
        surface.inputs[0].default_value = max(0, min(1, spec['transmission']))
        tree.links.new(shader.outputs[0], surface.inputs[1])
        tree.links.new(glass.outputs[0], surface.inputs[2])
        # Apply the source opacity to both reflection and transmission.
        opacity = tree.nodes.new('ShaderNodeMixShader')
        opacity.inputs[0].default_value = min(spec.get('opacity', (1, 1, 1)))
        clear = tree.nodes.new('ShaderNodeBsdfTransparent')
        tree.links.new(clear.outputs[0], opacity.inputs[1])
        for link in list(shader.inputs['Alpha'].links):
            tree.links.new(link.from_socket, opacity.inputs[0]);tree.links.remove(link)
        shader.inputs['Alpha'].default_value = 1
        tree.links.new(surface.outputs[0], opacity.inputs[2])
        output = next(node for node in tree.nodes if node.type == 'OUTPUT_MATERIAL')
        tree.links.new(opacity.outputs[0], output.inputs['Surface'])
        mat.surface_render_method = 'BLENDED'
        mat.use_transparency_overlap = False
        mat['eevee_transmission_preview'] = True
    return mat


def install_ambient_material(mat):
    """Object attributes keep light linking without duplicating shared materials."""
    if not mat or not mat.use_nodes or mat.get('eevee_ambient_preview'):
        return
    tree=mat.node_tree
    shader=tree.nodes.get('Principled BSDF')
    if shader is None:return
    attribute=tree.nodes.new('ShaderNodeAttribute');attribute.attribute_type='OBJECT'
    attribute.attribute_name='eevee_ambient_color';attribute.name='EeveeMayaAmbient'
    multiply=tree.nodes.new('ShaderNodeMixRGB');multiply.blend_type='MULTIPLY';multiply.inputs[0].default_value=1
    multiply.inputs[1].default_value=shader.inputs['Base Color'].default_value
    if shader.inputs['Base Color'].links:
        tree.links.new(shader.inputs['Base Color'].links[0].from_socket,multiply.inputs[1])
    tree.links.new(attribute.outputs['Color'],multiply.inputs[2])
    weight=tree.nodes.new('ShaderNodeVectorMath');weight.operation='SCALE'
    weight.inputs['Scale'].default_value=mat.get('eevee_ambient_diffuse',1)
    tree.links.new(multiply.outputs['Color'],weight.inputs[0])
    original=tree.nodes.new('ShaderNodeVectorMath');original.operation='SCALE'
    original.inputs[0].default_value=shader.inputs['Emission Color'].default_value[:3]
    original.inputs['Scale'].default_value=shader.inputs['Emission Strength'].default_value
    if shader.inputs['Emission Color'].links:
        tree.links.new(shader.inputs['Emission Color'].links[0].from_socket,original.inputs[0])
    addition=tree.nodes.new('ShaderNodeVectorMath');addition.operation='ADD'
    tree.links.new(original.outputs['Vector'],addition.inputs[0])
    tree.links.new(weight.outputs['Vector'],addition.inputs[1])
    tree.links.new(addition.outputs['Vector'],shader.inputs['Emission Color'])
    shader.inputs['Emission Strength'].default_value=1
    mat['eevee_ambient_preview']=True


def sync_ambient(objects, lights, native=None):
    ambient=[spec for spec in lights if spec['kind']=='ambientLight']
    mode=(native or {}).get('displayLights','all')
    selected=(native or {}).get('selected_lights',[])
    active=[spec for spec in ambient if (mode=='all' or mode in ('selected','active') and spec['name'] in selected)
            and spec.get('diffuse',True)]
    for name,obj in objects.items():
        if not ambient and 'eevee_ambient_color' not in obj:continue
        if ambient:
            for mat in obj.data.materials:install_ambient_material(mat)
        color=[0.,0.,0.]
        for spec in active:
            if 'receivers' in spec and name not in spec['receivers']:continue
            energy=max(0,spec['intensity']) * 2**spec.get('exposure',0) * (1-max(0,min(1,spec.get('ambient_shade',.45))))
            for i in range(3):color[i]+=spec['color'][i]*energy
        if list(obj.get('eevee_ambient_color',(0,0,0))) != color:
            obj['eevee_ambient_color']=color
            obj.update_tag(refresh={'OBJECT'})


def geometry_signature(request):
    import json
    data = {key: request[key] for key in ("meshes", "materials", "lights", "studio")}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def apply_light(obj, spec, previous=None):
    # Moving a light must not rewrite its photometric data and invalidate
    # Eevee's light/shadow resources on every transform sample.
    if previous is not None and all(value==previous.get(key) for key,value in spec.items() if key!="matrix"):
        if spec["matrix"]!=previous["matrix"]:
            matrix=transform(spec["matrix"])
            obj.matrix_world=matrix.normalized() if obj.data.type=='AREA' else matrix
        return
    data = obj.data
    changed=lambda *keys:previous is None or any(spec.get(key)!=previous.get(key) for key in keys)
    if changed("color"):data.color = spec["color"]
    # Maya intensity is not watts. Calibrate at one scene unit without the old
    # arbitrary x1000 boost which clipped spot/point lights into white.
    if changed("intensity","exposure","decay","decay_reference", "ambient_shade", "normalize", "legacy_intensity", "size_x", "size_y"):
        energy = max(0, spec["intensity"]) * 2 ** spec["exposure"] * (math.pi if data.type == "SUN" else 4*math.pi)
        # Eevee exposes inverse-square falloff only. Other Maya modes are
        # intensity-matched at centerOfIllumination, not exact distance curves.
        if data.type!="SUN":energy *= max(.001,spec.get("decay_reference",5))**(2-int(spec.get("decay",2)))
        if spec['kind'] == 'ambientLight':energy *= max(0, min(1, spec.get('ambient_shade', .45)))
        if data.type == 'AREA':
            if not spec.get('normalize', True):energy *= max(.000001,spec.get('size_x',2)*spec.get('size_y',2))
            if spec.get('legacy_intensity',False):energy *= 12
        data.energy=energy
    if data.type != "SUN" and previous is None:
        # AREA retains Eevee's automatic range. SceneMirror supplies a finite
        # receiver range for point/spot lights, independent of their intensity.
        data.use_custom_distance=False
    if data.type in ('POINT','SPOT') and changed('influence_distance') and spec.get('influence_distance'):
        data.use_custom_distance=True
        data.cutoff_distance=spec['influence_distance']
    if changed("diffuse"):data.diffuse_factor = float(spec.get("diffuse", True))
    if changed("specular"):data.specular_factor = 0 if spec['kind']=='ambientLight' else float(spec.get("specular", True))
    if changed("volume","volume_factor"):data.volume_factor = max(0,spec.get("volume_factor",1)) if spec.get("volume",True) else 0
    if changed("shadows"):data.use_shadow = bool(spec.get("shadows", True))
    if data.type == "SPOT" and changed("cone_angle","penumbra","dropoff"):
        cone=max(.001,min(math.pi-.001,spec["cone_angle"]))
        penumbra=spec.get("penumbra",0)
        outer=max(.001,min(math.pi-.001,cone+2*max(0,penumbra)))
        inner=max(0,cone+2*min(0,penumbra))
        data.spot_size=outer
        data.spot_blend=max(0,min(1,(math.cos(inner/2)-math.cos(outer/2))/max(1e-8,1-math.cos(outer/2))))
    if data.type in ("POINT", "SPOT") and changed("radius"):
        data.shadow_soft_size = max(0, spec.get("radius", 0))
    if data.type == "SUN" and changed("angle"):
        data.angle = max(0, min(math.pi, spec.get("angle", 0)))
    if data.type == "AREA" and changed('size_x','size_y','area_shape','spread'):
        data.shape = 'ELLIPSE' if spec.get('area_shape') == 'disk' else 'RECTANGLE'
        data.size, data.size_y = max(.001,spec.get('size_x',2)), max(.001,spec.get('size_y',2))
        data.spread = max(.001,min(math.pi,spec.get('spread',math.pi)))
    if changed("matrix"):
        matrix=transform(spec["matrix"])
        obj.matrix_world = matrix.normalized() if data.type=='AREA' else matrix


def create_light(spec):
    kind = {"pointLight": "POINT", "areaLight": "AREA", "aiAreaLight": "AREA", "ambientLight": "POINT", "directionalLight": "SUN", "spotLight": "SPOT"}[spec["kind"]]
    data = bpy.data.lights.new(spec["name"], kind)
    obj = bpy.data.objects.new(spec["name"], data)
    obj["maya_path"] = spec["name"]
    bpy.context.scene.collection.objects.link(obj)
    apply_light(obj, spec)
    return obj


def configure_color(request):
    settings = color_management.resolve(request.get('color_management'))
    if bpy.data.colorspace.working_space != settings['working_space']:
        # Values from Maya already belong to its scene-linear working space.
        # Reinterpret them, rather than converting the old Blender values twice.
        bpy.ops.wm.set_working_color_space(working_space=settings['working_space'], convert_colors=False)
    scene = bpy.context.scene
    if scene.view_settings.view_transform != settings['view']:
        scene.view_settings.view_transform = settings['view']
    return settings


def build_scene(request, transmission_preview=False, progress=None):
    configure_color(request)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(bpy.data.collections):
        if collection.get('eevee_bridge_links'):bpy.data.collections.remove(collection)
    for collection in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
        for block in list(collection):
            if block.users == 0:
                collection.remove(block)
    mats = {}
    for index, spec in enumerate(request['materials']):
        if progress: progress('materials', index, len(request['materials']))
        mats[spec['name']] = make_material(spec, transmission_preview=transmission_preview)
    for index, spec in enumerate(request["meshes"]):
        if progress: progress('meshes', index, len(request['meshes']))
        mesh = bpy.data.meshes.new(spec["name"])
        if spec.get("binary_geometry"):
            points = np.frombuffer(spec["points_buffer"], dtype="<f4")
            counts = np.frombuffer(spec["counts"], dtype="<i4")
            indices = np.frombuffer(spec["indices"], dtype="<i4")
            mesh.vertices.add(len(points) // 3)
            mesh.vertices.foreach_set("co", points)
            mesh.loops.add(len(indices))
            mesh.loops.foreach_set("vertex_index", indices)
            mesh.polygons.add(len(counts))
            mesh.polygons.foreach_set("loop_start", np.cumsum(counts, dtype=np.int32) - counts)
            mesh.polygons.foreach_set("loop_total", counts)
            mesh.update(calc_edges=True)
            uvs = np.frombuffer(spec["uvs"], dtype="<f4") if spec["uvs"] else []
            normal_bytes = spec.get("normals_buffer")
            normals = np.frombuffer(normal_bytes, dtype="<f4").reshape(-1, 3) if normal_bytes else []
            face_materials = np.frombuffer(spec["face_materials"], dtype="<i4")
        else:
            faces, offset = [], 0
            for count in spec["counts"]:
                faces.append(spec["indices"][offset:offset + count])
                offset += count
            mesh.from_pydata(spec["points"], [], faces)
            mesh.update()
            uvs = [v for uv in spec["uvs"] for v in uv]
            normals = spec.get("normals", [])
            face_materials = spec["face_materials"]
        if len(uvs) == len(mesh.loops) * 2 and len(uvs):
            layer = mesh.uv_layers.new(name="map1")
            layer.data.foreach_set("uv", uvs)
        for name in spec["materials"]:
            mesh.materials.append(mats[name])
        if len(face_materials):
            mesh.polygons.foreach_set("material_index", np.maximum(face_materials, 0).astype(np.int32))
        if len(normals) == len(mesh.loops):
            mesh.polygons.foreach_set("use_smooth", np.ones(len(mesh.polygons), dtype=np.bool_))
            set_normals(mesh, normals)
            mesh.update()
        obj = bpy.data.objects.new(spec["name"], mesh)
        obj["maya_path"] = spec["name"]
        material_specs={m['name']:m for m in request['materials']}
        obj['eevee_depth_surface']=any(material_specs[name]['kind']!='aiStandardVolume' and
                                      max(material_specs[name].get('opacity',(1,1,1))) *
                                      (1-material_specs[name].get('transmission',0))>.001 for name in spec['materials'])
        obj['eevee_source_depth_surface']=obj['eevee_depth_surface']
        obj.hide_viewport = not spec.get("visible", True)
        obj.hide_render = not spec.get("visible", True)
        bpy.context.scene.collection.objects.link(obj)
        obj.matrix_world = transform(spec["matrix"])
    for spec in request["lights"]:
        if spec['kind'] != 'aiSkyDomeLight':
            create_light(spec)
    if request["studio"]:
        for name, location, energy, size in (
                ("EeveeStudioKey", (4, -6, 8), 1500, 5),
                ("EeveeStudioFill", (-4, -2, 4), 800, 4)):
            data = bpy.data.lights.new(name, "AREA")
            data.energy, data.shape, data.size = energy, "DISK", size
            obj = bpy.data.objects.new(name, data)
            bpy.context.scene.collection.objects.link(obj)
            obj.location = location
            obj.rotation_euler = (-Vector(location)).to_track_quat("-Z", "Y").to_euler()
    if "native" in request or (not request["lights"] and not request["studio"]):
        data = bpy.data.lights.new("EeveeDefaultHeadlight", "SUN")
        data.energy = 2.5
        obj = bpy.data.objects.new("EeveeDefaultHeadlight", data)
        bpy.context.scene.collection.objects.link(obj)
    cam = bpy.data.objects.new("EeveeBridgeCamera", bpy.data.cameras.new("EeveeBridgeCamera"))
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam


def apply_camera(cam,spec):
    matrix=transform(spec["matrix"])
    scale=max(.000001,matrix.col[2].to_3d().length)
    # Viewport 2.0 cancels inherited transform scale in its projection matrix.
    # Clip and focus distances are in world centimetres, even for scaled rigs.
    cam.matrix_world = matrix.normalized()
    cam.data.type = "ORTHO" if spec["orthographic"] else "PERSP"
    cam.data.sensor_fit = "HORIZONTAL"
    cam.data.lens = spec.get("focal_length",35)
    if spec["orthographic"]:
        cam.data.ortho_scale = spec["ortho_width"]*scale
    else:
        cam.data.angle = spec["fov_x"]
    cam.data.shift_x, cam.data.shift_y = spec.get("shift_x", 0), spec.get("shift_y", 0)
    cam.data.clip_start, cam.data.clip_end = spec["near"], spec["far"]
    cam.data.dof.use_dof=spec.get("dof",False)
    cam.data.dof.focus_distance=max(.001,spec.get("focus_distance",10))
    cam.data.dof.aperture_fstop=max(.1,spec.get("fstop",5.6))
    return cam


def camera_matrices(cam, spec, width, height):
    native = spec.get('viewport')
    if native:
        projection = Matrix([native['projection'][i:i+4] for i in range(0,16,4)]).transposed()
        view = Matrix([native['view'][i:i+4] for i in range(0,16,4)]).transposed() @ CONVERSION.inverted()
        # Keep the native pair together. Folding view/source cancellation into
        # projection left a nonzero [3][3] from float rounding. Eevee tests that
        # entry exactly to classify perspective, breaking local-light culling.
        # The product remains Maya's original projection/view, including gates
        # and inherited camera scale; color and shared depth use the same pair.
        return view, projection
    return cam.matrix_world.inverted(), cam.calc_matrix_camera(
        bpy.context.evaluated_depsgraph_get(), x=width, y=height)


def render(request, output):
    configure_color(request)
    if any(light['kind']=='ambientLight' for light in request['lights']):
        sync_ambient({obj['maya_path']:obj for obj in bpy.context.scene.objects
                      if obj.type=='MESH' and 'maya_path' in obj},request['lights'],request.get('native'))
    shadow_settings = request.get('shadow_settings', {})
    shadow_quality.apply(bpy.context.scene.eevee, {
        'shadow_quality': shadow_settings.get('preset', 'high'),
        'shadow_pool_size': shadow_settings.get('pool', 'auto')})
    scene = bpy.context.scene
    cam=apply_camera(scene.camera,request["camera"])
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = request["width"], request["height"]
    scene.render.resolution_percentage = 100
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = request["samples"]
    from environment import sync_environment
    native = request.get('native', {})
    sync_environment(native.get('displayLights', 'all'), request.get('lights', []),
                     native.get('selected_lights', []), native.get('shadows', True))
    if not any(s['kind'] == 'aiSkyDomeLight' for s in request.get('lights', [])):
        # Preserve the image backend's original neutral world illumination.
        ambient = scene.world.node_tree.nodes['EeveeAmbientLighting']
        ambient.inputs['Color'].default_value = (.12, .12, .12, 1)
        ambient.inputs['Strength'].default_value = .5
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.filepath = str(output)
    bpy.ops.render.render(write_still=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--parent-pid", type=int)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    session = Path(args.session).resolve()
    session.mkdir(parents=True, exist_ok=True)
    write_json(session / "ready.json", {"blender": bpy.app.version_string, "pid": os.getpid()})
    previous_id, previous_geometry = None, None
    parent_handle = None
    if args.parent_pid and os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        parent_handle = kernel.OpenProcess(0x1000, False, args.parent_pid)
        if not parent_handle:
            raise RuntimeError("Cannot monitor Maya parent process")
    while not (session / "stop").exists():
        if parent_handle:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(parent_handle, ctypes.byref(code)) or code.value != 259:
                break
        path = session / "request.json"
        if not path.exists():
            time.sleep(0.05)
            continue
        request = read_json(path)
        request_id = request["id"]
        if request_id == previous_id:
            time.sleep(0.05)
            continue
        previous_id = request_id
        started = time.monotonic()
        try:
            if request.get("protocol") != 1:
                raise ValueError("Unsupported bridge protocol")
            signature = geometry_signature(request)
            if signature != previous_geometry:
                build_scene(request)
                previous_geometry = signature
            filename = "frame_%08d.png" % int(request_id)
            render(request, session / filename)
            write_json(session / "response.json", {"id": request_id, "image": filename,
                       "seconds": time.monotonic() - started, "engine": "BLENDER_EEVEE",
                       "meshes": len(request["meshes"]), "warnings": request.get("warnings", [])})
        except Exception:
            write_json(session / "response.json", {"id": request_id, "error": traceback.format_exc()})
        if args.once:
            break
    if parent_handle:
        kernel.CloseHandle(parent_handle)
    write_json(session / "exited.json", {"pid": os.getpid()})


if __name__ == "__main__":
    main()

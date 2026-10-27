"""Keep Blender objects/materials alive across transform and deformation updates."""
import bpy
import numpy as np
import math
from mathutils import Matrix

import worker
from eevee_maya.mesh_packet import records
from eevee_maya.lighting import same_light_links, set_light_visibility


class SceneMirror:
    def __init__(self):
        self.previous = None
        self.objects = {}
        self.rebuilds = 0
        self.updates = 0
        self.names = []
        self.deltas = []
        self.light_signature = None
        self.light_specs = {}
        self.display_signature = None
        self.texture_links = []
        self.original_materials = {}
        self.link_collections = {}
        self.progress = None
        self.ambient_enabled = False

    def sync_light_links(self,obj,spec):
        meshes={name:mesh for name,mesh in self.objects.items() if mesh.type=='MESH'}
        for field,prop in (('receivers','receiver_collection'),('shadow_blockers','blocker_collection')):
            if field not in spec:continue
            included=tuple(sorted(set(spec[field]) & meshes.keys()))
            if len(included)==len(meshes):
                setattr(obj.light_linking,prop,None)
                continue
            key=(included,tuple(sorted(meshes)) if not included else ())
            collection=self.link_collections.get(key)
            if collection is None:
                collection=bpy.data.collections.new('EeveeMayaLightLinks')
                collection['eevee_bridge_links']=True
                # An empty Blender linking collection means "all". Excluding
                # every mesh is required for Maya's explicit "no receivers".
                for name in included or tuple(sorted(meshes)):
                    collection.objects.link(meshes[name])
                    collection.collection_objects[-1].light_linking.link_state='INCLUDE' if included else 'EXCLUDE'
                self.link_collections[key]=collection
            setattr(obj.light_linking,prop,collection)

    def update(self, request):
        self.deltas = list(records(request["mesh_delta"])) if request.get("mesh_delta") else []
        if "meshes" in request and any(spec.get("binary_geometry") for spec in request["meshes"]):
            for delta in self.deltas:
                spec = request["meshes"][delta["index"]]
                spec["visible"] = delta["visible"]
                if "points" in delta: spec["points_buffer"] = delta["points"]
                if "normals" in delta: spec["normals_buffer"] = delta["normals"]
                if "matrix" in delta: spec["matrix"] = np.frombuffer(delta["matrix"], dtype="<f8").tolist()
            worker.build_scene(request, transmission_preview=True, progress=self.progress)
            self.light_signature = None
            self.light_specs = {}
            self.link_collections = {}
            self.display_signature = None
            self.texture_links = []
            self.objects = {obj["maya_path"]: obj for obj in bpy.context.scene.objects if obj.type == "MESH" and "maya_path" in obj}
            self.original_materials={name:list(obj.data.materials) for name,obj in self.objects.items()}
            self.names = [spec["name"] for spec in request["meshes"]]
            self.rebuilds += 1
            self.previous = None
            return
        if "meshes" not in request and self.deltas:
            for delta in self.deltas:
                obj = self.objects[self.names[delta["index"]]]
                if "matrix" in delta:
                    obj.matrix_world = worker.transform(np.frombuffer(delta["matrix"], dtype="<f8").tolist())
                if "points" in delta:
                    obj.data.vertices.foreach_set("co", np.frombuffer(delta["points"], dtype="<f4"))
                if "normals" in delta:
                    worker.set_normals(obj.data, np.frombuffer(delta["normals"], dtype="<f4"))
                if "points" in delta or "normals" in delta:
                    obj.data.update()
                if delta["flags"] & 16:
                    obj.hide_viewport = not delta["visible"]
                    obj.hide_render = not delta["visible"]
            self.updates += 1
            return
        if "meshes" not in request:
            return
        previous = self.previous
        rebuild = previous is None
        if previous:
            rebuild = any(previous[key] != request[key] for key in ("materials", "lights", "studio"))
            rebuild = rebuild or len(previous["meshes"]) != len(request["meshes"])
            if not rebuild:
                for old, new in zip(previous["meshes"], request["meshes"]):
                    if any(old[key] != new[key] for key in
                           ("name", "counts", "indices", "uvs", "materials", "face_materials")):
                        rebuild = True
                        break
        if rebuild:
            worker.build_scene(request, transmission_preview=True, progress=self.progress)
            self.light_signature = None
            self.light_specs = {}
            self.link_collections = {}
            self.display_signature = None
            self.texture_links = []
            self.objects = {obj["maya_path"]: obj for obj in bpy.context.scene.objects if "maya_path" in obj}
            self.original_materials={name:list(obj.data.materials) for name,obj in self.objects.items() if obj.type=="MESH"}
            self.rebuilds += 1
            self.names = [spec["name"] for spec in request["meshes"]]
        else:
            for old, new in zip(previous["meshes"], request["meshes"]):
                obj = self.objects[new["name"]]
                if old["matrix"] != new["matrix"]:
                    obj.matrix_world = worker.transform(new["matrix"])
                if old["points"] != new["points"]:
                    obj.data.vertices.foreach_set("co", np.asarray(new["points"], dtype=np.float32).ravel())
                    obj.data.update()
                if old["normals"] != new["normals"]:
                    worker.set_normals(obj.data, new["normals"])
                    obj.data.update()
            self.updates += 1
        self.previous = {key: request[key] for key in ("meshes", "materials", "lights", "studio")}

    def sync_lights(self, request):
        if "native" not in request:
            return
        native = request["native"]
        signature = (request["lights"], native["displayLights"], native.get("selected_lights", []),native["shadows"])
        if signature == self.light_signature:
            return
        ambient_enabled=any(spec['kind']=='ambientLight' for spec in request['lights'])
        if ambient_enabled or self.ambient_enabled:
            worker.sync_ambient(self.objects,request['lights'],native)
        self.ambient_enabled=ambient_enabled
        existing = {obj["maya_path"]: obj for obj in bpy.context.scene.objects if obj.type == "LIGHT" and "maya_path" in obj}
        lights=worker.expand_spot_profiles(request['lights'])
        wanted = {spec["name"] for spec in lights}
        for name, obj in existing.items():
            if name not in wanted:
                data = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if data.users == 0: bpy.data.lights.remove(data)
        mode = native["displayLights"]
        effective_specs={}
        for spec in lights:
            # Enforce the panel switch on the actual light too; do not rely on
            # legacy/global Eevee flags to disable a cached shadow caster.
            spec=dict(spec,shadows=bool(spec.get("shadows",False) and native["shadows"]))
            effective_specs[spec["name"]]=spec
            obj = existing.get(spec["name"])
            previous = self.light_specs.get(spec["name"])
            created = obj is None
            if obj is None: obj = worker.create_light(spec)
            elif previous != spec:
                worker.apply_light(obj, spec, previous)
            # Transform/intensity/cone edits do not change receiver membership.
            # Avoid rebuilding mesh sets and reassigning Blender collections for
            # every helper light of a dropoff profile. Scene rebuilds reset the
            # previous specs, and new lights always initialize their links.
            if created or not same_light_links(spec, previous):
                self.sync_light_links(obj,spec)
            visible = mode == "all" or (mode in ("selected", "active") and spec.get('maya_source',spec['name']) in native.get("selected_lights", []))
            set_light_visibility(obj, visible)
        headlight = bpy.data.objects.get("EeveeDefaultHeadlight")
        if headlight:
            if headlight.data.use_shadow: headlight.data.use_shadow = False
            set_light_visibility(headlight, mode == 'default')
        for name in ("EeveeStudioKey", "EeveeStudioFill"):
            obj = bpy.data.objects.get(name)
            if obj: set_light_visibility(obj, False)
        sync_environment(mode)
        self.light_signature = signature
        self.light_specs = effective_specs
        for key,collection in list(self.link_collections.items()):
            if collection.users==0:
                bpy.data.collections.remove(collection);del self.link_collections[key]

    def sync_display(self, request):
        native = request.get("native")
        if not native: return
        signature = (native["displayTextures"], native["useDefaultMaterial"])
        if signature == self.display_signature: return
        if native["displayTextures"]:
            for tree, output, input_ in self.texture_links:
                tree.links.new(output, input_)
            self.texture_links = []
        else:
            for mat in bpy.data.materials:
                if not mat.use_nodes: continue
                tree = mat.node_tree
                for link in list(tree.links):
                    if link.from_node.type == "TEX_IMAGE":
                        self.texture_links.append((tree, link.from_socket, link.to_socket))
                        tree.links.remove(link)
        if native["useDefaultMaterial"]:
            mat = bpy.data.materials.get("EeveeNativeDefaultMaterial")
            if mat is None:
                mat = bpy.data.materials.new("EeveeNativeDefaultMaterial")
                mat.use_nodes = True
                shader = mat.node_tree.nodes.get("Principled BSDF")
                shader.inputs["Base Color"].default_value = (.5, .5, .5, 1)
                shader.inputs["Roughness"].default_value = .5
            if self.ambient_enabled:worker.install_ambient_material(mat)
            for obj in self.objects.values():
                if obj.type!="MESH":continue
                obj['eevee_depth_surface']=True
                for i in range(len(obj.data.materials)):obj.data.materials[i]=mat
        else:
            for name,materials in self.original_materials.items():
                obj=self.objects[name]
                obj['eevee_depth_surface']=obj.get('eevee_source_depth_surface',True)
                for i,mat in enumerate(materials):obj.data.materials[i]=mat
        # A view-layer override would also turn the atmosphere into a solid cube.
        bpy.context.view_layer.material_override = None
        self.display_signature = signature


def update_camera(request):
    spec = request["camera"]
    cam = bpy.context.scene.camera
    worker.apply_camera(cam,spec)
    headlight = bpy.data.objects.get("EeveeDefaultHeadlight")
    if headlight:
        headlight.matrix_world = cam.matrix_world
    return cam


def sync_environment(mode):
    """A visible backdrop is independent of the lights selected in Maya."""
    scene = bpy.context.scene
    scene.world.use_nodes = True
    tree = scene.world.node_tree
    ambient=tree.nodes.get("EeveeAmbientLighting")
    if ambient is None:
        background=tree.nodes.get("Background") or tree.nodes.new("ShaderNodeBackground")
        background.inputs[0].default_value=(.12,.12,.12,1);background.inputs[1].default_value=.5
        ambient=tree.nodes.new("ShaderNodeBackground");ambient.name="EeveeAmbientLighting"
        ambient.inputs[0].default_value=(1,1,1,1)
        path=tree.nodes.new("ShaderNodeLightPath");path.name="EeveeBackgroundOnly"
        mix=tree.nodes.new("ShaderNodeMixShader");mix.name="EeveeBackgroundMix"
        tree.links.new(path.outputs["Is Camera Ray"],mix.inputs[0])
        tree.links.new(ambient.outputs[0],mix.inputs[1]);tree.links.new(background.outputs[0],mix.inputs[2])
        output=next(node for node in tree.nodes if node.type=="OUTPUT_WORLD")
        tree.links.new(mix.outputs[0],output.inputs["Surface"])
    strength=1.0 if mode=="flat" else 0.0
    if ambient.inputs[1].default_value!=strength:ambient.inputs[1].default_value=strength


def update_effects(request):
    spec = request.get("effects", {})
    scene = bpy.context.scene
    scene.world.use_nodes = True
    tree = scene.world.node_tree
    output = next(node for node in tree.nodes if node.type == "OUTPUT_WORLD")
    for link in list(output.inputs["Volume"].links):tree.links.remove(link)
    obj=bpy.data.objects.get("EeveeAtmosphereVolume")
    if obj is None:
        mesh=bpy.data.meshes.new("EeveeAtmosphereBounds")
        mesh.from_pydata([(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)],[],
                         [(0,3,2,1),(4,5,6,7),(0,1,5,4),(3,7,6,2),(0,4,7,3),(1,2,6,5)])
        mesh.update();obj=bpy.data.objects.new("EeveeAtmosphereVolume",mesh)
        scene.collection.objects.link(obj)
        mat=bpy.data.materials.new("EeveeAtmosphereMaterial");mat.use_nodes=True
        mat.node_tree.nodes.clear()
        material_output=mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
        scatter=mat.node_tree.nodes.new("ShaderNodeVolumeScatter");scatter.name="EeveeAtmosphere"
        mat.node_tree.links.new(scatter.outputs[0],material_output.inputs["Volume"])
        mesh.materials.append(mat)
    obj.hide_viewport=obj.hide_render=not spec.get("fog",False)
    scatter=obj.data.materials[0].node_tree.nodes["EeveeAtmosphere"]
    scatter.inputs["Color"].default_value=(*spec.get("fog_color",(.8,.85,1)),1)
    scatter.inputs["Anisotropy"].default_value=max(-.99,min(.99,spec.get("anisotropy",.3)))
    scene.eevee.volumetric_tile_size=str(spec.get("volume_tile",4))
    scene.eevee.volumetric_samples=spec.get("volume_samples",32)


def world_bounds(objects):
    """Cacheable world corners; camera movement does not change these points."""
    corners=[]
    for obj in objects:
        if obj.type!='MESH' or obj.hide_viewport:continue
        matrix=np.asarray(obj.matrix_world,dtype=np.float64)
        corners.append(np.asarray(obj.bound_box,dtype=np.float64) @ matrix[:3,:3].T+matrix[:3,3])
    return np.concatenate(corners) if corners else np.empty((0,3),dtype=np.float64)


def position_atmosphere(request,objects=(),bounds=None):
    """Finite camera-aligned volume: a world volume absorbs sunlight at infinity."""
    obj=bpy.data.objects.get("EeveeAtmosphereVolume")
    if obj is None or not request.get("effects",{}).get("fog"):return
    camera=request["camera"];spec=request["effects"];scene=bpy.context.scene
    scale=max(.000001,worker.transform(camera["matrix"]).col[2].to_3d().length)
    start=max(.0001,camera["near"])
    end=max(start*1.01,min(camera["far"],spec.get("fog_distance",100)))
    if spec.get('fog_auto_range',True):
        view=np.asarray(scene.camera.matrix_world.inverted(),dtype=np.float64)
        points=world_bounds(objects) if bounds is None else bounds
        if len(points):
            farthest=float(np.max(-(points @ view[2,:3]+view[2,3])))
            if farthest>start:end=max(end,min(camera['far'],farthest*1.05))
    half_x=(camera["ortho_width"]*.5*scale if camera["orthographic"] else end*math.tan(camera["fov_x"]*.5))*1.1
    half_y=half_x*request["height"]/request["width"]
    obj.matrix_world=scene.camera.matrix_world @ Matrix.Translation((0,0,-(start+end)*.5)) @ Matrix.Diagonal((half_x,half_y,(end-start)*.5,1))
    obj.data.materials[0].node_tree.nodes["EeveeAtmosphere"].inputs["Density"].default_value=max(0,spec.get("fog_density",.015))
    scene.eevee.use_volume_custom_range=True
    scene.eevee.volumetric_start=start;scene.eevee.volumetric_end=end
    scene.eevee.volumetric_sample_distribution=.8

"""Interactive Eevee GPU viewport -> shared memory. Requires a Blender UI context."""
import argparse
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import time
import traceback
import os

import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader


def hide_own_helper_window():
    """The renderer is a helper: hide only windows owned by this Blender PID."""
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    def hide(window, data):
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(window, ctypes.byref(pid))
        if pid.value == os.getpid():
            user.ShowWindow(window, 0)
        return True
    callback = callback_type(hide)
    user.EnumWindows(callback, 0)


hide_own_helper_window()

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "blender"))
from eevee_maya.protocol import read_json, write_json
from eevee_maya.shared_frame import SharedFrame, SharedMailbox
from eevee_maya.gpu_share import GpuShare
from eevee_maya.mesh_packet import records
from eevee_maya import shadow_quality
from eevee_maya.gpu_lifetime import RetiredGpuPools
from scene_sync import SceneMirror, update_camera, update_effects, position_atmosphere, world_bounds
import worker

parser = argparse.ArgumentParser()
parser.add_argument("--session", required=True)
parser.add_argument("--parent-pid", type=int, required=True)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
session = Path(args.session)
shared = SharedFrame(session.name)
requests = SharedMailbox(session.name, "request", 256 * 1024 * 1024)
responses = SharedMailbox(session.name, "response", 1024 * 1024)
mirror = SceneMirror()
state = {"last_id": 0, "offscreen": None, "depth_offscreen": None, "depth_batches": {},
         "last_effects": None, "area": None, "size": None, "retired_gpu": RetiredGpuPools()}


def startup_progress(stage, completed=0, total=0):
    if state.get('rendered_once'): return
    now = time.monotonic()
    if stage == state.get('startup_stage') and now - state.get('startup_updated', 0) < .1: return
    write_json(session / 'startup.json', {'stage':stage, 'completed':completed, 'total':total})
    state['startup_stage'], state['startup_updated'] = stage, now


mirror.progress = startup_progress
kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel.OpenProcess.restype = wintypes.HANDLE
kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
kernel.CloseHandle.argtypes = [wintypes.HANDLE]
parent = kernel.OpenProcess(0x1000, False, args.parent_pid)


def close():
    if state.get("pump"):
        bpy.context.window_manager.event_timer_remove(state["pump"])
    for item in state.get("gpu_pool", []):
        item.close()
    state['retired_gpu'].close()
    for key in ("offscreen", "depth_offscreen"):
        if state[key]:
            state[key].free()
    shared.close()
    requests.close()
    responses.close()
    if parent:
        kernel.CloseHandle(parent)
    write_json(session / "exited.json", {"pid": __import__("os").getpid()})
    bpy.ops.wm.quit_blender()


def rebuild_depth_batches(request):
    if "meshes" not in request:
        for delta in mirror.deltas:
            if "points" not in delta: continue
            name = mirror.names[delta["index"]]
            old = state["depth_batches"][name]
            points = np.frombuffer(delta["points"], dtype="<f4").reshape(-1, 3)
            vbo = gpu.types.GPUVertBuf(state["depth_format"], len=len(points))
            vbo.attr_fill(id="pos", data=points)
            batch = gpu.types.GPUBatch(type="TRIS", buf=vbo, elem=old[4])
            state["depth_batches"][name] = (None, None, batch, old[3], old[4])
        return
    shader = state.get("depth_shader")
    if shader is None:
        info = gpu.types.GPUShaderCreateInfo()
        info.push_constant("MAT4", "ModelViewProjectionMatrix")
        info.vertex_in(0, "VEC3", "pos")
        info.fragment_out(0, "VEC4", "fragColor")
        info.vertex_source("void main(){gl_Position=ModelViewProjectionMatrix*vec4(pos,1.0);}")
        info.fragment_source("void main(){fragColor=vec4(gl_FragCoord.z);}")
        shader = gpu.shader.create_from_info(info)
        state["depth_shader"] = shader
        fmt = gpu.types.GPUVertFormat()
        fmt.attr_add(id="pos", comp_type="F32", len=3, fetch_mode="FLOAT")
        state["depth_format"] = fmt
    previous = state["depth_batches"]
    batches = {}
    for spec in request["meshes"]:
        old = previous.get(spec["name"])
        if old and not spec.get("binary_geometry") and old[0] == spec["points"] and old[1] == spec["indices"]:
            batches[spec["name"]] = old
            continue
        obj = mirror.objects[spec["name"]]
        obj.data.calc_loop_triangles()
        triangles = np.empty(len(obj.data.loop_triangles) * 3, dtype=np.int32)
        obj.data.loop_triangles.foreach_get("vertices", triangles)
        points = np.frombuffer(spec["points_buffer"], dtype="<f4").reshape(-1, 3) if spec.get("binary_geometry") else spec["points"]
        triangles = triangles.reshape(-1, 3)
        vbo = gpu.types.GPUVertBuf(state["depth_format"], len=len(points))
        vbo.attr_fill(id="pos", data=points)
        ibo = gpu.types.GPUIndexBuf(type="TRIS", seq=triangles)
        batch = gpu.types.GPUBatch(type="TRIS", buf=vbo, elem=ibo)
        batches[spec["name"]] = (None if spec.get("binary_geometry") else spec["points"], spec["indices"], batch, triangles, ibo)
    state["depth_batches"] = batches


def render_depth(width, height, view, projection, gpu_transport=False):
    with state["depth_offscreen"].bind():
        buffer = gpu.state.active_framebuffer_get()
        buffer.clear(color=(1, 1, 1, 1), depth=1.0)
        gpu.state.depth_test_set("LESS_EQUAL")
        gpu.state.depth_mask_set(True)
        with gpu.matrix.push_pop():
            gpu.matrix.load_matrix(view)
            gpu.matrix.load_projection_matrix(projection)
            shader = state["depth_shader"]
            shader.bind()
            for name, (_, _, batch, _, _) in state["depth_batches"].items():
                if mirror.objects[name].hide_viewport or not mirror.objects[name].get('eevee_depth_surface',True): continue
                with gpu.matrix.push_pop():
                    gpu.matrix.multiply_matrix(mirror.objects[name].matrix_world)
                    batch.draw(shader)
        if gpu_transport:
            state["gpu"].publish(1)
            depth = None
        else:
            depth = np.asarray(buffer.read_depth(0, 0, width, height), dtype=np.float32).copy()
        gpu.state.depth_test_set("NONE")
        gpu.state.depth_mask_set(False)
    return depth


def tick():
    try:
        state['retired_gpu'].collect(shared.presented_id)
        exit_code = wintypes.DWORD()
        if (session / "stop").exists() or not parent or not kernel.GetExitCodeProcess(parent, ctypes.byref(exit_code)) or exit_code.value != 259:
            close()
            return None
        if state["area"] is None:
            # Blender may create/show its main window after the startup script.
            hide_own_helper_window()
            area = next(a for a in bpy.context.screen.areas if a.type == "VIEW_3D")
            space = area.spaces.active
            space.shading.type = "RENDERED"
            space.shading.use_scene_world_render = True
            space.shading.use_scene_lights_render = True
            space.shading.use_dof = True
            space.overlay.show_overlays = False
            space.region_3d.view_perspective = "CAMERA"
            state.update(area=area, space=space,
                         region=next(r for r in area.regions if r.type == "WINDOW"))
            # Keep Blender's UI event loop responsive while its helper window is
            # hidden; app timers alone are throttled by the idle event loop.
            state["pump"] = bpy.context.window_manager.event_timer_add(0.005, window=bpy.context.window)
            write_json(session / "ready.json", {"blender": bpy.app.version_string, "backend": "GPUOffScreen"})
        request = requests.read(state["last_id"])
        if request is None:
            return 0.005
        state["last_id"] = request["id"]
        started = time.perf_counter()
        limit = int(request.get("texture_limit", 2048))
        setting = "CLAMP_" + str(limit) if limit in (128,256,512,1024,2048,4096,8192) else "CLAMP_OFF"
        if bpy.context.preferences.system.gl_texture_limit != setting:
            bpy.context.preferences.system.gl_texture_limit = setting
        mirror.update(request)
        if 'meshes' in request or any(delta['flags'] & (1|2|16) for delta in mirror.deltas):
            state['bounds_points']=None
        mirror.sync_lights(request)
        mirror.sync_display(request)
        mirror_finished = time.perf_counter()
        rebuild_depth_batches(request)
        sync_finished = time.perf_counter()
        cam = update_camera(request)
        # The shared-depth presentation applies the physical preview in Maya.
        # Applying Blender's DOF as well blurs the source before that pass and
        # makes a sharply focused surface impossible to recover downstream.
        cam.data.dof.use_dof = False
        # Offscreen drawing has no camera-object argument: Eevee still reads
        # the SpaceView3D clip range for culling, even with explicit matrices.
        state["space"].clip_start=cam.data.clip_start
        state["space"].clip_end=cam.data.clip_end
        state["space"].lens=cam.data.lens
        effects_changed=(not state.get("effects_applied") or request.get("effects") != state["last_effects"]
                         or bpy.data.objects.get("EeveeAtmosphereVolume") is None)
        if effects_changed:
            update_effects(request)
            state["last_effects"] = request.get("effects")
            state["effects_applied"] = True
        volume_view=(request["camera"],request["width"],request["height"])
        if effects_changed or volume_view!=state.get("volume_view") or mirror.deltas:
            if request.get('effects',{}).get('fog') and state.get('bounds_points') is None:
                state['bounds_points']=world_bounds(mirror.objects.values())
            position_atmosphere(request,bounds=state.get('bounds_points'));state["volume_view"]=volume_view
        scene = bpy.context.scene
        scene.render.engine = "BLENDER_EEVEE"
        scene.eevee.taa_samples = request.get("samples", 8)
        # IPC frames are independent snapshots. Reprojecting the previous
        # light/volume pose produces ghosting and flashes while editing in Maya.
        # Spatial AA still uses the requested sample count.
        scene.eevee.use_taa_reprojection = False
        native = request.get("native")
        if native:
            scene.eevee.use_shadows = bool(native["shadows"])
            ao = bool(native["ao"] and native["ao_amount"] > 0)
            # Native SSAO must also darken direct-lit surfaces without adding
            # environment illumination. Use the shared-depth GPU presentation.
            scene.eevee.use_raytracing = ao and not request.get("gpu_transport",False)
            scene.eevee.use_fast_gi = scene.eevee.use_raytracing
            scene.eevee.fast_gi_method = "AMBIENT_OCCLUSION_ONLY"
            scene.eevee.fast_gi_distance = native["ao_world_radius"]
            # AO must not silently enable the separate glossy reflection tracer.
            # Route all roughnesses through Fast GI's AO-only approximation.
            scene.eevee.ray_tracing_options.trace_max_roughness=0
        shadow_settings = request.get('shadow_settings', {})
        shadow_state = shadow_quality.apply(scene.eevee, {
            'shadow_quality': shadow_settings.get('preset', 'high'),
            'shadow_pool_size': shadow_settings.get('pool', 'auto')})
        color_state = worker.configure_color(request)
        state["space"].camera = cam
        width, height = request["width"], request["height"]
        gpu_transport = request.get("gpu_transport", False)
        if state["size"] != (width, height, gpu_transport):
            state["window_hidden_after_draw"]=False
            # A response for the old size may still be waiting for Maya's first
            # OpenSharedResource. Resize must not invalidate those handles.
            state['retired_gpu'].retire(state.get('gpu_pool', []), max(state.get('gpu_frames', [0])))
            state['retired_gpu'].collect(shared.presented_id)
            state["gpu_pool"] = []
            state["gpu"] = None
            for key in ("offscreen", "depth_offscreen"):
                if state[key]:
                    state[key].free()
            state["offscreen"] = gpu.types.GPUOffScreen(width, height, format="RGBA16F")
            state["depth_offscreen"] = gpu.types.GPUOffScreen(width, height, format="RGBA32F")
            if gpu_transport:
                state["generation"] = state.get("generation", 0) + 1
                state["gpu_generation"] = session.name + "_g" + str(state["generation"])
                state["gpu_pool"] = [GpuShare(state["gpu_generation"] + "_s" + str(i), width, height) for i in range(3)]
                state["gpu_frames"] = [0, 0, 0]
            state["size"] = (width, height, gpu_transport)
        if gpu_transport:
            slot = request["id"] % 3
            while state["gpu_frames"][slot] > shared.presented_id:
                if (session / "stop").exists():
                    close()
                    return None
                time.sleep(.001)
            state["gpu"] = state["gpu_pool"][slot]
        update_started = time.perf_counter()
        bpy.context.view_layer.update()
        update_finished = time.perf_counter()
        view, projection = worker.camera_matrices(cam,request['camera'],width,height)
        startup_progress('shaders')
        state["offscreen"].draw_view3d(scene, bpy.context.view_layer, state["space"], state["region"],
                                      view, projection, do_color_management=True)
        color_finished = time.perf_counter()
        with state["offscreen"].bind():
            audit=None
            if request.get("audit_color"):
                values=np.asarray(gpu.state.active_framebuffer_get().read_color(0,0,width,height,4,0,"FLOAT"),dtype=np.float32)
                audit=values[::16,::16,:3].tolist()
            if os.environ.get("EEVEE_RENDER_DEBUG")=="1":
                debug_color=np.asarray(gpu.state.active_framebuffer_get().read_color(0,0,width,height,4,0,"FLOAT"),dtype=np.float32)
                state["debug_color_std"]=float(debug_color[...,0].std())
            if gpu_transport:
                state["gpu"].publish(0)
            else:
                pixels = np.asarray(gpu.state.active_framebuffer_get().read_color(
                    0, 0, width, height, 4, 0, "FLOAT"), dtype=np.float32).copy()
        depth = render_depth(width, height, view, projection, gpu_transport)
        startup_progress('presenting')
        state['rendered_once'] = True
        seconds = time.perf_counter() - started
        if not gpu_transport:
            shared.write(request["id"], width, height, pixels, depth, seconds)
        response = {"id": request["id"], "seconds": seconds,
                   "interactive":bool(request.get("interactive",False)),
                   "navigating":bool(request.get("navigating",False)),
                   "color_audit":audit,
                   "engine": "BLENDER_EEVEE_VIEWPORT", "transport": "gpu_shared_texture" if gpu_transport else "shared_memory",
                   "retired_gpu_pools":len(state['retired_gpu'].pending),
                   "meshes": len(mirror.objects), "scene_rebuilds": mirror.rebuilds,
                   "incremental_updates": mirror.updates, "width": width, "height": height,
                   "effects": request.get("effects", {}),
                   "camera": request["camera"],
                   "render_camera":{"projection_kind":"perspective" if projection[3][3]==0 else "orthographic",
                                    "near":cam.data.clip_start,"far":cam.data.clip_end,
                                    "view_near":state["space"].clip_start,"view_far":state["space"].clip_end},
                   "native": request.get("native"),
                   "eevee_state": {"samples":scene.eevee.taa_samples,"shadows":scene.eevee.use_shadows,
                                   "shadow_quality":shadow_state,
                                   "transmission_preview_materials":[m.name for m in bpy.data.materials if m.get('eevee_transmission_preview')],
                                   "color_management":color_state,
                                   "source_dof":cam.data.dof.use_dof,"dof_backend":"shared_depth_preview",
                                   "temporal_reprojection":scene.eevee.use_taa_reprojection,
                                   "ao":bool(native and native["ao"]),
                                   "ao_backend":"shared_depth_gpu" if gpu_transport else "eevee_fast_gi",
                                   "reflection_trace_roughness":scene.eevee.ray_tracing_options.trace_max_roughness,
                                   "background_camera_only":bool(scene.world.node_tree.nodes.get("EeveeBackgroundOnly")),
                                   "environment":mirror.environment_state,
                                   "environment_strength":scene.world.node_tree.nodes["EeveeAmbientLighting"].inputs[1].default_value if scene.world.node_tree.nodes.get("EeveeAmbientLighting") else None,
                                   "volume_range":[scene.eevee.volumetric_start,scene.eevee.volumetric_end],
                                   "volume_density":bpy.data.objects['EeveeAtmosphereVolume'].data.materials[0].node_tree.nodes['EeveeAtmosphere'].inputs['Density'].default_value,
                                   "lights":len([o for o in bpy.context.scene.objects if o.type=="LIGHT" and not o.hide_viewport]),
                                   "light_details":[{"name":o.get("maya_path",o.name),"type":o.data.type,"energy":o.data.energy,
                                                     "diffuse":o.data.diffuse_factor,"specular":o.data.specular_factor,
                                                     "normalize":getattr(o.data,"normalize",None),"cutoff_distance":getattr(o.data,"cutoff_distance",None),
                                                     "custom_distance":getattr(o.data,'use_custom_distance',False),
                                                     "size_x":getattr(o.data,"size",None),"size_y":getattr(o.data,"size_y",None),
                                                     "shadows":o.data.use_shadow,
                                                     "shadow_angle":getattr(o.data,"angle",None),
                                                     "shadow_radius":getattr(o.data,"shadow_soft_size",None),
                                                     "position":list(o.matrix_world.translation),"color":list(o.data.color),
                                                     "volume":o.data.volume_factor,"spot_size":getattr(o.data,"spot_size",None),
                                                     "receivers":o.light_linking.receiver_collection.name if o.light_linking.receiver_collection else None,
                                                     "shadow_blockers":o.light_linking.blocker_collection.name if o.light_linking.blocker_collection else None,
                                                     "spot_blend":getattr(o.data,"spot_blend",None)}
                                                    for o in bpy.context.scene.objects if o.type=="LIGHT" and not o.hide_viewport]},
                   "maya_frame": request.get("maya_frame"),
                   "timings_ms": {"sync": (sync_finished-started)*1000,
                                  "mirror": (mirror_finished-started)*1000,
                                  "depth_geometry": (sync_finished-mirror_finished)*1000,
                                  "queue": (started-request.get("submitted_at", started))*1000,
                                  "color": (color_finished-sync_finished)*1000,
                                  "depsgraph": (update_finished-update_started)*1000,
                                  "draw_color": (color_finished-update_finished)*1000,
                                  "depth_share": (time.perf_counter()-color_finished)*1000},
                   "depth_min": float(depth.min()) if depth is not None else None,
                   "depth_max": float(depth.max()) if depth is not None else None}
        if gpu_transport:
            response["gpu_handles"] = state["gpu"].handles
            response["gpu_generation"] = state["gpu_generation"]
            response["gpu_identifier"] = state["gpu_generation"] + "_s" + str(slot)
            state["gpu_frames"][slot] = request["id"]
        if os.environ.get("EEVEE_RENDER_DEBUG")=="1":
            from mathutils import Vector
            response["debug_objects"]=[]
            for obj in list(mirror.objects.values())[:3]:
                center=obj.matrix_world @ (sum((Vector(v) for v in obj.bound_box),Vector())/8)
                clip=projection @ view @ Vector((*center,1))
                response["debug_objects"].append({"name":obj.name,"clip":list(clip),"matrix":[list(row) for row in obj.matrix_world],"hidden":obj.hide_viewport})
            response["debug_view"]=[list(row) for row in view]
            response["debug_projection"]=[list(row) for row in projection]
            response["debug_color_std"]=state["debug_color_std"]
            with state["depth_offscreen"].bind():
                values=np.asarray(gpu.state.active_framebuffer_get().read_color(0,0,width,height,1,0,"FLOAT"),dtype=np.float32)
                response["debug_depth_range"]=[float(values.min()),float(values.max())]
        response["finished_at"] = time.perf_counter()
        if not state.get("window_hidden_after_draw"):
            # GPU/context initialization can show a helper after startup.
            hide_own_helper_window();state["window_hidden_after_draw"]=True
        responses.write(request["id"], response)
        if time.monotonic() - state.get("last_diagnostics", 0) > 1:
            write_json(session / "response.json", response)
            state["last_diagnostics"] = time.monotonic()
    except Exception:
        error = {"id": state["last_id"], "error": traceback.format_exc()}
        write_json(session / "response.json", error)
        responses.write(state["last_id"], error)
    return 0.005


def render_loop():
    # This process is exclusively a renderer. Staying in one main-thread callback
    # avoids Blender's UI redraw/idle cycle between IPC requests; bpy/GPU calls
    # never move to a Python background thread.
    while True:
        delay = tick()
        if delay is None:
            return None
        time.sleep(0.0005)


bpy.app.timers.register(render_loop, first_interval=1)

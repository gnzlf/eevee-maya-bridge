"""Capability probe: real Eevee offscreen viewport, not final render / PNG loop."""
import json
from pathlib import Path
import sys
import time
import traceback

import bpy
import gpu
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))
import worker

state = {"index": 0, "durations": [], "offscreen": None}


def finish(result):
    (ROOT / "diagnostics" / "viewport_benchmark.json").write_text(json.dumps(result, indent=2))
    if state["offscreen"]:
        state["offscreen"].free()
    bpy.ops.wm.quit_blender()


def tick():
    try:
        if not state["offscreen"]:
            request = json.loads((ROOT / "diagnostics" / "smoke" / "request.json").read_text())
            worker.build_scene(request)
            scene = bpy.context.scene
            scene.render.engine = "BLENDER_EEVEE"
            scene.eevee.taa_samples = 8
            scene.world.use_nodes = True
            scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.12, 0.12, 0.12, 1)
            scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.5
            cam = scene.camera
            spec = request["camera"]
            cam.matrix_world = worker.transform(spec["matrix"])
            cam.data.sensor_fit = "HORIZONTAL"
            cam.data.angle = spec["fov_x"]
            cam.data.clip_start, cam.data.clip_end = spec["near"], spec["far"]
            area = next(a for a in bpy.context.screen.areas if a.type == "VIEW_3D")
            space = area.spaces.active
            space.shading.type = "RENDERED"
            space.shading.use_scene_world_render = True
            space.shading.use_scene_lights_render = True
            space.overlay.show_overlays = False
            space.region_3d.view_perspective = "CAMERA"
            space.camera = cam
            region = next(r for r in area.regions if r.type == "WINDOW")
            state.update(area=area, space=space, region=region, request=request)
            state["offscreen"] = gpu.types.GPUOffScreen(640, 360, format="RGBA16F")
        cam = bpy.context.scene.camera
        bpy.data.objects["|EeveeCube|EeveeCubeShape"].location.x = 1.25 + 0.2 * np.sin(state["index"] * 0.1)
        bpy.context.view_layer.update()
        started = time.perf_counter()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        projection = cam.calc_matrix_camera(depsgraph, x=640, y=360)
        state["offscreen"].draw_view3d(
            bpy.context.scene, bpy.context.view_layer, state["space"], state["region"],
            cam.matrix_world.inverted(), projection, do_color_management=True)
        with state["offscreen"].bind():
            buffer = gpu.state.active_framebuffer_get().read_color(0, 0, 640, 360, 4, 0, "FLOAT")
            pixels = np.asarray(buffer, dtype=np.float32).copy()
            depth = gpu.state.active_framebuffer_get().read_depth(0, 0, 640, 360)
            zvalues = np.asarray(depth, dtype=np.float32).copy()
        state["durations"].append(time.perf_counter() - started)
        state["index"] += 1
        if state["index"] >= 40:
            image = bpy.data.images.new("EeveeViewportBenchmark", width=640, height=360, float_buffer=True)
            image.pixels.foreach_set(pixels.ravel())
            image.file_format = "OPEN_EXR"
            image.filepath_raw = str(ROOT / "diagnostics" / "viewport_offscreen.exr")
            image.save()
            timings = state["durations"][5:]
            finish({"passed": True, "backend": gpu.platform.backend_type_get(),
                    "renderer": gpu.platform.renderer_get(), "width": 640, "height": 360,
                    "frames": len(timings), "mean_ms": float(np.mean(timings) * 1000),
                    "p95_ms": float(np.percentile(timings, 95) * 1000),
                    "depth_min": float(zvalues.min()), "depth_max": float(zvalues.max()),
                    "all_frame_seconds": state["durations"]})
            return None
        return 0.01
    except Exception:
        finish({"passed": False, "error": traceback.format_exc()})
        return None


bpy.app.timers.register(tick, first_interval=2)

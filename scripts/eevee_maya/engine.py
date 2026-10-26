"""Manage one persistent Blender worker and asynchronous frame exchange."""
import hashlib
import json
import pickle
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
from collections import deque

from .protocol import read_json, write_json

ROOT = Path(__file__).resolve().parents[2]


def settings():
    defaults = {"blender": r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe",
                "max_width": 640, "samples": 1, "interval_ms": 1, "studio": False,
                "backend": "viewport", "adaptive_quality": True, "interaction_width": 960,
                "fast_navigation": True, "navigation_width": 640,
                "shadow_quality": "high", "shadow_pool_size": "auto"}
    path = ROOT / "config.json"
    if path.exists():
        defaults.update(read_json(path))
    # Installed releases keep user preferences outside immutable version folders.
    if ROOT.parent.name == 'versions':
        user_path = ROOT.parent.parent / 'config.json'
        if user_path.exists():defaults.update(read_json(user_path))
    return defaults


class Engine:
    def __init__(self):
        self.config = settings()
        self.process = None
        self.session = None
        self.log = None
        self.sent_id = 0
        self.received_id = 0
        self.signature = None
        self.image = None
        self.last_response = {}
        self.status = "Detenido"
        self.started = 0
        self.shared = None
        self.frame = None
        self.request_mailbox = self.response_mailbox = None
        self.ready = False
        self.gpu = False
        # Queueing an extra pose helps playback throughput but makes direct
        # manipulator/attribute edits visibly trail Maya's native overlays.
        self.playing = False
        self.history = deque(maxlen=4096)
        self.startup_stage = {'stage': 'starting'}
        self.startup_read_at = 0

    def start(self):
        if self.process and self.process.poll() is None:
            return
        blender = Path(self.config["blender"])
        if not blender.is_file():
            raise RuntimeError("No se encuentra Blender: " + str(blender))
        self.session = Path(tempfile.gettempdir()) / "eevee_maya" / uuid.uuid4().hex
        self.session.mkdir(parents=True)
        self.log = open(self.session / "blender.log", "w", encoding="utf-8")
        interactive = self.config["backend"] == "viewport"
        if interactive:
            from .shared_frame import SharedFrame, SharedMailbox
            self.shared = SharedFrame(self.session.name)
            self.request_mailbox = SharedMailbox(self.session.name, "request", 256 * 1024 * 1024)
            self.response_mailbox = SharedMailbox(self.session.name, "response", 1024 * 1024)
        command = [str(blender)] + (["--window-geometry", "0", "0", "128", "128"] if interactive else ["--background"])
        command += ["--factory-startup", "--python", str(ROOT / "blender" /
                   ("viewport_worker.py" if interactive else "worker.py")), "--", "--session",
                    str(self.session), "--parent-pid", str(os.getpid())]
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        environment = os.environ.copy()
        environment["TEMP"] = environment["TMP"] = str(self.session)
        self.process = subprocess.Popen(command, stdout=self.log, stderr=subprocess.STDOUT,
                                        startupinfo=startup,
                                        env=environment,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.started = time.monotonic()
        self.sent_id = self.received_id = 0
        self.last_response = {}
        self.frame = self.image = None
        self.history.clear()
        self.signature = None
        self.ready = False
        self.startup_stage = {'stage': 'starting'}
        self.startup_read_at = 0
        self.status = "Iniciando Blender / Eevee..."

    def startup_progress(self):
        if self.sent_id and time.monotonic() - self.startup_read_at >= .1:
            self.startup_read_at = time.monotonic()
            try:
                self.startup_stage = read_json(self.session / 'startup.json')
            except (OSError, ValueError):
                pass
        return self.startup_stage

    def poll(self):
        if not self.process:
            return False
        if self.process.poll() is not None:
            self.status = "Blender termino. Registro: " + str(self.session / "blender.log")
            return False
        path = self.session / "response.json"
        if self.response_mailbox:
            response = self.response_mailbox.read(self.received_id)
            if response is None:
                return False
        else:
            if not path.exists():
                return False
            response = read_json(path)
        if response["id"] <= self.received_id:
            return False
        if "error" in response:
            self.received_id = response["id"]
            self.last_response = response
            self.status = "Error de Eevee; ver " + str(path)
            return False
        if self.shared:
            if response.get("transport") == "gpu_shared_texture":
                frame = {key: response[key] for key in ("id", "width", "height", "gpu_handles")}
                frame["gpu_session"] = response.get("gpu_identifier", self.session.name)
                frame["gpu_generation"] = response.get("gpu_generation", self.session.name)
                frame["maya_frame"] = response.get("maya_frame")
            else:
                frame = self.shared.read(self.received_id)
                if frame is None:
                    return False
            self.frame = frame
            self.frame["effects"] = response.get("effects", {})
            self.frame["camera"] = response.get("camera", {})
            self.frame["native"] = response.get("native", {})
        else:
            self.image = self.session / response["image"]
        self.received_id = response["id"]
        self.last_response = response
        self.history.append(dict(response))
        self.status = "Eevee %d×%d (%s) | %d mallas | %.1f ms" % (
            response['width'],response['height'],'navegación rápida' if response.get('navigating') else ('previa al editar' if response.get('interactive') else 'calidad completa'),
            response["meshes"], response["seconds"] * 1000)
        return True

    @property
    def available(self):
        if self.process and not self.ready:
            self.ready = (self.session / "ready.json").exists()
        return bool(self.process and self.process.poll() is None
                    and self.ready
                    and (self.request_mailbox.consumed_id >= self.sent_id if self.gpu and self.playing and self.config.get("pipeline", False)
                         else self.sent_id == self.received_id))

    def submit(self, snapshot, force=False):
        snapshot = dict(snapshot)
        snapshot.pop("id", None)
        scene_changed = False
        if self.request_mailbox:
            scene_changed = "meshes" in snapshot or bool(snapshot.get("mesh_delta", b"\0\0\0\0")[:4] != b"\0\0\0\0")
            metadata = {key: value for key, value in snapshot.items() if key not in
                        ("mesh_delta", "meshes", "materials", "studio", "warnings", "unit", "maya_frame")}
            data = pickle.dumps(metadata, protocol=4)
        else:
            data = json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
        signature = hashlib.sha256(data).hexdigest()
        if signature == self.signature and not force and not scene_changed:
            return False
        self.sent_id += 1
        snapshot["id"] = self.sent_id
        snapshot["gpu_transport"] = self.gpu
        snapshot["submitted_at"] = time.perf_counter()
        snapshot["texture_limit"] = self.config.get("texture_limit", 2048)
        if self.request_mailbox:
            self.request_mailbox.write(self.sent_id, snapshot)
        else:
            write_json(self.session / "request.json", snapshot)
        self.signature = signature
        return True

    def prune_frames(self):
        # Keep current and previous frames while the renderer releases textures.
        for path in self.session.glob("frame_*.png"):
            try:
                if int(path.stem.split("_")[-1]) < self.received_id - 1:
                    path.unlink()
            except OSError:
                pass

    def stop(self):
        if self.session:
            (self.session / "stop").touch()
        if self.process and self.process.poll() is None:
            try:
                self.process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
        self.process = None
        if self.log:
            self.log.close()
            self.log = None
        self.status = "Detenido"
        if self.shared:
            self.shared.close()
            self.shared = None
        for mailbox in (self.request_mailbox, self.response_mailbox):
            if mailbox:
                mailbox.close()
        self.request_mailbox = self.response_mailbox = None

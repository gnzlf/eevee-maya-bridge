"""Temporary interaction quality; never changes Maya attributes or capture size."""
import hashlib
import pickle
import time


class InteractionQuality:
    def __init__(self):
        self.signature = None
        self.changed_at = 0
        self.camera_signature = None
        self.navigation_at = -float('inf')
        self.maya_frame = None

    def apply(self, snapshot, config, playing=False, now=None):
        now = time.monotonic() if now is None else now
        controls = tuple(snapshot.get(key) for key in ('camera', 'lights', 'effects', 'native', 'maya_frame'))
        camera = snapshot.get('camera') or {}
        navigation = tuple(camera.get(key) for key in ('matrix','orthographic','ortho_width','fov_x','shift_x','shift_y'))
        camera_signature = pickle.dumps(navigation, protocol=4)
        timeline_changed = snapshot.get('maya_frame') != self.maya_frame
        self.maya_frame = snapshot.get('maya_frame')
        if playing or timeline_changed:
            self.navigation_at = -float('inf')
        elif self.camera_signature is not None and camera_signature != self.camera_signature:
            self.navigation_at = now
        self.camera_signature = camera_signature
        signature = hashlib.sha256(pickle.dumps(controls, protocol=4)).digest()
        # Mesh deltas include object matrices, evaluated points/normals and
        # visibility. They do not change camera/light controls, but are edits
        # too. Ignore the empty count header so idle restores full quality.
        geometry_changed = bool(any((snapshot.get('mesh_delta') or b'')[:4]))
        if signature != self.signature or geometry_changed:
            self.signature, self.changed_at = signature, now
        interactive = bool(config.get('adaptive_quality', True) and
                           (playing or now - self.changed_at < .4))
        snapshot['interactive'] = interactive
        navigating = bool(interactive and not playing and config.get('fast_navigation',True) and now-self.navigation_at < .4)
        snapshot['navigating'] = navigating
        if interactive:
            width, height = snapshot['width'], snapshot['height']
            maximum = max(64, int(config.get('interaction_width', 960)))
            if navigating:
                maximum = max(64, int(config.get('navigation_width',640)))
            if width > maximum:
                snapshot['width'] = maximum
                snapshot['height'] = max(64, round(height * maximum / width))
            # Keep Maya's AA count on each animated pose. Two samples caused
            # visible noise and shimmering even with the native AA button on.
        return snapshot

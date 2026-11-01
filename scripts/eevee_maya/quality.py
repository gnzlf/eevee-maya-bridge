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
        self.interactive = False

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
        settle = settle_seconds(config)
        interactive = bool(config.get('adaptive_quality', True) and
                           (playing or now - self.changed_at < settle))
        snapshot['interactive'] = interactive
        navigating = bool(interactive and not playing and config.get('fast_navigation',True) and now-self.navigation_at < settle)
        snapshot['navigating'] = navigating
        self.interactive = interactive
        if interactive:
            width, height = snapshot['width'], snapshot['height']
            maximum = max(64, int(config.get('interaction_width', 960)))
            if navigating:
                maximum = max(64, int(config.get('navigation_width',640)))
            if width > maximum:
                snapshot['width'] = maximum
                snapshot['height'] = max(64, round(height * maximum / width))
            # Like Blender's own viewport: a single, un-jittered sample while
            # the pose/camera changes, then Maya's full AA count on settle.
            # One sample is stable (no jitter), unlike the old 2-sample test
            # which alternated subpixel offsets and shimmered.
            limit = interaction_samples(config)
            if limit and int(snapshot.get('samples', 1)) > limit:
                snapshot['samples'] = limit
        return snapshot

    def settle_due(self, config, now=None):
        """True once a reduced preview must be replaced by final quality."""
        if not getattr(self, 'interactive', False):
            return False
        now = time.monotonic() if now is None else now
        return now - self.changed_at >= settle_seconds(config)


def settle_seconds(config):
    try:
        return max(.05, min(2.0, float(config.get('settle_seconds', .3))))
    except (TypeError, ValueError):
        return .3


def interaction_samples(config):
    """0 keeps Maya's AA while interacting; otherwise an upper sample limit."""
    try:
        value = int(config.get('interaction_samples', 1))
    except (TypeError, ValueError):
        return 1
    return value if value in (0, 1, 2, 4, 8) else 1

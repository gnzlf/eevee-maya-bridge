"""Temporary interaction quality; never changes Maya attributes or capture size."""
import hashlib
import pickle
import time


class InteractionQuality:
    def __init__(self):
        self.signature = None
        self.changed_at = 0

    def apply(self, snapshot, config, playing=False, now=None):
        now = time.monotonic() if now is None else now
        controls = tuple(snapshot.get(key) for key in ('camera', 'lights', 'effects', 'native', 'maya_frame'))
        signature = hashlib.sha256(pickle.dumps(controls, protocol=4)).digest()
        if signature != self.signature:
            self.signature, self.changed_at = signature, now
        interactive = bool(config.get('adaptive_quality', True) and
                           (playing or now - self.changed_at < .4))
        snapshot['interactive'] = interactive
        if interactive:
            width, height = snapshot['width'], snapshot['height']
            maximum = max(64, int(config.get('interaction_width', 960)))
            if width > maximum:
                snapshot['width'] = maximum
                snapshot['height'] = max(64, round(height * maximum / width))
            # Keep Maya's AA count on each animated pose. Two samples caused
            # visible noise and shimmering even with the native AA button on.
        return snapshot

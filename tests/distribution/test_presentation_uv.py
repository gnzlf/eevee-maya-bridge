"""Previous frames keep their projection while a panel is resized (no stretching)."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from eevee_maya.gpu_share import IDENTITY_UV, presentation_uv


def perspective(fov_x, aspect, shift=(0.0, 0.0)):
    """VP2 row-major OpenGL projection (row vectors), horizontal fit."""
    sx = 1 / math.tan(fov_x / 2)
    return [sx, 0, 0, 0,
            0, sx * aspect, 0, 0,
            -2 * shift[0], -2 * shift[1], -1.001, -1,
            0, 0, -.2, 0]


def orthographic(width, aspect):
    return [2 / width, 0, 0, 0, 0, 2 / width * aspect, 0, 0, 0, 0, -.001, 0, 0, 0, -1, 1]


def project(p, x, y, z):
    clip = [x * p[0] + y * p[4] + z * p[8] + p[12], x * p[1] + y * p[5] + z * p[9] + p[13]]
    w = x * p[3] + y * p[7] + z * p[11] + p[15]
    return [.5 + .5 * clip[0] / w, .5 + .5 * clip[1] / w]


class PresentationUvTest(unittest.TestCase):
    def assertMapsPoint(self, frame, current, point):
        sx, sy, ox, oy = presentation_uv({'viewport': {'projection': frame}}, current)
        u, v = project(current, *point)
        expected = project(frame, *point)
        self.assertAlmostEqual(u * sx + ox, expected[0], places=5)
        self.assertAlmostEqual(v * sy + oy, expected[1], places=5)

    def test_same_projection_is_identity(self):
        p = perspective(.8, 1.6)
        self.assertEqual(presentation_uv({'viewport': {'projection': p}}, list(p)), IDENTITY_UV)

    def test_wider_panel_keeps_proportions(self):
        # Tall split pane rendered, then maximized to a wide panel.
        frame, current = perspective(.8, .5), perspective(.8, 2.87)
        for point in ((1, 2, -10), (-3, .5, -7), (0, 0, -4)):
            self.assertMapsPoint(frame, current, point)
        sx, sy, _, _ = presentation_uv({'viewport': {'projection': frame}}, current)
        self.assertAlmostEqual(sx, 1)
        self.assertLess(sy, 1)

    def test_camera_shift_and_orthographic(self):
        self.assertMapsPoint(perspective(.6, 1.2, (.1, -.05)), perspective(.6, 2.0, (.1, -.05)), (2, -1, -9))
        self.assertMapsPoint(orthographic(20, .7), orthographic(20, 1.9), (3, 4, -5))

    def test_missing_or_mismatched_projection_is_identity(self):
        self.assertEqual(presentation_uv({}, perspective(.8, 1)), IDENTITY_UV)
        self.assertEqual(presentation_uv({'viewport': {'projection': perspective(.8, 1)}}, None), IDENTITY_UV)
        self.assertEqual(presentation_uv({'viewport': {'projection': perspective(.8, 1)}}, orthographic(10, 1)), IDENTITY_UV)


if __name__ == '__main__':
    unittest.main()

from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from eevee_maya import graphics


class GraphicsPreference(unittest.TestCase):
    def test_only_explicit_call_changes_next_start_preference(self):
        cmds = mock.Mock(spec=['optionVar', 'savePrefs'])
        message = graphics.configure_opengl(cmds)
        cmds.optionVar.assert_called_once_with(stringValue=('vp2RenderingEngine', 'OpenGLCoreProfile'))
        cmds.savePrefs.assert_called_once_with(general=True)
        self.assertIn('reinicia Maya', message)

    def test_preference_write_failure_is_not_reported_as_success(self):
        cmds = mock.Mock(spec=['optionVar', 'savePrefs'])
        cmds.optionVar.side_effect = RuntimeError('preferences unavailable')
        with self.assertRaises(RuntimeError):
            graphics.configure_opengl(cmds)
        cmds.savePrefs.assert_not_called()

    def test_device_override_is_explained_without_mutating_environment(self):
        cmds = mock.Mock(spec=['optionVar', 'savePrefs'])
        with mock.patch.dict('os.environ', {'MAYA_VP2_DEVICE_OVERRIDE': 'VirtualDeviceDx11'}):
            message = graphics.configure_opengl(cmds)
            self.assertIn('MAYA_VP2_DEVICE_OVERRIDE', message)
            self.assertIn('retira esa variable', message)


if __name__ == '__main__':
    unittest.main()

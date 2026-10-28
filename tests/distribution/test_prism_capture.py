from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from eevee_maya.prism_capture import validate_frames, bind, unbind


class PrismFrameValidation(unittest.TestCase):
    def test_complete_capture_is_accepted(self):
        validate_frames([{'maya_frame':f} for f in (101,102,103)],(101,103))

    def test_empty_partial_and_repeated_frames_cannot_publish(self):
        for frames in ([],[101,103],[101,102,102],[101,102,103,103]):
            with self.subTest(frames=frames),self.assertRaisesRegex(RuntimeError,'todos los fotogramas'):
                validate_frames([{'maya_frame':f} for f in frames],(101,103))

    def test_draw_failure_rejects_even_a_complete_pose_trace(self):
        with self.assertRaisesRegex(RuntimeError,'GPU'):
            validate_frames([{'maya_frame':1}],(1,1),'Error GPU')


class PrismBinding(unittest.TestCase):
    def tearDown(self):
        unbind()

    def test_repeat_install_and_unload_restore_prism(self):
        original=lambda *args:None
        plugin=SimpleNamespace(sm_playblast_createPlayblast=original)
        core=SimpleNamespace(appPlugin=plugin)
        self.assertTrue(bind(core));wrapper=plugin.sm_playblast_createPlayblast
        self.assertIsNot(wrapper,original)
        self.assertTrue(bind(core));self.assertIs(plugin.sm_playblast_createPlayblast,wrapper)
        unbind();self.assertIs(plugin.sm_playblast_createPlayblast,original)

    def test_unload_preserves_a_later_third_party_wrapper(self):
        plugin=SimpleNamespace(sm_playblast_createPlayblast=lambda *args:None)
        bind(SimpleNamespace(appPlugin=plugin))
        replacement=lambda *args:None
        plugin.sm_playblast_createPlayblast=replacement
        unbind();self.assertIs(plugin.sm_playblast_createPlayblast,replacement)

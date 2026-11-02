from pathlib import Path
import sys, unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from eevee_maya.startup import label, hud_text, LABELS


class StartupMilestones(unittest.TestCase):
    def test_real_material_counts_are_shown_without_time_estimates(self):
        text=label({'stage':'materials','completed':12,'total':45})
        self.assertIn('12 de 45',text)
        self.assertNotIn('%',text)

    def test_shader_compilation_has_no_fake_progress_count(self):
        self.assertNotIn('/',label({'stage':'shaders'}))

    def test_viewport_text_is_plain_ascii_and_readable(self):
        # Maya's HUD font drops accents and the middle dot; keep words intact.
        self.assertEqual(hud_text('Preparando geometría · 3 / 9'),'Preparando geometria - 3 / 9')
        self.assertEqual(hud_text('Maya está usando DirectX 11.'),'Maya esta usando DirectX 11.')
        for stage in LABELS:
            text=hud_text(label({'stage':stage,'completed':1,'total':2}))
            self.assertTrue(text.isascii());self.assertNotIn('?',text)

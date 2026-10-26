from pathlib import Path
import sys, unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from eevee_maya.startup import label


class StartupMilestones(unittest.TestCase):
    def test_real_material_counts_are_shown_without_time_estimates(self):
        text=label({'stage':'materials','completed':12,'total':45})
        self.assertIn('12 / 45',text)
        self.assertNotIn('%',text)

    def test_shader_compilation_has_no_fake_progress_count(self):
        self.assertNotIn('/',label({'stage':'shaders'}))

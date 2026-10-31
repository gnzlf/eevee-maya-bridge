import copy,math,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from eevee_maya.light_photometry import energy,volume_compensation,receiver_reference

class Photometry(unittest.TestCase):
 def spec(self,kind='pointLight',**kwargs):
  return dict(dict(kind=kind,intensity=1,exposure=0,decay=0,decay_reference=5,
   intensity_mode='viewport2',viewport_reference=10,receiver_gain=math.pi),**kwargs)
 def test_point_no_decay_and_quadratic_match_at_receiver(self):
  self.assertAlmostEqual(energy(self.spec()),400*math.pi**2)
  self.assertAlmostEqual(energy(self.spec(decay=2)),4*math.pi**2)
 def test_standard_and_classic_follow_different_vp2_conventions(self):
  self.assertAlmostEqual(energy(self.spec('directionalLight')),math.pi)
  self.assertAlmostEqual(energy(self.spec('directionalLight',receiver_gain=1)),1)
  self.assertAlmostEqual(energy(self.spec('areaLight')),math.pi**2)
  self.assertAlmostEqual(energy(self.spec('aiAreaLight',decay=2)),math.pi**2)
 def test_area_extra_decay_normalization_and_legacy_switch(self):
  self.assertAlmostEqual(energy(self.spec('areaLight',decay=1)),math.pi**2/10)
  self.assertAlmostEqual(energy(self.spec('areaLight',normalize=False,size_x=6,size_y=4)),math.pi**2*24)
  self.assertAlmostEqual(energy(self.spec(intensity_mode='legacy')),100*math.pi)
 def test_volume_preserves_previous_light_power_without_mutating_source(self):
  for kind in ('pointLight','spotLight','directionalLight','areaLight','ambientLight'):
   source=self.spec(kind);before=copy.deepcopy(source)
   self.assertAlmostEqual(energy(source)*volume_compensation(source),energy(source,legacy=True))
   self.assertEqual(source,before)
  self.assertEqual(volume_compensation(self.spec(intensity=0)),1)
 def test_reference_follows_surface_distance_and_beam_direction(self):
  bounds=[([-2,-2,0],[2,2,0]),([-2,-2,8],[2,2,8])]
  self.assertEqual(receiver_reference((0,0,5),bounds,direction=(0,0,-1)),(0,5))
  self.assertEqual(receiver_reference((0,0,5),bounds,direction=(0,0,1)),(1,3))
  self.assertEqual(receiver_reference((0,0,10),bounds[:1]),(0,10))
 def test_empty_or_enclosing_receivers_do_not_create_zero_distance_energy(self):
  self.assertEqual(receiver_reference((0,0,0),[]),(None,5))
  self.assertEqual(receiver_reference((0,0,0),[([-1,-1,-1],[1,1,1])]),(None,5))

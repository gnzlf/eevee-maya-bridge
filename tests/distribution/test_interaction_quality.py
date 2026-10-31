import struct,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from eevee_maya.quality import InteractionQuality

class GeometryInteraction(unittest.TestCase):
 def snapshot(self,changed=False):
  return {'camera':{'matrix':[1]*16},'lights':[],'native':{'aa_samples':8},'maya_frame':1,
          'width':1920,'height':1080,'samples':8,'mesh_delta':struct.pack('<I',int(changed))}
 def test_object_drag_stays_interactive_and_recovers_full_hd(self):
  quality=InteractionQuality();config={'adaptive_quality':True,'interaction_width':960}
  quality.apply(self.snapshot(),config,now=0)
  idle=quality.apply(self.snapshot(),config,now=1);self.assertEqual(idle['width'],1920)
  for now in (2,2.6,3.2):
   frame=quality.apply(self.snapshot(True),config,now=now)
   self.assertEqual((frame['width'],frame['height'],frame['samples']),(960,540,8))
   self.assertFalse(frame['navigating'])
  idle=quality.apply(self.snapshot(),config,now=4)
  self.assertEqual((idle['width'],idle['height']),(1920,1080));self.assertFalse(idle['interactive'])
 def test_strict_resolution_and_non_geometric_requests_keep_their_contract(self):
  quality=InteractionQuality()
  frame=quality.apply(self.snapshot(True),{'adaptive_quality':False},now=1)
  self.assertEqual((frame['width'],frame['height'],frame['samples']),(1920,1080,8))
  frame=quality.apply(self.snapshot(),{'adaptive_quality':True},now=2)
  self.assertEqual(frame['width'],1920)
 def test_legacy_full_snapshots_do_not_keep_idle_in_preview_forever(self):
  quality=InteractionQuality();config={'adaptive_quality':True}
  first=self.snapshot();first.pop('mesh_delta');first['meshes']=[{'matrix':[1]*16}]
  quality.apply(dict(first),config,now=0)
  frame=quality.apply(dict(first),config,now=1)
  self.assertEqual(frame['width'],1920);self.assertFalse(frame['interactive'])

import math
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
from eevee_maya.lighting import expand_spot_profiles
from eevee_maya.quality import InteractionQuality


class SpotProfiles(unittest.TestCase):
    def test_extreme_dropoff_stays_in_a_narrow_cone(self):
        source={'name':'Spot','kind':'spotLight','dropoff':20000,'cone_angle':math.radians(86),
                'penumbra':0,'intensity':3}
        profiles=expand_spot_profiles([source])
        self.assertAlmostEqual(sum(p['intensity'] for p in profiles),3)
        self.assertTrue(all(p['intensity']>=0 for p in profiles))
        self.assertTrue(all(math.isfinite(p['cone_angle']) for p in profiles))
        self.assertLess(max(p['cone_angle'] for p in profiles[1:]),math.radians(3))
        self.assertEqual(source['dropoff'],20000)

    def test_low_dropoff_keeps_energy_and_native_cone(self):
        source={'name':'Spot','kind':'spotLight','dropoff':4,'cone_angle':1,'penumbra':-.1,'intensity':2}
        profiles=expand_spot_profiles([source])
        self.assertEqual(profiles[0]['cone_angle'],1)
        self.assertAlmostEqual(sum(p['intensity'] for p in profiles),2)
        self.assertTrue(all(p['cone_angle']<=.8 for p in profiles[1:]))


class AdaptiveQuality(unittest.TestCase):
    def data(self):
        return {'camera':{'focus_distance':20},'lights':[{'intensity':1}], 'effects':{'fog':True},
                'native':{'aa_samples':16},'width':1920,'height':1080,'samples':16}
    def test_edits_use_preview_then_idle_restores_full_quality(self):
        quality=InteractionQuality();config={'adaptive_quality':True}
        preview=quality.apply(self.data(),config,now=0)
        self.assertEqual((preview['width'],preview['height'],preview['samples']),(960,540,2))
        full=quality.apply(self.data(),config,now=.5)
        self.assertEqual((full['width'],full['height'],full['samples']),(1920,1080,16))
        changed=self.data();changed['lights'][0]['intensity']=2
        self.assertTrue(quality.apply(changed,config,now=.6)['interactive'])
    def test_adaptive_can_be_disabled(self):
        data=InteractionQuality().apply(self.data(),{'adaptive_quality':False},playing=True,now=0)
        self.assertEqual((data['width'],data['height'],data['samples']),(1920,1080,16))
    def test_timeline_scrubbing_uses_preview(self):
        quality=InteractionQuality();initial=self.data();initial['maya_frame']=1
        quality.apply(initial,{},now=0)
        settled=self.data();settled['maya_frame']=1
        self.assertFalse(quality.apply(settled,{},now=1)['interactive'])
        scrub=self.data();scrub['maya_frame']=2
        self.assertTrue(quality.apply(scrub,{},now=1.01)['interactive'])

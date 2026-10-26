import math
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
from eevee_maya.lighting import expand_spot_profiles
from eevee_maya.quality import InteractionQuality
from eevee_maya import shadow_quality


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
    def test_full_shadow_quality_survives_adaptive_preview(self):
        snapshot=self.data();snapshot['shadow_settings']=shadow_quality.resolve({'shadow_quality':'ultra'})
        result=InteractionQuality().apply(snapshot,{},playing=True,now=0)
        self.assertEqual(result['width'],960)
        self.assertEqual(result['shadow_settings']['resolution'],1)
        self.assertEqual(result['shadow_settings']['rays'],4)

    def test_invalid_persisted_shadow_preferences_fall_back(self):
        settings=shadow_quality.resolve({'shadow_quality':'obsolete','shadow_pool_size':'99999'})
        self.assertEqual(settings,shadow_quality.resolve({}))
    def data(self):
        return {'camera':{'focus_distance':20},'lights':[{'intensity':1}], 'effects':{'fog':True},
                'native':{'aa_samples':16},'width':1920,'height':1080,'samples':16}
    def test_edits_use_preview_then_idle_restores_full_quality(self):
        quality=InteractionQuality();config={'adaptive_quality':True}
        preview=quality.apply(self.data(),config,now=0)
        self.assertEqual((preview['width'],preview['height'],preview['samples']),(960,540,16))
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
    def test_playback_keeps_native_samples_including_aa_off(self):
        for samples in (1,2,8,16,32,64):
            snapshot=self.data();snapshot['samples']=samples
            self.assertEqual(InteractionQuality().apply(snapshot,{},playing=True,now=0)['samples'],samples)
    def test_camera_navigation_restores_resolution_and_preserves_aa(self):
        quality=InteractionQuality();a=self.data();a['camera']['matrix']=[0]
        quality.apply(a,{},now=0)
        b=self.data();b['camera']['matrix']=[1]
        moved=quality.apply(b,{},now=1)
        self.assertEqual((moved['width'],moved['height'],moved['samples']),(640,360,16))
        self.assertTrue(moved['navigating'])
        c=self.data();c['camera']['matrix']=[1]
        idle=quality.apply(c,{},now=1.5)
        self.assertEqual((idle['width'],idle['height']),(1920,1080))
        self.assertFalse(idle['navigating'])
    def test_animated_camera_does_not_trigger_fast_navigation(self):
        quality=InteractionQuality();a=self.data();a['camera']['matrix']=[0]
        quality.apply(a,{},now=0)
        b=self.data();b['camera']['matrix']=[1]
        played=quality.apply(b,{},playing=True,now=1)
        self.assertEqual(played['width'],960)
        self.assertFalse(played['navigating'])
    def test_focus_change_is_not_navigation_and_fast_mode_can_be_disabled(self):
        quality=InteractionQuality();quality.apply(self.data(),{},now=0)
        a=self.data();a['camera']['focus_distance']=100
        self.assertFalse(quality.apply(a,{},now=1)['navigating'])
        b=self.data();b['camera']['matrix']=[1]
        disabled=quality.apply(b,{'fast_navigation':False},now=2)
        self.assertEqual(disabled['width'],960)
        self.assertFalse(disabled['navigating'])
    def test_scrubbing_animated_camera_keeps_animation_resolution(self):
        quality=InteractionQuality();a=self.data();a['camera']['matrix']=[0];a['maya_frame']=1
        quality.apply(a,{},now=0)
        b=self.data();b['camera']['matrix']=[1];b['maya_frame']=2
        scrub=quality.apply(b,{},now=1)
        self.assertEqual(scrub['width'],960)
        self.assertFalse(scrub['navigating'])
    def test_configured_navigation_width_is_used(self):
        quality=InteractionQuality();a=self.data();a['camera']['matrix']=[0]
        quality.apply(a,{},now=0)
        b=self.data();b['camera']['matrix']=[1]
        moved=quality.apply(b,{'navigation_width':1280},now=1)
        self.assertEqual(moved['width'],1280)

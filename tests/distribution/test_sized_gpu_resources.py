import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from eevee_maya.gpu_lifetime import RetiredGpuPools,SizedGpuResources

class Resource:
 def __init__(self):self.closed=0;self.freed=0
 def close(self):self.closed+=1
 def free(self):self.freed+=1

def resources(token):return {'pool':[Resource() for _ in range(3)],'frames':[token]*3,'offscreen':Resource(),'depth_offscreen':Resource()}

class SizedCache(unittest.TestCase):
 def test_960_full_hd_960_reuses_handles_and_frame_ownership(self):
  retired=RetiredGpuPools();cache=SizedGpuResources(retired,2)
  small=cache.acquire((960,540),lambda:resources(5));full=cache.acquire((1920,1080),lambda:resources(9))
  reused=cache.acquire((960,540),lambda:self.fail('allocated an existing size'),released_frame=5)
  self.assertIs(reused,small);self.assertEqual(reused['frames'],[5]*3)
  self.assertEqual((cache.allocations,cache.reuses),(2,1));self.assertEqual(retired.pending,[])
  cache.close();self.assertTrue(all(r.closed==1 for r in small['pool']+full['pool']))
  self.assertEqual(small['offscreen'].freed,1)
 def test_eviction_preserves_unacknowledged_handles_and_bounds_cache(self):
  retired=RetiredGpuPools();cache=SizedGpuResources(retired,2)
  old=cache.acquire((320,180),lambda:resources(12))
  cache.acquire((960,540),lambda:resources(15));cache.acquire((1920,1080),lambda:resources(18))
  self.assertEqual(len(cache.entries),2);self.assertEqual(old['offscreen'].freed,1)
  retired.collect(11);self.assertTrue(all(r.closed==0 for r in old['pool']))
  retired.collect(12);self.assertTrue(all(r.closed==1 for r in old['pool']))
  cache.close();retired.close();self.assertTrue(all(r.closed==1 for r in old['pool']))
 def test_revisiting_a_size_before_import_keeps_old_frame_and_never_waits(self):
  retired=RetiredGpuPools();cache=SizedGpuResources(retired,3)
  old=cache.acquire((960,540),lambda:resources(7))
  cache.acquire((1920,1080),lambda:resources(8))
  fresh=cache.acquire((960,540),lambda:resources(9),released_frame=6)
  self.assertIsNot(old,fresh);self.assertEqual((cache.allocations,cache.reuses),(3,0))
  retired.collect(6);self.assertTrue(all(r.closed==0 for r in old['pool']))
  retired.collect(7);self.assertTrue(all(r.closed==1 for r in old['pool']))
  cache.close();retired.close()
 def test_failed_replacement_preserves_old_framebuffer_and_handles(self):
  retired=RetiredGpuPools();cache=SizedGpuResources(retired,3)
  old=cache.acquire((960,540),lambda:resources(7))
  def failed():raise RuntimeError('Simulated allocation failure')
  with self.assertRaises(RuntimeError):cache.acquire((960,540),failed,released_frame=6)
  self.assertIs(cache.entries[(960,540)],old)
  self.assertEqual(old['offscreen'].freed,0);self.assertEqual(retired.pending,[])
  self.assertTrue(all(r.closed==0 for r in old['pool']));cache.close()

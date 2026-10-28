from pathlib import Path
import sys,unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from eevee_maya.gpu_lifetime import RetiredGpuPools


class Lifetime(unittest.TestCase):
    def test_delayed_consumer_keeps_two_resized_generations_alive(self):
        retired=RetiredGpuPools();a,b=Mock(),Mock()
        retired.retire([a],7);retired.retire([b],9)
        retired.collect(6);a.close.assert_not_called();b.close.assert_not_called()
        retired.collect(7);a.close.assert_called_once();b.close.assert_not_called()
        retired.collect(8);a.close.assert_called_once();b.close.assert_not_called()
        retired.collect(9);b.close.assert_called_once();self.assertFalse(retired.pending)

    def test_shutdown_releases_pending_and_unpublished_resources(self):
        retired=RetiredGpuPools();a,b=Mock(),Mock()
        retired.retire([a],0);retired.retire([b],4)
        retired.collect(0);a.close.assert_called_once();b.close.assert_not_called()
        retired.close();retired.close();b.close.assert_called_once()

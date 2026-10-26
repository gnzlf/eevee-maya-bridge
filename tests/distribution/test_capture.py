from pathlib import Path
import sys
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
from eevee_maya import capture


class CaptureWait(unittest.TestCase):
    def engine(self):
        engine=mock.Mock();engine.process.poll.return_value=None;engine.last_response={}
        return engine
    def test_waits_for_delayed_exact_frame(self):
        engine=self.engine();engine.poll.side_effect=[False,False,True]
        predicate=mock.Mock(side_effect=[False,False,True]);accept=mock.Mock()
        with mock.patch.object(capture.time,'sleep'):
            capture.wait_until(engine,predicate,accept,1)
        self.assertEqual(engine.poll.call_count,3);accept.assert_called_once()
    def test_render_error_is_never_accepted(self):
        engine=self.engine();engine.last_response={'error':'render failed'}
        with self.assertRaisesRegex(RuntimeError,'render failed'):
            capture.wait_until(engine,lambda:True,mock.Mock(),1)
    def test_worker_exit_aborts_wait(self):
        engine=self.engine();engine.poll.return_value=False;engine.process.poll.return_value=1
        with self.assertRaisesRegex(RuntimeError,'Blender terminó'):
            capture.wait_until(engine,lambda:False,mock.Mock(),1)
    def test_timeout_is_bounded(self):
        engine=self.engine();engine.poll.return_value=False
        with mock.patch.object(capture.time,'monotonic',side_effect=[0,2]):
            with self.assertRaises(TimeoutError):capture.wait_until(engine,lambda:False,mock.Mock(),1)

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from eevee_maya.diagnostics import distribution, performance_report
from eevee_maya.engine import Engine


class PerformanceReports(unittest.TestCase):
    def request(self, token, timestamp, **values):
        return dict(id=token, submitted_at=timestamp, width=1920, height=1080,
                    samples=8, mode='full_quality', **values)

    def test_counts_new_images_and_ignores_repeated_draws(self):
        requests = [self.request(1, 9), self.request(2, 9.02)]
        draws = [(9.1, 1, 1), (9.11, 1, 1), (9.2, 2, 2), (9.21, 2, 2)]
        report = performance_report(requests, [], draws, now=10)
        self.assertEqual(report['presented_unique_frames'], 2)
        self.assertAlmostEqual(report['new_gpu_frames_per_second_in_sample'], 10)
        self.assertAlmostEqual(report['last_new_frame_age_seconds'], .8)
        self.assertEqual(report['submit_to_draw_ms']['count'], 2)
        self.assertEqual(report['actual_resolutions'], {'1920 x 1080': 2})

    def test_unsubmitted_or_old_session_draws_and_future_times_are_ignored(self):
        requests = [self.request(1, 9)]
        draws = [(8.5, 1, 1), (9.2, 88, 1), (11, 1, 1), (9.5, 1, 1)]
        report = performance_report(requests, [], draws, now=10)
        self.assertEqual(report['presented_unique_frames'], 1)
        self.assertAlmostEqual(report['submit_to_draw_ms']['p50'], 500)
        self.assertIsNone(report['new_gpu_frames_per_second_in_sample'])

    def test_idle_window_does_not_invent_render_fps(self):
        report = performance_report([self.request(1, 0)], [], [(1, 1, 1)], now=30)
        self.assertEqual(report['presented_unique_frames'], 0)
        self.assertIsNone(report['new_gpu_frames_per_second_in_sample'])
        self.assertIsNone(report['submit_to_draw_ms']['p95'])
        self.assertIsNone(report['last_new_frame_age_seconds'])

    def test_redrawing_an_old_image_inside_the_window_is_not_a_new_frame(self):
        report = performance_report([self.request(1, 0)], [], [(1, 1, 1), (25, 1, 1)], now=30)
        self.assertEqual(report['presented_unique_frames'], 0)

    def test_actual_dimensions_quality_modes_and_stage_percentiles(self):
        requests = [self.request(1, 9), self.request(2, 9.1)]
        requests[1].update(mode='capture', samples=16, shadow_settings={'preset': 'ultra'})
        responses = [dict(id=1, width=640, height=360, received_at=9.08,
                          eevee_state={'samples': 8}, timings_ms={'color': 20, 'queue': -1}),
                     dict(id=2, width=1920, height=1080, received_at=9.18,
                          timings_ms={'color': 40, 'draw_color': 30, 'unknown': 20})]
        report = performance_report(requests, responses, [(9.1, 1, 1), (9.2, 2, 2)], now=10)
        self.assertTrue(report['mixed_modes_or_quality'])
        self.assertEqual(report['actual_resolutions'], {'640 x 360': 1, '1920 x 1080': 1})
        self.assertEqual(report['modes'], {'full_quality': 1, 'capture': 1})
        self.assertEqual(report['worker_stages_ms']['color']['p95'], 39)
        self.assertEqual(report['worker_stages_ms']['queue']['count'], 0)
        self.assertAlmostEqual(report['submit_to_receive_ms']['p50'], 80)

    def test_shadow_quality_change_is_identified_even_at_same_resolution(self):
        requests = [self.request(1, 9), self.request(2, 9.1)]
        requests[1]['shadow_settings'] = {'preset': 'ultra'}
        report = performance_report(requests, [], [(9.1, 1, 1), (9.2, 2, 1)], now=10)
        self.assertTrue(report['mixed_modes_or_quality'])

    def test_payload_names_and_paths_are_not_exported(self):
        request = self.request(1, 9, private_scene='CLIENT_SECRET', camera={'name': 'CLIENT_SECRET'})
        response = {'id': 1, 'error_detail': 'CLIENT_SECRET',
                    'eevee_state': {'transmission_preview_materials': ['CLIENT_SECRET']}}
        report = performance_report([request], [response], [(9.1, 1, 1)], now=10)
        self.assertNotIn('CLIENT_SECRET', json.dumps(report, allow_nan=False))

    def test_nonfinite_or_negative_timing_values_are_excluded(self):
        self.assertEqual(distribution([None, float('nan'), float('inf'), -1, True, 10])['mean'], 10)
        for window in (0, -1, float('inf'), float('nan')):
            with self.assertRaises(ValueError):
                performance_report([], [], [], now=10, window_seconds=window)


class SubmissionTracing(unittest.TestCase):
    def engine(self):
        with mock.patch('eevee_maya.engine.settings', return_value={}):
            engine = Engine()
        engine.request_mailbox = mock.Mock()
        return engine

    def test_skipped_signature_does_not_count_as_a_new_submission(self):
        engine = self.engine()
        snapshot = {'width': 1920, 'height': 1080, 'samples': 8, 'maya_frame': 1}
        before = deepcopy(snapshot)
        self.assertTrue(engine.submit(snapshot))
        self.assertFalse(engine.submit(snapshot))
        self.assertEqual(len(engine.request_history), 1)
        self.assertEqual(snapshot, before)
        self.assertEqual(engine.request_history[0]['width'], 1920)

    def test_capture_is_explicit_and_never_sent_as_a_render_setting(self):
        engine = self.engine()
        self.assertTrue(engine.submit({'width': 1920}, force=True, capture=True))
        self.assertEqual(engine.request_history[-1]['mode'], 'capture')
        self.assertNotIn('capture', engine.request_mailbox.write.call_args.args[1])

    def test_failure_to_write_is_not_recorded_as_success(self):
        engine = self.engine()
        engine.request_mailbox.write.side_effect = OSError('mailbox unavailable')
        with self.assertRaises(OSError):
            engine.submit({'width': 1920})
        self.assertEqual(len(engine.request_history), 0)

    def test_history_is_bounded_and_does_not_keep_geometry(self):
        engine = self.engine()
        for index in range(4100):
            engine.submit({'width': 640, 'maya_frame': index, 'meshes': ['CLIENT_SECRET']}, force=True)
        self.assertEqual(len(engine.request_history), 4096)
        self.assertNotIn('CLIENT_SECRET', json.dumps(list(engine.request_history)))


if __name__ == '__main__':
    unittest.main()

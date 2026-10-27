import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))


def load_with_commands(commands):
    maya = types.ModuleType('maya')
    maya.cmds = commands
    spec = importlib.util.spec_from_file_location('eevee_maya.diagnostics_ui',
        ROOT / 'scripts/eevee_maya/diagnostics_ui.py')
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {'maya': maya, 'maya.cmds': commands}):
        spec.loader.exec_module(module)
    return module


class DiagnosticsBoundaries(unittest.TestCase):
    def commands(self):
        commands = mock.Mock(spec=['about', 'fileDialog2', 'warning'])
        commands.about.return_value = '2024'
        return commands

    def test_export_cancellation_never_writes_a_file(self):
        commands = self.commands()
        commands.fileDialog2.return_value = None
        module = load_with_commands(commands)
        with mock.patch.object(module, 'write_json') as write:
            self.assertIsNone(module._save({}, 'test', 'report.json'))
        write.assert_not_called()

    def test_disk_error_is_reported_without_touching_renderer(self):
        commands = self.commands()
        commands.fileDialog2.return_value = ['report.json']
        module = load_with_commands(commands)
        with mock.patch.object(module, 'write_json', side_effect=PermissionError('read only')):
            self.assertIsNone(module._save({}, 'test', 'report.json'))
        commands.warning.assert_called_once()

    def test_collection_does_not_start_renderer_or_query_scene(self):
        commands = self.commands()
        module = load_with_commands(commands)
        engine = types.SimpleNamespace(request_history=[], history=[], gpu=True,
            last_response={'meshes': 12, 'private_scene': 'PRIVATE'},
            start=mock.Mock(), config={'blender': 'PRIVATE'})
        controller = types.SimpleNamespace(engine=engine, timings={'export_ms': 2, 'private_name': 'PRIVATE'})
        report = module.collect_performance(controller, None)
        engine.start.assert_not_called()
        self.assertEqual(report['presented_unique_frames'], 0)
        self.assertEqual(report['latest_scene_counts'], {'meshes': 12})
        self.assertEqual(report['latest_main_thread_ms'], {'export_ms': 2})
        self.assertNotIn('PRIVATE', str(report))
        self.assertEqual(commands.method_calls, [mock.call.about(version=True)])

    def test_cpu_route_never_uses_previous_gpu_presentations(self):
        module = load_with_commands(self.commands())
        engine = types.SimpleNamespace(request_history=[], history=[], gpu=False, last_response={})
        controller = types.SimpleNamespace(engine=engine, timings={})
        override = types.SimpleNamespace(gpu_image=types.SimpleNamespace(presentations=[(1, 1, 1)]))
        with mock.patch.object(module.diagnostics, 'performance_report', return_value={'notes': []}) as build:
            module.collect_performance(controller, override)
        self.assertEqual(build.call_args.args[2], [])


if __name__ == '__main__':
    unittest.main()

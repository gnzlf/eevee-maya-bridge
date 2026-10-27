"""Reproduce failed VP2 registration/unload without needing a graphics device."""
from contextlib import contextmanager
from pathlib import Path
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


class RenderBase:
    def __init__(self, *args):
        pass


@contextmanager
def environment():
    maya = types.ModuleType('maya'); maya.__path__ = []
    api = types.ModuleType('maya.api'); api.__path__ = []
    om = types.ModuleType('maya.api.OpenMaya')
    om.MPxCommand = object
    om.MFnPlugin = mock.Mock()
    om.MGlobal = mock.Mock()
    cmds = types.ModuleType('maya.cmds')
    cmds.about = mock.Mock(return_value=False)
    cmds.evalDeferred = mock.Mock()
    render = types.ModuleType('maya.api.OpenMayaRender')
    for name in ('MUserRenderOperation', 'MQuadRender', 'MSceneRender', 'MHUDRender', 'MRenderOverride', 'MPresentTarget'):
        setattr(render, name, RenderBase)
    render.MRenderer = mock.Mock()
    render.MRenderer.findRenderOverride.return_value = None
    render.MRenderer.kDirectX11 = 2
    render.MRenderer.kOpenGL = 1
    render.MRenderer.kOpenGLCoreProfile = 4
    render.MRenderer.drawAPI.return_value = 4
    package = types.ModuleType('eevee_maya'); package.__path__ = []; package.__version__ = '0.6.3'
    ui = types.ModuleType('eevee_maya.ui')
    ui.stop = mock.Mock(); ui.remove_menu = mock.Mock(); ui.install_menu = mock.Mock()
    ui.QtCore = mock.Mock()
    maya.api = api; maya.cmds = cmds; api.OpenMaya = om; api.OpenMayaRender = render
    modules = {'maya': maya, 'maya.api': api, 'maya.api.OpenMaya': om,
               'maya.api.OpenMayaRender': render, 'maya.cmds': cmds,
               'eevee_maya': package, 'eevee_maya.ui': ui}
    def load(path):
        module = types.ModuleType('lifecycle_fixture'); module.__file__ = str(ROOT / path)
        if path.startswith('scripts/eevee_maya/'):
            module.__package__ = 'eevee_maya'
        exec(compile((ROOT / path).read_text(encoding='utf-8'), module.__file__, 'exec'), module.__dict__)
        return module
    with mock.patch.dict(sys.modules, modules):
        viewport = load('scripts/eevee_maya/viewport.py')
        package.viewport = viewport; package.ui = ui
        with mock.patch.dict(sys.modules, {'eevee_maya.viewport': viewport}):
            entry = load('plug-ins/eeveeBridge.py')
            entry.diagnostic_writer = entry._write_diagnostic
            with mock.patch.object(entry, '_write_diagnostic', return_value='test-log.json') as log:
                yield entry, viewport, render.MRenderer, om.MFnPlugin.return_value, cmds, ui, log


class Lifecycle(unittest.TestCase):
    def test_failed_registration_can_be_retried(self):
        with environment() as (_, viewport, renderer, *_):
            renderer.registerOverride.side_effect = [RuntimeError('(kFailure)'), None]
            with self.assertRaisesRegex(RuntimeError, 'OpenGL Core Profile'):
                viewport.register()
            self.assertIsNone(viewport._override)
            self.assertIsNotNone(viewport.register())
            self.assertEqual(renderer.registerOverride.call_count, 2)

    def test_unload_after_maya_already_removed_override(self):
        with environment() as (_, viewport, renderer, *_):
            candidate = mock.Mock(); viewport._override = candidate
            viewport.deregister(); viewport.deregister()
            renderer.deregisterOverride.assert_not_called()
            candidate.quad.release.assert_called_once()
            candidate.gpu_image.release.assert_called_once()
            self.assertIsNone(viewport._override)

    def test_registered_override_is_removed_once(self):
        with environment() as (_, viewport, renderer, *_):
            candidate = mock.Mock(); viewport._override = candidate
            renderer.findRenderOverride.return_value = candidate
            viewport.deregister(); viewport.deregister()
            renderer.deregisterOverride.assert_called_once_with(candidate)

    def test_conflicting_instance_is_not_removed(self):
        with environment() as (_, viewport, renderer, *_):
            renderer.findRenderOverride.return_value = mock.Mock()
            with self.assertRaisesRegex(RuntimeError, 'otra instancia'):
                viewport.register()
            renderer.deregisterOverride.assert_not_called()

    def test_load_does_not_require_ready_viewport(self):
        with environment() as (entry, viewport, renderer, plugin, cmds, ui, log):
            renderer.registerOverride.side_effect = RuntimeError('(kFailure)')
            entry.initializePlugin(object())
            plugin.registerCommand.assert_called_once()
            renderer.registerOverride.assert_not_called()
            cmds.evalDeferred.assert_called_once_with(entry._install_menu)
            entry._install_menu()
            ui.install_menu.assert_called_once()
            self.assertEqual(log.call_args.args[0]['stage'], 'renderer')
            self.assertIsNone(viewport._override)
            ui.QtCore.QTimer.singleShot.assert_called_once()

    def test_directx_registers_a_visible_compatibility_entry(self):
        with environment() as (entry, viewport, renderer, plugin, cmds, ui, log):
            renderer.drawAPI.return_value = renderer.kDirectX11
            entry.initializePlugin(object())
            entry._install_menu()
            renderer.registerOverride.assert_called_once()
            self.assertTrue(log.call_args.args[0]['opengl_restart_required'])
            self.assertEqual(viewport._override.supportedDrawAPIs(), 7)

    def test_directx_setup_cannot_reach_opengl_operations_or_attach(self):
        with environment() as (entry, viewport, renderer, plugin, cmds, ui, log):
            renderer.drawAPI.return_value = renderer.kDirectX11
            capture = types.ModuleType('eevee_maya.capture')
            capture.active = mock.Mock(return_value=False)
            with mock.patch.dict(sys.modules, {'eevee_maya.capture': capture}):
                override = viewport.Override()
                override.setup('modelPanel4')
                self.assertEqual(override.operations, [override.loading_background, override.graphics_notice, override.present])
                self.assertNotIn(override.gpu_image, override.operations)
                cmds.evalDeferred.assert_not_called()
                capture.active.return_value = True
                override.setup('modelPanel4')
                self.assertEqual(override.operations, [override.capture_failure, override.present])

    def test_batch_diagnostic_does_not_replace_gui_diagnostic(self):
        with environment() as (entry, viewport, renderer, plugin, cmds, ui, log):
            cmds.about.return_value = True
            with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {'LOCALAPPDATA': folder}):
                base = Path(folder) / 'EeveeMayaBridge/diagnostics'
                base.mkdir(parents=True)
                legacy = base / 'plugin_load.json'
                legacy.write_text('GUI sentinel', encoding='utf-8')
                target = Path(entry.diagnostic_writer({'ok': True}))
                self.assertEqual(legacy.read_text(encoding='utf-8'), 'GUI sentinel')
                self.assertEqual(target.name, 'plugin_load.%d.json' % os.getpid())
                self.assertTrue(json.loads(target.read_text(encoding='utf-8'))['batch'])

    def test_delayed_renderer_readiness_recovers_without_rebuilding_menu(self):
        with environment() as (entry, viewport, renderer, plugin, cmds, ui, log):
            renderer.registerOverride.side_effect = [RuntimeError('VP2 starting'), None]
            entry.initializePlugin(object()); entry._install_menu()
            callback = ui.QtCore.QTimer.singleShot.call_args.args[1]
            callback()
            self.assertEqual(renderer.registerOverride.call_count, 2)
            ui.install_menu.assert_called_once()
            self.assertTrue(log.call_args.args[0]['ok'])

    def test_registration_retry_stops_on_unload(self):
        with environment() as (entry, viewport, renderer, plugin, cmds, ui, log):
            renderer.registerOverride.side_effect = RuntimeError('VP2 starting')
            entry.initializePlugin(object()); entry._install_menu()
            callback = ui.QtCore.QTimer.singleShot.call_args.args[1]
            entry.uninitializePlugin(object()); callback()
            self.assertEqual(renderer.registerOverride.call_count, 1)

    def test_registration_retries_are_bounded(self):
        with environment() as (entry, viewport, renderer, plugin, cmds, ui, log):
            renderer.registerOverride.side_effect = RuntimeError('VP2 unavailable')
            entry.initializePlugin(object()); entry._install_menu()
            for _ in range(4):
                ui.QtCore.QTimer.singleShot.call_args.args[1]()
            self.assertEqual(renderer.registerOverride.call_count, 5)
            self.assertEqual(ui.QtCore.QTimer.singleShot.call_count, 4)
            om_error = log.call_args.args[0]
            self.assertEqual(om_error['attempt'], 5)

    def test_failed_load_rolls_back_owned_command(self):
        with environment() as (entry, viewport, renderer, plugin, cmds, ui, log):
            cmds.evalDeferred.side_effect = RuntimeError('idle unavailable')
            with self.assertRaisesRegex(RuntimeError, 'idle unavailable'):
                entry.initializePlugin(object())
            plugin.deregisterCommand.assert_called_once_with('eeveeViewport')
            self.assertFalse(entry._active)

    def test_failed_unload_still_removes_owned_command(self):
        with environment() as (entry, viewport, renderer, plugin, cmds, ui, log):
            with mock.patch.object(viewport, 'deregister', side_effect=RuntimeError('(kFailure)')):
                with self.assertRaisesRegex(RuntimeError, 'kFailure'):
                    entry.uninitializePlugin(object())
            plugin.deregisterCommand.assert_called_once_with('eeveeViewport')

    def test_failed_command_registration_does_not_remove_another_command(self):
        with environment() as (entry, viewport, renderer, plugin, cmds, ui, log):
            plugin.registerCommand.side_effect = RuntimeError('duplicate command')
            with self.assertRaisesRegex(RuntimeError, 'duplicate command'):
                entry.initializePlugin(object())
            plugin.deregisterCommand.assert_not_called()

    def test_unloaded_plugin_does_not_recreate_deferred_menu(self):
        with environment() as (entry, viewport, renderer, plugin, cmds, ui, log):
            entry.initializePlugin(object()); entry.uninitializePlugin(object())
            entry._install_menu()
            ui.install_menu.assert_not_called()

    def test_unwritable_diagnostic_folders_do_not_break_loading(self):
        with environment() as (entry, *_):
            with mock.patch.object(Path, 'mkdir', side_effect=PermissionError('read-only')):
                self.assertIn('Script Editor', entry.diagnostic_writer({'ok': True}))


if __name__ == '__main__':
    unittest.main()

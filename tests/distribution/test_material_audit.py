import json
from pathlib import Path
import sys
import unittest
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from eevee_maya.material_audit import audit, anonymized


class MaterialAudit(unittest.TestCase):
    def commands(self, kind='aiStandardSurface', pairs=None):
        # A restricted spec catches any attempt to mutate the scene.
        cmds = mock.Mock(spec=['ls', 'nodeType', 'listConnections', 'getAttr', 'workspace'])
        cmds.ls.return_value = ['Client:Skin']
        cmds.nodeType.side_effect = lambda node: kind if node == 'Client:Skin' else {
            'file1': 'file', 'remap1': 'remapValue', 'bump1': 'bump2d'}[node]
        cmds.listConnections.side_effect = lambda plug, **kw: (pairs or []) if plug == 'Client:Skin' else ['file1.outAlpha']
        cmds.getAttr.return_value = 'Client/private/missing.png'
        cmds.workspace.return_value = 'Z:/Client/private/missing.png'
        return cmds

    def test_unsupported_shader_is_reported_without_pretending_to_translate(self):
        report = audit(self.commands(kind='aiMixShader'))
        self.assertEqual(report['unsupported_count'], 1)
        self.assertEqual(report['materials'][0]['status'], 'unsupported')
        self.assertEqual(report['scope'], 'all_scene_materials_including_unused')
        self.assertNotIn('Client', json.dumps(report))

    def test_clean_known_shader_still_has_approximate_status(self):
        report = audit(self.commands(), nodes=['Client:Skin'])
        self.assertEqual(report['materials_with_issues'], 0)
        self.assertEqual(report['materials'][0]['status'], 'approximate')
        self.assertEqual(report['scope'], 'explicit_materials')

    def test_untranslated_network_and_missing_file_are_identified(self):
        cmds = self.commands(pairs=['Client:Skin.baseColor', 'remap1.outValue',
                                   'Client:Skin.specularColor', 'file1.outColor'])
        with mock.patch('eevee_maya.material_audit.os.path.isfile', return_value=False):
            report = audit(cmds)
        issues = report['materials'][0]['issues']
        self.assertEqual({issue['code'] for issue in issues}, {'untranslated_connection', 'texture_not_readable'})
        self.assertNotIn('Client', json.dumps(report))

    def test_supported_file_channels_and_bump_connections_are_recognized(self):
        cmds = self.commands(pairs=['Client:Skin.opacity', 'file1.outAlpha',
                                   'Client:Skin.normalCamera', 'bump1.outNormal'])
        with mock.patch('eevee_maya.material_audit.os.path.isfile', return_value=True):
            report = audit(cmds)
        issues = report['materials'][0]['issues']
        self.assertEqual(issues, [])

    def test_names_can_be_shown_locally_then_removed_for_export(self):
        report = audit(self.commands(), include_names=True)
        self.assertEqual(report['materials'][0]['name'], 'Client:Skin')
        self.assertNotIn('Client', json.dumps(anonymized(report)))
        self.assertIn('name', report['materials'][0])

    def test_existing_udim_token_source_is_readable(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'skin_1001.png').write_bytes(b'fixture')
            cmds=self.commands(pairs=['Client:Skin.baseColor','file1.outColor'])
            values={'file1.fileTextureName':str(root/'skin_<UDIM>.png'),
                    'file1.uvTilingMode':3,'file1.computedFileTextureNamePattern':''}
            cmds.getAttr.side_effect=lambda plug:values[plug]
            report=audit(cmds)
            self.assertEqual(report['materials_with_issues'],0)

    def test_read_error_is_reported_and_does_not_reveal_paths(self):
        cmds = self.commands()
        cmds.nodeType.side_effect = RuntimeError('Client/private/path')
        report = audit(cmds)
        self.assertEqual(report['unreadable_count'], 1)
        self.assertNotIn('Client', json.dumps(report))


if __name__ == '__main__':
    unittest.main()

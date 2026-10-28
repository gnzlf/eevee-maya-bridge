from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from eevee_maya.texture_paths import resolve


class TexturePaths(unittest.TestCase):
    def test_literal_token_reads_existing_tiles_and_ignores_other_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ('skin_1001.png','skin_1002.png','skin_1003.jpg','skin_1004.png.bak'):
                (root/name).write_bytes(b'fixture')
            result=resolve(str(root/'skin_<UDIM>.png'),True)
            self.assertEqual(result['tiles'],[1001,1002])
            self.assertEqual(Path(result['path']),root/'skin_1001.png')
            self.assertEqual(result['udim_pattern'],str(root/'skin_<UDIM>.png'))

    def test_concrete_tile_and_missing_first_tile_resolve_the_same_set(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'cloth_1002.exr').write_bytes(b'fixture')
            a=resolve(str(root/'cloth_1001.exr'),True)
            b=resolve(str(root/'cloth_<UDIM>.exr'),True)
            self.assertEqual(a,b);self.assertEqual(a['tiles'],[1002])

    def test_missing_udim_and_missing_single_image_remain_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(resolve(str(Path(folder)/'absent_<UDIM>.png'),True))
            self.assertIsNone(resolve(str(Path(folder)/'absent.png')))

    def test_existing_single_file_is_not_reinterpreted_as_tiles(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'image_1001.png';path.write_bytes(b'fixture')
            self.assertEqual(resolve(str(path)),{'path':str(path)})

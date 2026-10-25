import copy
import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import urllib.request

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
from eevee_maya import updates


class ReleaseUpdates(unittest.TestCase):
    def setUp(self):
        self.payload=b'installer payload for checksum validation'
        self.release={'tag_name':'v0.6.2','draft':False,'prerelease':False,'body':'New version',
            'assets':[{'name':'EeveeMayaBridge-0.6.2-maya2024-win64-Setup.exe',
            'url':'https://api.github.com/repos/gnzlf/eevee-maya-bridge/releases/assets/123',
            'digest':'sha256:'+hashlib.sha256(self.payload).hexdigest(),'size':len(self.payload)}]}
    def select(self):return updates.select_release(self.release,'0.6.1',repo='gnzlf/eevee-maya-bridge')
    def test_version_comparison_is_numeric(self):
        self.release['tag_name']='v0.10.0';self.release['assets'][0]['name']='EeveeMayaBridge-0.10.0-maya2024-win64-Setup.exe'
        self.assertEqual(self.select()['version'],'0.10.0')
    def test_current_or_older_does_not_offer_update(self):
        self.assertIsNone(updates.select_release(self.release,'0.6.2'))
        self.assertIsNone(updates.select_release(self.release,'1.0.0'))
    def test_draft_and_prerelease_are_skipped(self):
        for flag in ('draft','prerelease'):
            data=copy.deepcopy(self.release);data[flag]=True
            self.assertIsNone(updates.select_release(data,'0.6.1'))
    def test_incompatible_maya_has_no_installer(self):
        with self.assertRaisesRegex(ValueError,'Maya 2025'):updates.select_release(self.release,'0.6.1','2025')
    def test_missing_hash_is_rejected(self):
        self.release['assets'][0]['digest']=None
        with self.assertRaises(ValueError):self.select()
    def test_foreign_repository_and_http_are_rejected(self):
        for url in ('https://api.github.com/repos/other/repo/releases/assets/123','http://api.github.com/repos/gnzlf/eevee-maya-bridge/releases/assets/123'):
            self.release['assets'][0]['url']=url
            with self.assertRaises(ValueError):self.select()
    def test_verified_download_is_exact_and_reports_progress(self):
        progress=[]
        with tempfile.TemporaryDirectory() as folder,mock.patch.object(updates,'request',return_value=io.BytesIO(self.payload)):
            path=updates.download(self.select(),progress.append,folder)
            self.assertEqual(path.read_bytes(),self.payload);self.assertEqual(progress[-1],100)
            self.assertFalse(list(Path(folder).glob('*.part')))
    def test_corrupt_download_is_never_returned(self):
        with tempfile.TemporaryDirectory() as folder,mock.patch.object(updates,'request',return_value=io.BytesIO(b'x'*len(self.payload))):
            with self.assertRaisesRegex(ValueError,'SHA-256'):updates.download(self.select(),directory=folder)
            self.assertEqual(list(Path(folder).iterdir()),[])
    def test_oversized_download_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder,mock.patch.object(updates,'request',return_value=io.BytesIO(self.payload+b'x')):
            with self.assertRaisesRegex(ValueError,'Tamaño'):updates.download(self.select(),directory=folder)
    def test_redirect_does_not_forward_private_token(self):
        req=urllib.request.Request(self.release['assets'][0]['url'],headers={'Authorization':'Bearer example-test-token'})
        redirected=updates.SafeRedirect().redirect_request(req,None,302,'Found',{},'https://release-assets.githubusercontent.com/file')
        self.assertIsNone(redirected.get_header('Authorization'))
    def test_redirect_cannot_downgrade_https(self):
        req=urllib.request.Request(self.release['assets'][0]['url'])
        with self.assertRaises(ValueError):updates.SafeRedirect().redirect_request(req,None,302,'Found',{},'http://example.com/file')


if __name__=='__main__':unittest.main()

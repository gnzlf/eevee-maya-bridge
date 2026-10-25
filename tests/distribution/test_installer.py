"""Opt-in Windows integration: EEVEE_INSTALLER_BLENDER points to a Blender 5.2 executable."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[2]
BLENDER=os.environ.get('EEVEE_INSTALLER_BLENDER')


@unittest.skipUnless(os.name=='nt' and BLENDER,'Opt-in installer integration requires Blender 5.2')
class InstallerIntegration(unittest.TestCase):
    def run_install(self,archive,root,modules,expected=0):
        result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'packaging/InstallBridge.ps1'),
            '-PayloadPath',str(archive),'-InstallRoot',str(root),'-ModuleDirectory',str(modules),'-BlenderPath',BLENDER,'-NoRegistration'],capture_output=True,text=True,encoding='utf-8',errors='replace')
        if expected==0:self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        else:self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
        return result
    def test_upgrade_preserves_preferences_and_locked_version_and_rejects_corruption(self):
        archive=ROOT/'dist/EeveeMayaBridge-0.6.1-maya2024-win64.zip'
        with tempfile.TemporaryDirectory(prefix='Eevee installer test ') as temp:
            temp=Path(temp);root=temp/'Bridge With Spaces';modules=temp/'Maya Modules';modules.mkdir()
            module=modules/'EeveeMayaBridge.mod';original_module='+ EeveeMayaBridge 0.1 C:/PreviousBridge\n';module.write_text(original_module)
            self.run_install(archive,root,modules)
            self.assertEqual((root/'module-before-install.mod').read_text(),original_module)
            config=root/'config.json';prefs=json.loads(config.read_text(encoding='utf-8-sig'));prefs.update(max_width=1280,samples=8)
            config.write_text(json.dumps(prefs),encoding='utf-8')
            with zipfile.ZipFile(archive) as stream:files={name:stream.read(name) for name in stream.namelist()}
            manifest=json.loads(files['package.json']);manifest['version']='0.6.2'
            name='scripts/eevee_maya/__init__.py';files[name]=files[name].replace(b'0.6.1',b'0.6.2')
            manifest['files'][name]=hashlib.sha256(files[name]).hexdigest();files['package.json']=json.dumps(manifest).encode()
            upgrade=temp/'upgrade.zip'
            with zipfile.ZipFile(upgrade,'w') as stream:
                for name,data in files.items():stream.writestr(name,data)
            dll=root/'versions/0.6.1/bin/eevee_gpu_v5.dll';before=hashlib.sha256(dll.read_bytes()).hexdigest()
            locked=ctypes.WinDLL(str(dll))
            try:
                self.run_install(upgrade,root,modules)
                self.assertTrue((root/'versions/0.6.1').is_dir());self.assertTrue((root/'versions/0.6.2').is_dir())
                self.assertEqual(hashlib.sha256(dll.read_bytes()).hexdigest(),before)
                self.assertIn('0.6.2',module.read_text());self.assertEqual(json.loads(config.read_text(encoding='utf-8-sig'))['max_width'],1280)
                self.assertEqual(json.loads(config.read_text(encoding='utf-8-sig'))['samples'],8)
                active=module.read_bytes()
                corrupt=temp/'corrupt.zip';files['scripts/eevee_maya/__init__.py']+=b'\n# corrupt\n'
                with zipfile.ZipFile(corrupt,'w') as stream:
                    for name,data in files.items():stream.writestr(name,data)
                self.run_install(corrupt,root,modules,expected=1);self.assertEqual(module.read_bytes(),active)
                traversal=temp/'traversal.zip'
                with zipfile.ZipFile(traversal,'w') as stream:stream.writestr('../escape.txt',b'rejected')
                self.run_install(traversal,root,modules,expected=1);self.assertFalse((root/'escape.txt').exists());self.assertEqual(module.read_bytes(),active)
                self.assertFalse(list(root.glob('staging-*')))
            finally:
                free=ctypes.windll.kernel32.FreeLibrary;free.argtypes=[ctypes.c_void_p];free.restype=ctypes.c_bool;free(locked._handle)


if __name__=='__main__':unittest.main()

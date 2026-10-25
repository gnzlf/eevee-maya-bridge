"""Build a portable bridge ZIP and a self-contained Windows installer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def files(root=ROOT):
    for directory,pattern in (('scripts','*.py'),('blender','*.py'),('plug-ins','*.py'),('shaders','*')):
        yield from (p for p in (root/directory).rglob(pattern) if p.is_file() and '__pycache__' not in p.parts)
    for name in ('bin/eevee_gpu_v5.dll','bin/eevee_scene.dll','config.json','release-config.json','ABRIR_EN_MAYA.py',
                 'README.md','THIRD_PARTY_NOTICES.md','native/gpu_bridge.cpp','native/scene_stream.cpp','native/CMakeLists.txt'):
        yield root/name


def build(root=ROOT,output=None):
    output=Path(output) if output else root/'dist';output.mkdir(parents=True,exist_ok=True)
    version=re.search(r'__version__\s*=\s*"([0-9.]+)"',(root/'scripts/eevee_maya/__init__.py').read_text(encoding='utf-8')).group(1)
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('Version must be major.minor.patch')
    base='EeveeMayaBridge-'+version+'-maya2024-win64'
    archive=output/(base+'.zip')
    manifest={'version':version,'maya_version':'2024','platform':'win64','files':{}}
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as package:
        for path in sorted(files(root)):
            relative=path.relative_to(root).as_posix();data=path.read_bytes()
            manifest['files'][relative]=hashlib.sha256(data).hexdigest()
            package.writestr(relative,data)
        package.writestr('package.json',json.dumps(manifest,indent=2))
    compiler=Path(os.environ.get('WINDIR',r'C:\Windows'))/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    if not compiler.exists():raise RuntimeError('Windows con .NET Framework 4.x es necesario para compilar el instalador')
    executable=output/(base+'-Setup.exe')
    with tempfile.TemporaryDirectory(prefix='eevee-build-') as temp:
        script=Path(temp)/'InstallBridge.ps1'
        script.write_text((root/'packaging/InstallBridge.ps1').read_text(encoding='utf-8-sig'),encoding='utf-8-sig')
        subprocess.run([str(compiler),'/nologo','/target:winexe','/platform:x64','/optimize+','/codepage:65001',
                        '/reference:System.Windows.Forms.dll','/reference:System.Drawing.dll',
                        '/out:'+str(executable),'/resource:'+str(archive)+',payload.zip',
                        '/resource:'+str(script)+',InstallBridge.ps1',str(root/'packaging/Bootstrapper.cs')],check=True)
    hashes={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in (archive,executable)}
    checksum=output/'SHA256SUMS.txt';checksum.write_text(''.join(digest+'  '+name+'\n' for name,digest in hashes.items()),encoding='utf-8')
    print(json.dumps({'version':version,'zip':str(archive),'installer':str(executable),'sha256':hashes},indent=2))
    return archive,executable


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output');args=parser.parse_args();build(output=args.output)

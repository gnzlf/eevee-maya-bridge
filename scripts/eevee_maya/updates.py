"""GitHub release updates. Pure Python; no Maya calls on worker threads."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.request
from urllib.parse import urlparse

from . import __version__

ROOT=Path(__file__).resolve().parents[2]


def repository():
    with (ROOT/'release-config.json').open(encoding='utf-8-sig') as stream:
        name=json.load(stream)['repository']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',name):raise ValueError('Repositorio GitHub no válido')
    return name


def version_tuple(value):
    match=re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)',value)
    if not match:raise ValueError('Versión no compatible: '+value)
    return tuple(map(int,match.groups()))


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        if urlparse(newurl).scheme!='https':raise ValueError('Redirección sin HTTPS')
        redirected=super().redirect_request(request,fp,code,msg,headers,newurl)
        if redirected and urlparse(request.full_url).netloc!=urlparse(newurl).netloc:
            redirected.remove_header('Authorization')
        return redirected


def request(url,accept='application/vnd.github+json'):
    parsed=urlparse(url)
    if parsed.scheme!='https' or parsed.netloc!='api.github.com':raise ValueError('Origen de actualización no válido')
    headers={'User-Agent':'EeveeMayaBridge/'+__version__,'Accept':accept,'X-GitHub-Api-Version':'2022-11-28'}
    token=os.environ.get('EEVEE_MAYA_GITHUB_TOKEN')
    if token:headers['Authorization']='Bearer '+token
    return urllib.request.build_opener(SafeRedirect()).open(urllib.request.Request(url,headers=headers),timeout=30)


def select_release(release,current=__version__,maya_version='2024',repo=None):
    repo=repo or repository()
    tag=release['tag_name'];version=tag.removeprefix('v')
    if release.get('draft') or release.get('prerelease') or version_tuple(tag)<=version_tuple(current):return None
    asset_name='EeveeMayaBridge-'+version+'-maya'+maya_version+'-win64-Setup.exe'
    asset=next((item for item in release.get('assets',[]) if item['name']==asset_name),None)
    if asset is None:raise ValueError('La versión publicada no incluye instalador para Maya '+maya_version)
    digest=asset.get('digest') or ''
    if not re.fullmatch(r'sha256:[a-fA-F0-9]{64}',digest):raise ValueError('GitHub todavía no informa el SHA-256 del instalador')
    asset_url=asset['url']
    if not re.fullmatch(r'https://api\.github\.com/repos/'+re.escape(repo)+r'/releases/assets/\d+',asset_url):
        raise ValueError('El instalador no pertenece al repositorio configurado')
    return {'version':version,'name':asset_name,'url':asset_url,'sha256':digest.split(':',1)[1].lower(),
            'size':int(asset['size']),'notes':release.get('body',''),'page':'https://github.com/'+repo+'/releases/tag/'+tag}


def check(current=__version__,maya_version='2024'):
    repo=repository()
    with request('https://api.github.com/repos/'+repo+'/releases/latest') as response:release=json.load(response)
    return select_release(release,current,maya_version,repo)


def download(update,progress=None,directory=None):
    # Validate again: only execute an installer from the configured repository.
    repo=repository()
    if not re.fullmatch(r'https://api\.github\.com/repos/'+re.escape(repo)+r'/releases/assets/\d+',update['url']):raise ValueError('Origen de descarga no válido')
    expected='EeveeMayaBridge-'+update['version']+'-maya2024-win64-Setup.exe'
    if update['name']!=expected or not re.fullmatch(r'[a-f0-9]{64}',update['sha256']):raise ValueError('Instalador no válido')
    folder=Path(directory) if directory else Path(tempfile.mkdtemp(prefix='EeveeMayaBridge-update-'))
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/expected;partial=folder/(expected+'.part');digest=hashlib.sha256();length=0
    try:
        with request(update['url'],'application/octet-stream') as response, partial.open('wb') as stream:
            while True:
                data=response.read(1024*1024)
                if not data:break
                length+=len(data)
                if length>update['size']:raise ValueError('Tamaño de instalador no válido')
                stream.write(data);digest.update(data)
                if progress:progress(min(100,int(length*100/max(1,update['size']))))
        if length!=update['size'] or digest.hexdigest()!=update['sha256']:raise ValueError('El SHA-256 del instalador no coincide. No se ejecutó.')
        partial.replace(target)
        return target
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def launch(installer):
    arguments=[str(installer)]
    if ROOT.parent.name=='versions':arguments+=['--install-root',str(ROOT.parent.parent)]
    # The installer has its own visible UI; it stages a release for next restart.
    return subprocess.Popen(arguments,close_fds=True)

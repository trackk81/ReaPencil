"""Public GitHub Releases transport and verified, bounded update staging."""
import hashlib,json,re,stat,tempfile,zipfile
from pathlib import Path,PurePosixPath
from urllib.request import Request,urlopen
from urllib.parse import urlparse,unquote

REPOSITORY='trackk81/ReaPencil'
LATEST='https://api.github.com/repos/'+REPOSITORY+'/releases/latest'
DEPENDENCIES={'numba':'0.61.2','llvmlite':'0.44.0'}
MAX_ARCHIVE=512*1024**2

def version(value):
    match=re.fullmatch(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)',str(value))
    if not match:raise ValueError('정식 버전 번호가 아닙니다: '+str(value))
    return tuple(map(int,match.groups()))

def read_url(url,limit):
    if urlparse(url).scheme!='https':raise ValueError('HTTPS required')
    request=Request(url,headers={'User-Agent':'ReaPencil-updater','Accept':'application/vnd.github+json'})
    with urlopen(request,timeout=30) as response:
        if urlparse(response.geturl()).scheme!='https':raise ValueError('Insecure redirect')
        data=response.read(limit+1)
    if len(data)>limit:raise ValueError('Download exceeds size limit')
    return data

def release_info(data,current):
    if data.get('draft') or data.get('prerelease'):raise ValueError('정식 배포 버전만 설치할 수 있습니다.')
    tag=data['tag_name'];v=version(tag);name='ReaPencil-%d.%d.%d-Maya2025-Windows-x64.zip'%v
    matches=[a for a in data.get('assets',[]) if a['name']==name and a.get('state')=='uploaded']
    if len(matches)!=1:raise ValueError('Maya 2025 Windows x64 배포 파일이 없습니다.')
    asset=matches[0];url=asset['browser_download_url'];p=urlparse(url)
    if p.scheme!='https' or p.netloc!='github.com' or unquote(p.path)!='/'+REPOSITORY+'/releases/download/'+tag+'/'+name or p.query or p.fragment:
        raise ValueError('Unexpected release asset URL')
    digest=asset.get('digest') or ''
    if not re.fullmatch('sha256:[0-9a-fA-F]{64}',digest):raise ValueError('GitHub SHA-256 검증 정보가 없습니다. 수동 설치를 사용하세요.')
    size=asset.get('size',0)
    if not isinstance(size,int) or not 0<size<=MAX_ARCHIVE:raise ValueError('Invalid release size')
    return dict(version='.'.join(map(str,v)),available=v>version(current),url=url,name=name,
                sha256=digest[7:].lower(),size=size,notes=data.get('body','')[:30000],
                page='https://github.com/'+REPOSITORY+'/releases/tag/'+tag)

def latest(current):return release_info(json.loads(read_url(LATEST,2*1024**2)),current)

def safe_name(name):
    p=PurePosixPath(name)
    if not name or '\\' in name or ':' in name or p.is_absolute() or any(s in ('..','.') for s in name.split('/')):
        raise ValueError('Unsafe package path: '+name)
    if any(s.rstrip(' .')!=s or s.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))} for s in p.parts):
        raise ValueError('Invalid Windows package path')
    return p

def extract_verified(archive,destination,expected_version):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=False)
    seen=set();roots=set();total=0
    with zipfile.ZipFile(archive) as zipped:
        entries=zipped.infolist()
        if len(entries)>10000:raise ValueError('Too many package files')
        # Validate the entire directory before writing any payload.
        for entry in entries:
            p=safe_name(entry.filename.rstrip('/'));key=str(p).casefold()
            if key in seen:raise ValueError('Duplicate package path')
            seen.add(key);roots.add(p.parts[0]);total+=entry.file_size
            if stat.S_ISLNK(entry.external_attr>>16) or total>2*1024**3:raise ValueError('Invalid or oversized package')
        if len(roots)!=1:raise ValueError('Package must have exactly one root')
        root=destination/roots.pop()
        for entry in entries:
            target=destination.joinpath(*safe_name(entry.filename.rstrip('/')).parts)
            if entry.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with zipped.open(entry) as source,target.open('wb') as out:
                import shutil
                shutil.copyfileobj(source,out,1024*1024)
    verify_payload(root,expected_version)
    return root

def verify_payload(root,expected_version):
    root=Path(root).resolve();manifest=json.loads((root/'SHA256SUMS.json').read_text(encoding='utf-8'))
    if (manifest.get('product'),manifest.get('version'),manifest.get('maya'),manifest.get('platform'))!=('ReaPencil',expected_version,'2025','Windows x64'):
        raise ValueError('잘못된 버전 또는 지원되지 않는 플랫폼입니다.')
    if manifest.get('update_protocol')!=1 or manifest.get('dependencies')!=DEPENDENCIES:
        raise ValueError('설치기 또는 의존성이 변경된 배포입니다. 수동 설치가 필요합니다.')
    listed=manifest['files'];actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual!=set(listed)|{'SHA256SUMS.json'}:raise ValueError('Package manifest file set mismatch')
    for name,digest in listed.items():
        p=root.joinpath(*safe_name(name).parts)
        if p.is_symlink() or not p.resolve().is_relative_to(root) or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
            raise ValueError('Package checksum mismatch: '+name)
    for required in ('tools/install.py','plug-ins/reaPencil.py','scripts/reatoon/__init__.py'):
        if required not in listed:raise ValueError('Missing installer payload')
    return manifest

def stage(info,cache):
    folder=Path(tempfile.mkdtemp(prefix='release-',dir=cache));archive=folder/info['name']
    request=Request(info['url'],headers={'User-Agent':'ReaPencil-updater'})
    digest=hashlib.sha256();size=0
    with urlopen(request,timeout=60) as source,archive.open('wb') as out:
        if urlparse(source.geturl()).scheme!='https':raise ValueError('Insecure download redirect')
        while True:
            chunk=source.read(1024*1024)
            if not chunk:break
            size+=len(chunk)
            if size>min(info['size'],MAX_ARCHIVE):raise ValueError('Download exceeds expected size')
            digest.update(chunk);out.write(chunk)
    if size!=info['size'] or digest.hexdigest()!=info['sha256']:raise ValueError('다운로드 SHA-256 검증에 실패했습니다.')
    return extract_verified(archive,folder/'payload',info['version'])

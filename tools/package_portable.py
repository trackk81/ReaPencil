"""Build the portable runtime ZIP without workstation scenes, caches or reports."""
import ast,hashlib,json,shutil,tempfile
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
ROOT=Path(__file__).resolve().parents[1]
version_ast=ast.parse((ROOT/'scripts/reatoon/__init__.py').read_text(encoding='utf-8'))
VERSION=next(ast.literal_eval(node.value) for node in version_ast.body if isinstance(node,ast.Assign)
             and any(isinstance(target,ast.Name) and target.id=='__version__' for target in node.targets))
NAME='ReaPencil-'+VERSION+'-Maya2025-Windows-x64'
stage=Path(tempfile.mkdtemp(prefix='ReaPencilDistribution_'))/NAME
stage.mkdir()
def copy(source,relative):
    target=stage/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
for folder in ('scripts','plug-ins','rendererDesc'):
    for path in (ROOT/folder).rglob('*'):
        if path.is_file() and path.suffix in ('.py','.mel','.mll','.dll','.xml','.ogsfx') and '__pycache__' not in path.parts:
            copy(path,path.relative_to(ROOT))
copy(ROOT/'tools/install.py',Path('tools/install.py'))
copy(ROOT/'distribution/README_PUBLIC.md',Path('README.md'))
copy(ROOT/'docs/updates.md',Path('docs/updates.md'))
for path in sorted((ROOT/'docs').glob('release_*.md')):copy(path,Path('docs')/path.name)
for name in ('INSTALL.cmd','CHECK.cmd','SETUP.py','CHECK.py','INSTALL_KO.md'):
    copy(ROOT/'distribution'/name,Path(name))
    if name.endswith('.cmd'):
        p=stage/name;p.write_bytes(p.read_text(encoding='utf-8').replace('\r\n','\n').replace('\n','\r\n').encode('ascii'))
for path in (ROOT/'examples').glob('*.ma'):copy(path,Path('examples')/path.name)
notices=[]
for package in ('numba-0.61.2','llvmlite-0.44.0'):
    name=package+'-cp311-cp311-win_amd64.whl'
    path=ROOT/'distribution/wheels'/name
    copy(path,Path('wheels')/name)
    with ZipFile(path) as wheel:
        for entry in wheel.namelist():
            if not entry.endswith('/') and '.dist-info/' in entry and any(token in entry.upper() for token in ('LICENSE','COPYING','NOTICE')):
                target=stage/'THIRD_PARTY_LICENSES'/package/entry.split('.dist-info/',1)[1]
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(wheel.read(entry))
                notices.append(target.relative_to(stage).as_posix())
assert any('numba-' in p for p in notices) and any('llvmlite-' in p for p in notices)
(stage/'THIRD_PARTY_NOTICES.txt').write_text(
    'Offline accelerator wheels: numba 0.61.2 and llvmlite 0.44.0 (CPython 3.11 Windows x64).\n'
    'Downloaded from the public PyPI distribution using pinned versions.\n'
    'Wheel contents are unmodified; upstream copyright and license notices are retained.\n'
    +'\n'.join(notices)+'\n',encoding='utf-8')
files=sorted(p for p in stage.rglob('*') if p.is_file())
manifest=dict(product='ReaPencil',version=VERSION,platform='Windows x64',maya='2025',
              update_protocol=1,dependencies={'numba':'0.61.2','llvmlite':'0.44.0'},
              files={p.relative_to(stage).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
(stage/'SHA256SUMS.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
destination=ROOT/'dist';destination.mkdir(exist_ok=True)
archive=destination/(NAME+'.zip')
with ZipFile(archive,'w',ZIP_DEFLATED,compresslevel=9) as zip:
    for path in sorted(stage.rglob('*')):
        if path.is_file():zip.write(path,(Path(NAME)/path.relative_to(stage)).as_posix())
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
(destination/(NAME+'.sha256')).write_text(digest+'  '+archive.name+'\n',encoding='ascii')
with ZipFile(archive) as zip:assert zip.testzip() is None
result=dict(archive=str(archive),stage=str(stage),sha256=digest,bytes=archive.stat().st_size,files=len(manifest['files'])+1)
(ROOT/'validation').mkdir(exist_ok=True)
(ROOT/'validation/distribution_build.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))

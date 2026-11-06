"""Publish reviewed runtime sources and a verified portable GitHub release.

Uses Git Credential Manager; never writes credentials into source or artifacts.
Run --prepare to review the exact source tree before publishing.
"""
import argparse,hashlib,json,os,re,shutil,subprocess,sys
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[1]
REPO='trackk81/ReaPencil'

def prepare():
    stage=ROOT/'validation/github_public_source';stage.mkdir(parents=True,exist_ok=True)
    for name in ('plug-ins/reaToon.py','scripts/revtoon_start.py','scripts/reatoon/plugin_migration.py'):
        (stage/name).unlink(missing_ok=True)
    entries=[]
    for folder in ('scripts','plug-ins','rendererDesc'):
        entries.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in ('.py','.mel','.mll','.ogsfx','.xml') and '__pycache__' not in p.parts)
    entries.extend(ROOT/p for p in ['native/viewport_retained.cpp','native/viewport_draw.cpp','native/render_view.cpp','native/mesh_export.cpp',
        'tools/install.py','tools/package_portable.py','tools/publish_github.py','tools/build_native.ps1','tools/build_mesh_native.ps1','tools/build_image_native.ps1',
        'distribution/README_PUBLIC.md','distribution/INSTALL_KO.md','distribution/INSTALL.cmd','distribution/CHECK.cmd','distribution/SETUP.py','distribution/CHECK.py',
        'docs/updates.md','docs/release_085.md','docs/release_086.md','tests/test_updates.py'])
    expected=set()
    # Large unchanged upstream wheels are release assets, not Git history.
    for wheel in (ROOT/'distribution/wheels').glob('*.whl'):entries.append(wheel)
    for p in entries:
        relative=p.relative_to(ROOT);expected.add(relative.as_posix());target=stage/relative
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    shutil.copy2(ROOT/'distribution/README_PUBLIC.md',stage/'README.md');expected.add('README.md')
    ignore='__pycache__/\n*.pyc\n*.log\ndist/\nvalidation/\noutputs/\ndistribution/wheels/\n'
    (stage/'.gitignore').write_text(ignore,encoding='utf-8');expected.add('.gitignore')
    # Never publish stale staging files after the allowlist changes.
    extra={p.relative_to(stage).as_posix() for p in stage.rglob('*') if p.is_file() and '.git' not in p.relative_to(stage).parts}-expected
    if extra:raise RuntimeError('Unexpected files in public staging: '+repr(sorted(extra)))
    for p in stage.rglob('*'):
        if not p.is_file() or '.git' in p.relative_to(stage).parts or p.suffix=='.whl':continue
        data=p.read_bytes()
        private_home=str(Path.home()).replace('\\','/').encode()
        if private_home in data.replace(b'\\',b'/') or re.search(rb'(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY)',data):
            raise RuntimeError('Private material in public staging: '+p.relative_to(stage).as_posix())
    result=dict(stage=str(stage),files=len(expected))
    (ROOT/'validation/github_public_review.json').write_text(json.dumps(result,indent=2))
    return stage

def credential():
    p=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\nusername=trackk81\n\n',capture_output=True,text=True,timeout=30,
                     env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='Never'))
    fields=dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)
    if p.returncode or not fields.get('password'):raise RuntimeError('Log in with Git Credential Manager first.')
    return fields['password']

def publish(stage,notes):
    token=credential()
    def api(path,data=None,method=None,raw=None,content_type='application/json'):
        body=raw if raw is not None else (None if data is None else json.dumps(data).encode())
        req=Request(path if path.startswith('https://') else 'https://api.github.com'+path,data=body,
                    headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','Content-Type':content_type,
                             'User-Agent':'ReaPencil-release-publisher','X-GitHub-Api-Version':'2022-11-28'},
                    method=method or ('GET' if body is None else 'POST'))
        try:
            with urlopen(req,timeout=120) as response:return json.load(response)
        except HTTPError as error:
            # Response text cannot include request authorization headers.
            raise RuntimeError('GitHub HTTP '+str(error.code)+': '+error.read(2000).decode(errors='replace')) from None
    who=api('/user');assert who['login']=='trackk81',who['login']
    try:repo=api('/repos/'+REPO)
    except RuntimeError as error:
        if 'HTTP 404' not in str(error):raise
        repo=api('/user/repos',dict(name='ReaPencil',private=False,description='ReaPencil for Maya 2025: GPU viewport lines, CPU rendering and in-app updates.',has_wiki=False))
    if repo['private'] or repo['full_name']!=REPO:raise RuntimeError('Unexpected repository target')
    def git(*args):return subprocess.check_output(['git',*args],cwd=stage,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace').strip()
    if not (stage/'.git').exists():
        git('init','-b','main')
    git('config','user.name','trackk81');git('config','user.email',str(who['id'])+'+trackk81@users.noreply.github.com')
    if 'origin' not in git('remote').splitlines():git('remote','add','origin','https://github.com/'+REPO+'.git')
    if git('remote','get-url','origin')!='https://github.com/'+REPO+'.git':raise RuntimeError('Unexpected Git remote')
    git('add','--all')
    import ast
    tree=ast.parse((ROOT/'scripts/reatoon/__init__.py').read_text(encoding='utf-8'))
    version=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='__version__' for t in n.targets))
    if git('diff','--cached','--name-only'):git('commit','-m','ReaPencil '+version+': in-app GitHub updates and plug-in naming')
    git('push','-u','origin','main');head=git('rev-parse','HEAD')
    prefix='/repos/'+REPO;tag='v'+version
    try:release=api(prefix+'/releases/tags/'+tag)
    except RuntimeError as error:
        if 'HTTP 404' not in str(error):raise
        release=api(prefix+'/releases',dict(tag_name=tag,target_commitish=head,name='ReaPencil '+version,body=notes,draft=True,prerelease=False))
    name='ReaPencil-'+version+'-Maya2025-Windows-x64.zip'
    for path in (ROOT/'dist'/name,ROOT/'dist'/(name[:-4]+'.sha256')):
        data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
        existing=next((a for a in release.get('assets',[]) if a['name']==path.name),None)
        if existing:
            if existing.get('digest')!='sha256:'+digest:raise RuntimeError('Refusing to replace published asset: '+path.name)
            continue
        upload=release['upload_url'].split('{')[0]+'?name='+quote(path.name)
        asset=api(upload,raw=data,content_type='application/zip' if path.suffix=='.zip' else 'text/plain')
        if asset.get('digest')!='sha256:'+digest:raise RuntimeError('GitHub asset checksum mismatch')
    if release['draft']:release=api(prefix+'/releases/'+str(release['id']),dict(draft=False,make_latest='true'),method='PATCH')
    result=dict(repository=repo['html_url'],release=release['html_url'],commit=head,version=version)
    (ROOT/'validation/github_publication.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--prepare',action='store_true');parser.add_argument('--notes-file',type=Path)
    args=parser.parse_args();stage=prepare()
    if args.prepare:print(str(stage))
    else:
        if not args.notes_file:parser.error('--notes-file is required')
        publish(stage,args.notes_file.read_text(encoding='utf-8'))

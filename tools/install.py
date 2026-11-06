"""Install ReaToon in an ASCII Maya module path, preserving unrelated files."""
from __future__ import annotations
import argparse
import json
import sys
import os
from pathlib import Path
import shutil
import ast
import uuid
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent

def install(modules_dir=None, install_dir=None):
    if os.environ.get('MAYA_APP_DIR'):
        user_maya = Path(os.environ['MAYA_APP_DIR'])
    elif sys.platform == 'win32':
        user_maya = Path.home() / 'Documents' / 'maya'
    elif sys.platform == 'darwin':
        user_maya = Path.home() / 'Library' / 'Preferences' / 'Autodesk' / 'maya'
    else:
        user_maya = Path.home() / 'maya'
    modules = Path(modules_dir) if modules_dir else user_maya / 'modules'
    destination = Path(install_dir) if install_dir else user_maya / 'ReaToon'
    destination = destination.resolve()
    if sys.platform == 'win32' and not str(destination).isascii():
        raise ValueError('Choose an ASCII-only install path: Maya Windows Python plugin loading may fail with non-ASCII paths.')
    marker = destination / 'reatoon-install.json'
    if destination.exists() and any(destination.iterdir()) and not marker.exists():
        raise RuntimeError('Refusing to overwrite an unrecognized directory: ' + str(destination))
    files = [p for sub in ('scripts', 'plug-ins') for p in (ROOT / sub).rglob('*.py') if '__pycache__' not in p.parts]
    files += list((ROOT / 'rendererDesc').glob('*.xml'))
    files += list((ROOT / 'plug-ins').rglob('*.mll'))
    files += list((ROOT / 'scripts').glob('*.mel'))
    files += list((ROOT / 'scripts').rglob('*.ogsfx'))
    if not files or not (ROOT / 'plug-ins' / 'reaPencil.py').is_file():
        raise RuntimeError('Run this installer from a complete ReaToon distribution.')
    modules.mkdir(parents=True, exist_ok=True)
    destination.mkdir(parents=True, exist_ok=True)
    backup_root = destination / 'backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    copied = []
    payloads=[]
    for source in files:
        relative = source.relative_to(ROOT)
        target = destination / relative
        payloads.append((target,source.read_bytes()))
        copied.append(relative.as_posix())
    tree=ast.parse((ROOT/'scripts/reatoon/__init__.py').read_text(encoding='utf-8'))
    version=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='__version__' for t in n.targets))
    target_module = modules / 'ReaToon.mod'
    content = '+ ReaToon '+version+' ' + destination.as_posix() + '\nMAYA_RENDER_DESC_PATH+:=rendererDesc\n'
    payloads.append((target_module,content.encode('utf-8')))
    metadata=dict(product='ReaToon',display_name='ReaPencil',version=version,source=str(ROOT),files=copied,
                  modules_dir=str(modules.resolve()),install_dir=str(destination))
    payloads.append((marker,json.dumps(metadata,indent=2).encode('utf-8')))
    # Stage all replacements and retain every previous byte before committing.
    # A locked native DLL leaves the old installation usable after rollback.
    staged=[];applied=[]
    try:
        for index,(target,data) in enumerate(payloads):
            if target.exists() and target.read_bytes()==data:continue
            backup=None
            if target.exists():
                backup=backup_root/(str(index)+'-'+target.name)
                backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,backup)
            target.parent.mkdir(parents=True,exist_ok=True)
            temp=target.with_name(target.name+'.'+uuid.uuid4().hex+'.tmp');temp.write_bytes(data)
            staged.append((target,temp,backup))
        for target,temp,backup in staged:
            os.replace(temp,target);applied.append((target,backup))
    except Exception:
        errors=[]
        for target,backup in reversed(applied):
            try:
                if backup is None:target.unlink(missing_ok=True)
                else:
                    restore=target.with_name(target.name+'.restore.tmp');shutil.copy2(backup,restore);os.replace(restore,target)
            except Exception as error:errors.append(str(error))
        if errors:raise RuntimeError('Install rollback needs recovery from '+str(backup_root)+': '+'; '.join(errors))
        raise
    finally:
        for _,temp,_ in staged:temp.unlink(missing_ok=True)
    print('Installed:', destination)
    print('Registered module:', target_module)
    print('In Maya Python: import reapencil_start; reapencil_start.launch()')
    return destination

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--modules-dir')
    parser.add_argument('--install-dir')
    args = parser.parse_args()
    install(args.modules_dir, args.install_dir)

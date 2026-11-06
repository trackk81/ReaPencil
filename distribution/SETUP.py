"""Offline Windows Maya 2025 installer; never modifies Maya's Python packages."""
import argparse,ctypes,hashlib,importlib.util,json,os,struct,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(errors='backslashreplace')

def maya_documents():
    if os.environ.get('MAYA_APP_DIR'):return Path(os.environ['MAYA_APP_DIR'])
    buf=ctypes.create_unicode_buffer(32768)
    if ctypes.windll.shell32.SHGetFolderPathW(None,5,None,0,buf)!=0:
        raise RuntimeError('Windows Documents folder could not be located; use --maya-app-dir.')
    return Path(buf.value)/'maya'

def destination_for(profile):
    target=profile/'ReaToon'
    if str(target).isascii():return target
    # Maya's Windows Python plug-in loader requires an ASCII installation path.
    tag=hashlib.sha256(str(profile.resolve()).casefold().encode('utf-8')).hexdigest()[:12]
    target=Path(os.environ.get('PUBLIC','C:/Users/Public'))/'Documents/RevToon'/tag/'ReaToon'
    if not str(target).isascii():raise RuntimeError('Specify an ASCII path with --install-dir.')
    return target

def verify_package():
    manifest=json.loads((ROOT/'SHA256SUMS.json').read_text(encoding='utf-8'))
    for name,digest in manifest['files'].items():
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT.resolve()):raise ValueError('Invalid package path: '+name)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise RuntimeError('Package checksum mismatch: '+name+'; extract the ZIP again.')
    return manifest

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--maya-app-dir');parser.add_argument('--install-dir')
    args=parser.parse_args()
    if sys.platform!='win32' or struct.calcsize('P')!=8 or sys.version_info[:2]!=(3,11):
        raise RuntimeError('Use Windows x64 Maya 2025 mayapy.exe (Python 3.11).')
    from maya.api import OpenMaya as om
    if om.MGlobal.apiVersion()//10000!=2025:raise RuntimeError('This package supports Maya 2025 only.')
    import numpy
    original_numpy=numpy.__file__
    manifest=verify_package()
    profile=(Path(args.maya_app_dir) if args.maya_app_dir else maya_documents()).resolve()
    target=(Path(args.install_dir) if args.install_dir else destination_for(profile)).resolve()
    if not str(target).isascii():raise RuntimeError('The plug-in installation path must be ASCII.')
    accelerator=target.parent/'ReaToonAccelerator/py311'
    if (accelerator/'numpy').exists():raise RuntimeError('Unexpected NumPy in accelerator directory; choose a different installation path.')
    spec=importlib.util.spec_from_file_location('revtoon_installer',ROOT/'tools/install.py')
    installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
    installer.install(profile/'modules',target)
    print('Installing bundled CPU accelerator (offline)...',flush=True)
    pip_args=['pip','install','--no-index','--no-deps',
        '--disable-pip-version-check','--no-warn-script-location','--upgrade',
        '--find-links',str(ROOT/'wheels'),'--target',str(accelerator),
        'numba==0.61.2','llvmlite==0.44.0']
    # Maya's executable can misdecode non-ASCII argv even though Python handles
    # those filesystem paths correctly. Pass an ASCII bootstrap for pip too.
    code='import sys,runpy; sys.argv='+json.dumps(pip_args,ensure_ascii=True)+"; runpy.run_module('pip',run_name='__main__')"
    subprocess.check_call([sys.executable,'-s','-c',code])
    sys.path.insert(0,str(accelerator))
    import numba,llvmlite
    assert numba.__version__=='0.61.2' and llvmlite.__version__=='0.44.0'
    assert numpy.__file__==original_numpy
    record=dict(version=manifest['version'],install_dir=str(target),modules_dir=str(profile/'modules'),
                accelerator_dir=str(accelerator),mayapy=sys.executable,
                numpy_version=numpy.__version__,numpy_path=numpy.__file__)
    (ROOT/'installation.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print('Installation complete. Restart Maya 2025.\nPython: import reapencil_start; reapencil_start.launch()',flush=True)
    return record

if __name__=='__main__':
    try:main()
    except Exception:
        import traceback
        text=traceback.format_exc();(ROOT/'install_error.txt').write_text(text,encoding='utf-8')
        print(text,file=sys.stderr);sys.exit(1)

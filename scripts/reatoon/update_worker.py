"""Detached update installer: waits for Maya, never terminates it."""
import ctypes,importlib.util,json,os,sys,time,traceback
from pathlib import Path

def maya_running():
    if sys.platform!='win32':raise RuntimeError('Windows Maya 2025 only')
    from ctypes import wintypes as w
    class Entry(ctypes.Structure):
        _fields_=[('size',w.DWORD),('usage',w.DWORD),('pid',w.DWORD),('heap',ctypes.c_size_t),('module',w.DWORD),('threads',w.DWORD),('parent',w.DWORD),('priority',w.LONG),('flags',w.DWORD),('exe',w.WCHAR*260)]
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD];k.CreateToolhelp32Snapshot.restype=w.HANDLE
    for name in ('Process32FirstW','Process32NextW'):
        getattr(k,name).argtypes=[w.HANDLE,ctypes.POINTER(Entry)];getattr(k,name).restype=w.BOOL
    k.CloseHandle.argtypes=[w.HANDLE];k.CloseHandle.restype=w.BOOL
    handle=k.CreateToolhelp32Snapshot(2,0)
    if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    try:
        e=Entry();e.size=ctypes.sizeof(e)
        if not k.Process32FirstW(handle,ctypes.byref(e)):raise ctypes.WinError(ctypes.get_last_error())
        while True:
            if e.pid!=os.getpid() and e.exe.casefold() in ('maya.exe','mayabatch.exe','mayapy.exe'):return True
            if not k.Process32NextW(handle,ctypes.byref(e)):
                if ctypes.get_last_error()!=18:raise ctypes.WinError(ctypes.get_last_error())
                return False
    finally:k.CloseHandle(handle)

def main(job_path,running=maya_running,sleep=time.sleep,notify=True):
    if __package__:
        from .update_core import verify_payload
    else:
        from update_core import verify_payload
    job_path=Path(job_path);job=json.loads(job_path.read_text(encoding='utf-8'));status=job_path.with_name('status.json')
    def report(state,**extra):
        temp=status.with_suffix('.tmp');temp.write_text(json.dumps(dict(state=state,version=job['version'],**extra),ensure_ascii=False),encoding='utf-8');os.replace(temp,status)
    try:
        report('waiting_for_maya_exit');deadline=time.monotonic()+24*3600
        while running():
            if job_path.with_name('cancel').exists():report('cancelled');return
            if time.monotonic()>deadline:raise RuntimeError('24시간 내 Maya가 종료되지 않아 설치를 취소했습니다.')
            sleep(2)
        if job_path.with_name('cancel').exists():report('cancelled');return
        root=Path(job['payload']);verify_payload(root,job['version'])
        target=Path(job['install_dir']);previous=json.loads((target/'reatoon-install.json').read_text())
        if previous['version']!=job['previous_version']:raise RuntimeError('설치 버전이 다른 설치 작업으로 변경되었습니다. 업데이트를 다시 확인하세요.')
        report('installing')
        spec=importlib.util.spec_from_file_location('reapencil_update_installer',root/'tools/install.py')
        installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
        installer.install(modules_dir=job['modules_dir'],install_dir=target)
        report('installed',message='Maya를 다시 실행하세요.')
        if notify and sys.platform=='win32':
            ctypes.windll.user32.MessageBoxW(None,'ReaPencil '+job['version']+' 업데이트 설치가 완료되었습니다.\nMaya를 다시 실행하세요.','ReaPencil 업데이트',0x40)
    except Exception:
        report('error',error=traceback.format_exc())
        if notify and sys.platform=='win32':
            ctypes.windll.user32.MessageBoxW(None,'업데이트 설치에 실패했습니다.\n업데이트 창에서 상세 내용을 확인하세요.','ReaPencil 업데이트',0x10)
        raise

if __name__=='__main__':main(sys.argv[1])

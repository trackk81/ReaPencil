"""Nonblocking Maya update dialog; installs only after all Maya sessions exit."""
from .i18n import tr
import hashlib,json,os,shutil,subprocess,sys,threading
from pathlib import Path
from maya import cmds,utils,OpenMayaUI
from PySide6 import QtCore,QtWidgets
from shiboken6 import wrapInstance,isValid
from . import __version__,update_core

_window=None

class Updates(QtWidgets.QDialog):
    def __init__(self):
        super().__init__(wrapInstance(int(OpenMayaUI.MQtUtil.mainWindow()),QtWidgets.QWidget))
        self.setWindowTitle(tr('ReaPencil 업데이트'));self.resize(530,340);self.info=None;self.busy=False
        self.root=Path(__file__).resolve().parents[2]
        self.seen_status=None
        base=Path(cmds.internalVar(userAppDir=True))/'ReaPencilUpdates'
        self.cache=base/hashlib.sha256(str(self.root).encode()).hexdigest()[:16];self.cache.mkdir(parents=True,exist_ok=True)
        layout=QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(tr('현재 버전 '+__version__+' · GitHub '+update_core.REPOSITORY)))
        self.status=QtWidgets.QLabel(tr('업데이트 확인을 누르세요.'));self.status.setWordWrap(True);layout.addWidget(self.status)
        self.notes=QtWidgets.QPlainTextEdit();self.notes.setReadOnly(True);layout.addWidget(self.notes)
        layout.addWidget(QtWidgets.QLabel(tr('설치 예약 후 작업을 저장하고 모든 Maya를 직접 종료하세요.\n설치 완료 후 Maya를 다시 실행하면 적용됩니다.')))
        row=QtWidgets.QHBoxLayout();layout.addLayout(row)
        self.check_button=QtWidgets.QPushButton(tr('업데이트 확인'));self.install_button=QtWidgets.QPushButton(tr('다운로드 및 설치 예약'))
        self.install_button.setEnabled(False);self.check_button.clicked.connect(self.check);self.install_button.clicked.connect(self.install)
        row.addWidget(self.check_button);row.addWidget(self.install_button)
        self.cancel_button=QtWidgets.QPushButton(tr('설치 예약 취소'));self.cancel_button.clicked.connect(self.cancel);row.addWidget(self.cancel_button)
        self.timer=QtCore.QTimer(self);self.timer.timeout.connect(self.poll);self.timer.start(1000);self.poll()

    def background(self,fn,done):
        self.busy=True;self.check_button.setEnabled(False);self.install_button.setEnabled(False)
        def task():
            try:value=fn();error=None
            except Exception as exc:value=None;error=str(exc)
            def complete():
                if not isValid(self):return
                self.busy=False;self.check_button.setEnabled(True)
                if error:self.status.setText(tr('업데이트 실패: '+error))
                else:
                    try:done(value)
                    except Exception as exc:self.status.setText(tr('업데이트 실패: '+str(exc)))
            utils.executeDeferred(complete)
        threading.Thread(target=task,daemon=True).start()

    def check(self):
        if self.busy:return
        self.status.setText(tr('GitHub에서 최신 정식 버전을 확인하고 있습니다…'))
        def done(info):
            self.info=info;self.notes.setPlainText(info['notes'])
            self.status.setText(tr(('새 버전 '+info['version']+' · %.1f MB'%(info['size']/1024**2)) if info['available'] else '최신 버전입니다. ('+__version__+')'))
            self.install_button.setEnabled(info['available'])
        self.background(lambda:update_core.latest(__version__),done)

    def install(self):
        if self.busy:return
        if not self.info or not self.info['available']:self.check();return
        existing=self.pending()
        if existing and existing.get('state') in ('waiting_for_maya_exit','installing'):
            self.status.setText(tr('이미 설치가 예약되어 있습니다.'));return
        info=dict(self.info)
        self.status.setText(tr('배포 파일 다운로드 및 SHA-256 검증 중…'))
        def done(payload):
            marker=json.loads((self.root/'reatoon-install.json').read_text(encoding='utf-8'))
            if not marker.get('modules_dir'):raise RuntimeError('설치 위치 정보가 없습니다. 최신 배포본으로 한 번 재설치하세요.')
            job_dir=payload.parent.parent
            for name in ('update_worker.py','update_core.py'):shutil.copy2(Path(__file__).parent/name,job_dir/name)
            job=dict(version=info['version'],previous_version=__version__,payload=str(payload),install_dir=str(self.root),modules_dir=marker['modules_dir'])
            job_file=job_dir/'job.json';job_file.write_text(json.dumps(job,ensure_ascii=False),encoding='utf-8')
            exe=Path(sys.executable).parent/'mayapy.exe'
            if not exe.is_file():raise RuntimeError('Maya 2025 mayapy.exe를 찾을 수 없습니다.')
            environment=dict(os.environ,MAYA_SKIP_USERSETUP_PY='1',PYTHONNOUSERSITE='1')
            argv=[str(job_dir/'update_worker.py'),str(job_file)]
            bootstrap='import sys,runpy; sys.path.insert(0,'+json.dumps(str(job_dir),ensure_ascii=True)+'); sys.argv='+json.dumps(argv,ensure_ascii=True)+"; runpy.run_path(sys.argv[0],run_name='__main__')"
            with (job_dir/'worker.log').open('wb') as log:
                subprocess.Popen([str(exe),'-s','-c',bootstrap],stdout=log,stderr=subprocess.STDOUT,
                                 env=environment,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS,close_fds=True)
            (self.cache/'pending.json').write_text(json.dumps(dict(job=str(job_file),status=str(job_dir/'status.json'))),encoding='utf-8')
            self.status.setText(tr('설치 예약 완료. 작업을 저장하고 모든 Maya 창을 닫으세요.'));self.poll()
        self.background(lambda:update_core.stage(info,self.cache),done)

    def pending(self):
        p=self.cache/'pending.json'
        if not p.is_file():return None
        record=json.loads(p.read_text(encoding='utf-8'));status=Path(record['status'])
        if not status.is_file():return dict(state='waiting_for_maya_exit')
        return json.loads(status.read_text(encoding='utf-8'))

    def poll(self):
        try:
            state=self.pending();active=bool(state and state['state'] in ('waiting_for_maya_exit','installing'))
            self.cancel_button.setEnabled(active and state['state']=='waiting_for_maya_exit')
            if self.busy or not state:return
            signature=json.dumps(state,sort_keys=True)
            if signature==self.seen_status:return
            self.seen_status=signature
            messages={'waiting_for_maya_exit':'설치 예약 중: 모든 Maya 창을 닫으면 적용됩니다.','installing':'업데이트 설치 중…','installed':'업데이트 설치 완료. 현재 실행 버전: '+__version__,'cancelled':'설치 예약이 취소되었습니다.','error':'설치 실패: '+state.get('error','')}
            self.status.setText(tr(messages.get(state['state'],state['state'])))
        except Exception as error:self.status.setText(tr(str(error)))

    def cancel(self):
        p=self.cache/'pending.json'
        if p.is_file():
            job=json.loads(p.read_text(encoding='utf-8'))['job'];Path(job).with_name('cancel').touch()
            self.status.setText(tr('설치 예약 취소 요청 중…'))

def show():
    global _window
    if _window is None or not isValid(_window):_window=Updates()
    _window.show();_window.raise_();_window.check()
    return _window

def close():
    global _window
    if _window is not None and isValid(_window):
        _window.timer.stop();_window.close();_window.deleteLater()
    _window=None

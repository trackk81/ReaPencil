"""Throttled main-thread render status; never changes scene or render settings."""
import time

STAGES = {
    'prepare': ('Preparing render', '렌더 준비'),
    'export': ('Reading meshes', '메시 준비'),
    'alpha': ('Preparing material alpha', '재질 알파 준비'),
    'depth': ('Preparing depth and occlusion', '깊이·가림 준비'),
    'intersections': ('Finding intersections', '교차선 계산'),
    'alpha_clip': ('Clipping intersections to alpha', '교차선의 알파 가림 계산'),
    'lines': ('Generating lines and alpha outlines', '선·알파 윤곽 생성'),
    'visibility': ('Preparing line visibility', '선 가림 판정 준비'),
    'brush': ('Preparing brush strokes', '붓 스트로크 준비'),
    'strokes': ('Drawing CPU lines', 'CPU 선 렌더링'),
    'output': ('Saving images', '이미지 저장'),
    'display': ('Updating Render View', 'Render View 표시'),
    'complete': ('Render complete', '렌더 완료'),
    'failed': ('Render failed', '렌더 오류'),
}
_ACTIVE = False


class _Window:
    def __init__(self, english):
        from PySide6 import QtWidgets, QtCore
        from shiboken6 import wrapInstance
        from maya import OpenMayaUI
        parent = wrapInstance(int(OpenMayaUI.MQtUtil.mainWindow()), QtWidgets.QWidget)
        self.dialog = QtWidgets.QDialog(parent)
        self.dialog.setObjectName('reaPencilRenderProgress')
        self.dialog.setWindowTitle('ReaPencil — Render' if english else 'ReaPencil — 렌더 진행')
        self.dialog.setWindowModality(QtCore.Qt.WindowModal)
        self.dialog.setWindowFlag(QtCore.Qt.WindowCloseButtonHint, False)
        self.dialog.setMinimumWidth(520)
        layout = QtWidgets.QVBoxLayout(self.dialog)
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(92)
        self.bar = QtWidgets.QProgressBar()
        self.bar.setRange(0, 100)
        layout.addWidget(self.status)
        layout.addWidget(self.bar)
        self.dialog.show()
        # Realize the window before reading the scene. Subsequent updates only
        # repaint this dialog; never process Maya idle/selection callbacks.
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.ExcludeUserInputEvents |
                                           QtCore.QEventLoop.ExcludeSocketNotifiers)

    def update(self, percent, status):
        self.status.setText(status)
        self.bar.setValue(percent)
        self.dialog.repaint()

    def close(self):
        self.dialog.hide()
        self.dialog.deleteLater()


class RenderProgress:
    """Each percentage describes the named stage, not estimated total time.

    Maya commands run only at main-thread checkpoints. Native work already in
    flight keeps the last honest count until the next checkpoint. Do not pump
    arbitrary Qt events: scene-edit callbacks must not re-enter an active render.
    """
    def __init__(self, commands=None, clock=None, window_factory=None):
        if commands is None:
            from maya import cmds
            commands = cmds
        self.cmds = commands
        self.clock = clock or time.perf_counter
        self.started = self.clock()
        self.last_update = float('-inf')
        self.stage = None
        self.owned = False
        self.window = None
        self.window_factory = window_factory or _Window
        self.batch = bool(commands.about(batch=True))
        self.english = (commands.optionVar(q='reaPencilLanguage') == 'en'
                        if commands.optionVar(exists='reaPencilLanguage') else False)

    def __enter__(self):
        global _ACTIVE
        if _ACTIVE:
            raise RuntimeError('A ReaPencil render is already in progress.')
        _ACTIVE = True
        try:
            if not self.batch:
                self.window = self.window_factory(self.english)
                self.owned = True
            self('prepare')
        except Exception:
            if self.window is not None:self.window.close()
            _ACTIVE = False
            raise
        return self

    def __call__(self, stage, done=0, total=None, detail=''):
        now = self.clock()
        if (stage == self.stage and not (total is not None and total > 0 and done >= total)
                and now-self.last_update < (2.0 if self.batch else .15)):
            return
        self.stage = stage
        self.last_update = now
        title = STAGES.get(stage, (stage, stage))[0 if self.english else 1]
        elapsed = max(0, int(now-self.started))
        elapsed_text = '%d:%02d' % (elapsed//60, elapsed%60)
        if total is not None and total > 0:
            done = max(0, min(int(done), int(total)))
            percent = int(100*done/int(total))
            count = '{:,} / {:,} ({:d}%)'.format(done, int(total), percent)
        else:
            percent = 0
            count = 'Working…' if self.english else '계산 중…'
        label = 'Stage progress' if self.english else '현재 단계 진행률'
        timer = 'Elapsed' if self.english else '경과 시간'
        # Long DAG paths must not stretch the dialog beyond the screen.
        detail = str(detail).replace('\n', ' ')
        if len(detail) > 86:
            detail = '…' + detail[-85:]
        status = '%s\n%s: %s\n%s: %s' % (title, label, count, timer, elapsed_text)
        if detail:
            status += '\n' + detail
        if self.owned:
            self.window.update(percent, status)
        else:
            print('ReaPencil | ' + status.replace('\n', ' | '))

    def __exit__(self, exc_type, exc, traceback):
        global _ACTIVE
        try:
            self('failed' if exc_type else 'complete', 1, 1)
        finally:
            try:
                if self.owned:
                    self.window.close()
            finally:
                self.owned = False
                _ACTIVE = False
        return False

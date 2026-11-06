# ReaPencil GitHub 업데이트

배포 저장소: https://github.com/trackk81/ReaPencil

Windows x64 / Maya 2025용입니다. 다른 PC에서도 GitHub 로그인 없이 공개 Release의 배포 파일을 받을 수 있습니다.

## 사용

ReaPencil 메뉴의 **업데이트 확인…**을 선택하면 현재 버전, 최신 정식 버전, 변경 사항을 표시합니다. **업데이트 설치…**에서도 같은 창을 열 수 있습니다. 새 버전이 있으면 **다운로드 및 설치 예약**을 누릅니다.

다운로드와 SHA-256·내부 파일 검증이 끝나면 설치가 예약됩니다. 작업을 저장하고 모든 Maya 창을 직접 종료하세요. 별도 설치 도우미가 Maya 종료를 기다렸다가 파일을 교체합니다. Maya를 다시 실행하면 새 버전이 적용됩니다. Maya를 강제 종료하거나 장면을 자동 저장하지 않습니다. 대기 중에는 설치 예약을 취소할 수 있습니다. 설치 실패 정보는 다음 업데이트 창에서 확인할 수 있습니다.

기존 파일은 설치 폴더의 `backups`에 보관합니다. 파일 교체 중 실패하면 이전 파일을 복구합니다. 현재와 다른 Maya 버전/플랫폼, CPU 가속 의존성이 변경된 패키지는 수동 설치가 필요하다고 안내합니다.

## Plug-in Manager 이름

새 기본 파일은 **reaPencil.py**입니다. 기존 명령과 노드 이름은 저장된 장면을 읽기 위해 유지합니다. **reaToon.py**는 기존 장면의 플러그인 요구 사항과 이전 Auto load 설정을 처리하는 작은 호환 연결 파일입니다. 실제 노드·명령은 reaPencil.py가 등록합니다. 사용자가 이전 파일의 Auto load를 켰다면 새 파일로 이전하며, Auto load를 사용하지 않던 사용자는 그대로 둡니다.

## 새 버전 배포

파일을 GitHub에 커밋하는 것만으로는 업데이트가 배포되지 않습니다. 새 정식 GitHub **Release**와 해당 버전의 ZIP이 필요합니다.

1. `scripts/reatoon/__init__.py`의 버전을 높이고 변경 사항을 검증합니다.
2. Maya 2025 `mayapy -s tools/package_portable.py`로 ZIP과 SHA-256을 만듭니다.
3. `tools/publish_github.py`로 검토된 공개 소스와 해당 ZIP을 게시합니다. Git Credential Manager의 로그인된 `trackk81` 계정을 사용하며 토큰을 코드에 저장하지 않습니다.
4. 태그는 `v0.8.5` 형식, ZIP은 `ReaPencil-0.8.5-Maya2025-Windows-x64.zip` 형식입니다. Draft/Prerelease는 업데이트 대상으로 사용하지 않습니다.

업데이터는 고정 저장소의 HTTPS Release 자산만 받습니다. GitHub가 제공하는 ZIP의 SHA-256과 모든 내부 파일의 해시·경로·플랫폼을 검증한 후 설치 도우미에 전달합니다. GitHub 인증 정보는 플러그인에 포함되지 않습니다. 검증 정보는 다운로드 무결성을 확인하며 별도 코드 서명은 아닙니다.

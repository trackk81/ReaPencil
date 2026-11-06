# ReaPencil 0.8.5 다른 PC 설치 및 테스트

지원 대상: **Windows 64비트 / Maya 2025**. 다른 Maya 버전과 macOS/Linux용 바이너리는 포함하지 않습니다.

## 설치

1. ZIP을 다른 PC로 복사하고 **전체 압축을 풉니다**. ZIP 내부에서 바로 실행하지 마세요.
2. Maya를 종료한 뒤 `INSTALL.cmd`를 더블클릭합니다. CPU 가속 패키지가 포함되어 인터넷 연결 없이 설치됩니다.
3. Maya 2025를 실행하고 Script Editor의 **Python 탭**에서 아래 두 줄을 실행합니다.

```python
import reapencil_start
reapencil_start.launch()
```

플러그인 허용창에서는 `reaPencil.py`와 `reaPencilDraw084.mll` 등 설치한 ReaPencil 파일인지 확인하고 Allow를 선택하세요. 설치기는 Maya 보안 설정을 바꾸지 않습니다. 예전 `reaToon.py`의 Auto load를 켜 둔 경우에만 새 파일로 그 선택을 이전합니다.

Maya를 기본 경로에 설치하지 않았다면 명령 프롬프트에서 실제 mayapy 경로를 지정합니다.

```bat
INSTALL.cmd "D:\Autodesk\Maya2025\bin\mayapy.exe"
CHECK.cmd "D:\Autodesk\Maya2025\bin\mayapy.exe"
```

기본 설치 위치는 Windows의 실제 문서 폴더 아래 `maya/ReaToon`입니다. `MAYA_APP_DIR`이 있으면 해당 위치를 사용합니다. 사용자 문서 경로에 한글 등이 있으면 플러그인만 `공용 문서/RevToon/<사용자별 식별 폴더>/ReaToon`의 영문 경로에 설치하며, 모듈 등록은 해당 사용자의 Maya 폴더에 합니다. 실제 위치는 `installation.json`에 기록됩니다. 기존 ReaPencil 파일은 변경 전 백업됩니다.

## 점검과 테스트

- 설치 후 `CHECK.cmd` 실행: 별도 Maya 프로세스에서 작은 큐브 장면을 만들고 플러그인 로드, GPU 교차선/외곽선, 분할 경계 교차선과 캐시 정리, CPU 렌더를 검사합니다. 현재 작업 중인 Maya 장면은 열거나 수정하지 않습니다.
- 결과는 `diagnostics/report.json`, CPU 결과 이미지는 `diagnostics/test_beauty.png`에 저장됩니다. 문제가 있으면 이 보고서를 전달해 주세요. 자동 전송은 하지 않습니다.
- 실제 Maya 화면에서는 테스트 장면을 열고 **ReaPencil → Enable live viewport lines**를 켭니다. 스무스를 쓸 때는 **Add Render Settings Node**의 `Enabled Smooth Mesh`를 확인합니다.
- 최종 렌더는 Render Settings의 **ReaPencil**을 선택합니다. 최종 렌더는 CPU, 뷰포트 선 계산은 GPU입니다.
- `examples/RevToon_Intersections.ma`는 교차선 테스트용 예제입니다. 본인 장면에서는 복사본으로 테스트하세요.
- 처음 GPU 커널 또는 CPU 가속 코드를 컴파일할 때는 이후 실행보다 오래 걸릴 수 있습니다.

GPU 뷰포트에는 그래픽 드라이버의 **OpenCL 및 fp64(double precision)** 지원이 필요합니다. CUDA Toolkit이나 별도 Python GPU 패키지는 필요하지 않습니다. 현재 실제 GPU 검증 장치는 RTX 4070이며 다른 GPU 모델은 점검 도구로 확인해야 합니다. Maya 기본 NumPy를 변경하지 마세요. Numba 0.61.2와 llvmlite 0.44.0은 별도 폴더에 설치됩니다.

## Pencil+가 없는 PC에서 이전

1. ReaPencil을 설치하고 원본 장면의 **복사본**을 엽니다. Maya가 Pencil+ 플러그인 누락/unknown 노드 경고를 표시할 수 있습니다. unknown 노드는 삭제하지 마세요.
2. **ReaPencil → Pencil+ 장면 가져오기 / 이전**을 실행합니다. 저장된 라인·라인셋·오브젝트/재질 연결·브러시 크기/색·Smooth Mesh 설정과 지원되는 Render Elements를 읽습니다.
3. 변환 결과 창에서 복구된 노드 수와 미지원 항목을 확인합니다. **Use ReaPencil in Render Settings**를 선택해 CPU 렌더하거나 **Enable live viewport lines**를 켭니다.
4. Pencil 재질을 Maya 뷰포트에서도 보려면 **Assign converted Maya materials**를 실행합니다. 일반 rampShader로 근사 변환하고 기존 면별 할당을 유지합니다. 원본 Pencil 셰이더 노드는 남깁니다.
5. 원래 파일 형식(`.ma` 또는 `.mb`)을 유지해 새 이름으로 저장하세요. unknown 데이터가 남아 있으면 Maya가 형식 변경을 막을 수 있습니다. 원본 파일은 자동 수정하지 않습니다.

라이선스 서버·로그인·컴퓨터 인증은 없고 Pencil+ 실행 파일도 포함되지 않습니다. `.ma`와 `.mb`의 저장 데이터로 변환하므로 Pencil+ 설치가 필요하지 않습니다. 저장되지 않은 기본값은 관찰한 Pencil+ 4.2.3 속성 기준으로 복원합니다. 브러시 맵/획 연결, 원본 절차적 평가, 전용 PLD, 모든 버전의 완전 호환은 지원하지 않습니다. 원본 노드가 이미 삭제됐거나 저장 과정에서 데이터가 유실된 파일은 복구할 수 없습니다.

기본 플러그인은 `reaPencil.py`입니다. `reaToon.py`는 기존 장면의 요구 사항을 읽는 작은 호환 연결 파일이며, 실제 노드·명령은 새 플러그인이 등록합니다. 기존 명령과 내부 노드/렌더러 ID는 이어서 사용할 수 있습니다.

## GitHub 업데이트

처음 이 배포본을 설치한 다음부터 **ReaPencil → 업데이트 확인… / 업데이트 설치…**를 사용할 수 있습니다. 공개 저장소 `trackk81/ReaPencil`의 새 정식 Release를 확인합니다. **다운로드 및 설치 예약**을 누른 뒤 작업을 저장하고 모든 Maya를 종료하세요. 설치 완료 알림 후 Maya를 다시 실행하면 새 버전이 적용됩니다. GitHub 로그인은 필요하지 않습니다. 다운로드 및 모든 내부 파일을 검증하며, 교체 실패 시 기존 파일을 복구합니다.

추가 교차선 가림 검사는 원근 카메라의 가시선에 적용됩니다. 직교 카메라와 은선은 기존 VP2 가림 처리를 유지합니다. 모든 Pencil+ 기능과 결과가 동일하거나 30/60 FPS로 동작한다는 보장은 없습니다.

## 구성과 제거

0.8.2에는 대형 장면의 GPU BVH 메모리 오류 수정, 공간별 분할 처리, 화면 밖 선 제외와 캐시 정리가 포함됩니다. 0.8.1의 메시 선택 유지, Objects `+` 직접 추가와 이름 변경도 포함됩니다. 최종 렌더는 기존 CPU 방식을 유지합니다.

0.8.4 이후에는 카메라가 바뀔 때 선 버퍼를 다시 전송하지 않고 GPU에서 외곽선을 판단합니다. 스무스를 끈 약 1,595만 삼각형 장면을 RTX 4070에서 360도 회전하여 평균 34.1fps를 측정했습니다. 초기 준비에는 약 71초가 걸렸으며 대규모 메시 변형의 30fps를 의미하지 않습니다. Merge Groups·고급 브러시·비다양체 메시에서는 기존 GPU 표시 경로를 사용합니다. 대형 장면은 임시 캐시용 디스크 공간도 사용하며 장면 교체·뷰포트 해제·정상 종료 시 정리합니다.

이 ZIP에는 실행에 필요한 ReaPencil 코드, Maya 2025 네이티브 모듈(호환용 이전 VP2 모듈 포함), 설치/점검 도구, 업데이트 설명과 CPU 가속 wheel 2개가 포함됩니다. 개발 PC의 실제 프로젝트 장면·벤치마크 이미지·캐시·설치 설정은 포함하지 않습니다. `THIRD_PARTY_LICENSES`에는 wheel에 포함된 라이선스 원문이 있습니다.

제거하려면 Maya를 종료하고 `installation.json`에 기록된 경로의 `ReaToon.mod`, 이 플러그인 설치 폴더, 전용 `ReaToonAccelerator` 폴더만 제거하세요. 다른 Maya 폴더는 삭제하지 마세요.

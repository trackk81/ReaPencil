# ReaPencil for Maya

Maya 2025 / Windows x64용 선 렌더링 플러그인입니다. 뷰포트 프리뷰와 최종 CPU 렌더, 라인셋, 독립 브러시, Merge Groups, 렌더 요소와 PNG·SVG·EPS 출력을 지원합니다.

## 0.8.56 업데이트

일반 프리뷰의 카메라 깊이별 선폭 감소와 선택 메시의 거리 자동 측정, 측정 버튼 정리 및 한글 표시 수정을 포함합니다. [변경 사항과 실제 Maya 검증 범위](docs/release_056.md)를 확인하세요. 최종 렌더는 CPU입니다.

## 설치

[최신 릴리스](https://github.com/trackk81/ReaPencil/releases/latest)의 `ReaPencil-버전-Maya2025-Windows-x64.zip`을 내려받아 전체 압축을 풀고 `INSTALL.cmd`를 실행하세요. GitHub에서 자동 생성한 Source code ZIP은 설치 파일이 아닙니다. 기존 설치본에서는 ReaPencil 메뉴의 업데이트 확인과 설치 예약을 사용할 수 있습니다.

설치 후 Maya를 다시 실행합니다. 필요한 경우 Script Editor의 Python 탭에서 실행하세요.

```python
import reapencil_start
reapencil_start.launch()
```

Plug-in Manager의 주 플러그인은 `reaPencil.py`입니다. 보안 경고가 나오면 설치 위치와 플러그인 이름을 확인한 뒤 허용하세요.

## 뷰포트와 렌더

뷰포트 **Renderer → ReaPencil Preview** 또는 **ReaPencil Fast Preview**를 선택합니다. 오른쪽 옵션 버튼에서 뷰포트 성능이나 고속 프리뷰 설정을 바꿉니다. 선 종류·브러시·오브젝트·재질 대상은 Line Window에서 편집합니다. 고속 프리뷰는 라인셋에 등록된 오브젝트나 재질에 적용되며, 정확한 최종 결과는 CPU 렌더로 확인합니다.

GPU 표시는 Viewport 2.0 OpenGL Core Profile과 OpenCL fp64 지원이 필요합니다. CUDA Toolkit은 필요하지 않습니다. 배포 대상은 Maya 2025 / Windows x64이며 CPU 의존성 wheel을 포함합니다.

## 호환과 한계

지원되는 Pencil+ 장면 설정을 읽어 이관할 수 있으며, Pencil+가 설치되지 않은 환경의 지원되는 저장 속성도 처리합니다. 원본 전체 기능이나 모든 브러시·폐곡선·뷰포트 표현의 일치를 보장하지 않습니다. 지원되지 않는 항목은 이관 검사 결과를 확인하세요.

PSOFT 원본 플러그인·바이너리·셰이더·라이선스 코드는 배포하지 않습니다. [외부 구성요소 고지](THIRD_PARTY_NOTICES.txt)를 확인하세요.

## 소스와 빌드

이 태그의 런타임 파일은 릴리스 ZIP 및 검증한 로컬 0.8.56 설치본과 일치합니다. [런타임 해시 목록](docs/runtime_056_sha256.json)을 제공합니다. 사용자 장면과 내부 검증 데이터는 포함하지 않습니다.

네이티브 Maya 모듈을 다시 빌드하려면 Maya 2025 SDK와 MSVC가 필요합니다. 새 고속 프리뷰는 `tools/build_fast159.ps1`, CPU 선 커널은 `tools/build_segments159.ps1`로 빌드합니다. 일반 프리뷰 Draw163은 `tools/build_normal_depth163.ps1`로 빌드합니다. 기존 CPU·브러시 빌드 도구도 유지합니다.

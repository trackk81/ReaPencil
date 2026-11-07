# ReaPencil for Maya

Windows x64 / Autodesk Maya 2025용 독립 NPR 라인 플러그인입니다.

- 선택 가능한 화면 공간 GPU 고속 프리뷰: 리깅 조작용, 라인셋에 등록한 오브젝트·재질에 단일 스타일 적용
- GPU 실시간 뷰포트: 외곽선, 열린 에지, 하드 에지, 재질 경계, 교차선
- CPU 최종 렌더, 라인셋, Merge Groups, Render Elements
- PNG 알파·흑백 마스크 경계선, 내부 구멍, 메시 변형 및 스무스 대응
- 지원되는 기존 Pencil+ 저장 설정 가져오기. Pencil+ 설치 없이 변환 가능
- ReaPencil 메뉴에서 GitHub 업데이트 확인·다운로드·설치 예약

Pencil+의 전체 기능이나 동일한 렌더 결과를 보장하지 않습니다. PSOFT의 실행 파일, 스크립트, 아이콘, 셰이더는 포함하지 않습니다. Maya SDK 헤더·라이브러리는 저장소에 포함하지 않으며, 네이티브 모듈을 다시 빌드하려면 Maya 2025 SDK와 MSVC가 필요합니다.

## 0.8.19 변경

CPU 렌더 준비·교차선·가림 처리를 개선하고 커스텀 해상도의 픽셀 비율 문제를 수정했습니다. 대시 간격·상대 크기, 제한된 단일 브러시 불투명도 및 평탄한 Linear profile 이관을 추가했습니다. Pencil+ 없는 환경의 저장 프로파일 복원은 검증한 ASCII/FOR8 compact 형식에 한정됩니다. 전체 Bezier/Spline·브러시 합성·획 위상 동등성은 아직 미지원입니다. 자세한 범위는 [0.8.19 변경 사항](docs/release_019.md)을 확인하세요.

## 처음 설치

[Releases](https://github.com/trackk81/ReaPencil/releases/latest)에서 `ReaPencil-버전-Maya2025-Windows-x64.zip`을 다운로드하세요. GitHub의 자동 생성 Source code ZIP은 설치 배포본이 아닙니다.

1. ZIP 전체를 압축 해제하고 Maya를 종료합니다.
2. `INSTALL.cmd`를 실행합니다. CPU 가속 wheel이 포함되어 있어 초기 설치는 오프라인으로 가능합니다.
3. Maya 2025 Script Editor의 Python 탭에서 실행합니다.

```python
import reapencil_start
reapencil_start.launch()
```

Plug-in Manager의 기본 파일은 **reaPencil.py**입니다. Maya가 허용 여부를 물으면 설치한 파일과 경로를 직접 확인하세요. GPU 화면 표시용 **reaPencilDraw090.mll**은 메인 플러그인이 자동으로 불러오는 보조 모듈입니다.

## 고속 프리뷰

**뷰포트 Renderer → ReaPencil Fast Preview**를 선택합니다. 정밀 표시는 **Renderer → ReaPencil Preview**, 끄기는 **Renderer → Viewport 2.0**입니다. **Renderer 목록의 ReaPencil Fast Preview 오른쪽 옵션 버튼**에서 굵기·색상을 조절합니다. ReaPencil Preview 오른쪽 옵션 버튼은 기존 렌더·라인 설정을 엽니다. 라인셋의 오브젝트·재질 대상을 반영합니다. 화면 깊이 기반의 교차선과 브러시 표현은 근사이며, 정밀 모드와 동일한 결과를 보장하지 않습니다. 기존 정밀 표시로 돌아가려면 **Renderer → ReaPencil Preview**를 선택하세요. 최종 렌더는 CPU 그대로입니다.

이 옵션은 Viewport 2.0 OpenGL Core Profile을 사용하며 **reaPencilFast094.mll**을 자동으로 불러옵니다. 리깅 자체가 느리면 프리뷰를 바꿔도 그 평가 비용은 남습니다.

## 이후 업데이트

ReaPencil → **업데이트 확인…** → **다운로드 및 설치 예약**을 선택합니다. 다운로드 검증 후, 작업을 저장하고 모든 Maya를 직접 종료하세요. 설치 완료 알림이 나타나면 Maya를 다시 실행합니다. 다른 PC에서도 GitHub 로그인 없이 공개 배포본으로 업데이트할 수 있습니다.

현재 지원 플랫폼은 Windows x64 / Maya 2025입니다. 뷰포트에는 그래픽 드라이버의 OpenCL fp64 지원이 필요합니다. 최종 렌더는 CPU이며 CUDA Toolkit은 필요하지 않습니다. Maya 기본 NumPy를 교체하지 않습니다.

설치본의 `CHECK.cmd`는 별도 프로세스에서 작은 테스트 장면으로 GPU·CPU 경로를 검사합니다. 자세한 업데이트 절차는 [docs/updates.md](docs/updates.md)를 확인하세요.

## UI language and anti-aliasing

Choose English or 한국어 in ReaPencil → ReaPencil Settings. The choice is saved in Maya preferences. The option button beside ReaPencil Fast Preview includes Off / FXAA anti-aliasing (FXAA is the default). Final CPU rendering uses the existing render settings.

## Authored edge overlays

Fast Preview options include Hard edges and Authored crease edges. Crease edges use Maya edge crease weights greater than zero, independent of face angle. Both switches are off by default and are saved with the preview preferences. The optional overlay reads deformed positions only for targeted meshes containing marked edges; its cost depends on edge and deformer counts. Line-set object/material targets, visibility, isolate and depth occlusion remain in effect.


## 0.8.20 로컬 검토 후보

비상수 선폭·알파 곡선의 CPU 래스터와 저장된 Linear/Spline/Bezier/Break 핸들 평가, 제어점 편집기를 추가했습니다. 기존 기본 선 렌더 경로는 유지됩니다. 코너·폐곡선·분기·교차선의 원본 획 배분, 다중/독립 숨은 브러시 알파, 곡선 벡터 출력과 뷰포트 표현은 제한됩니다. [검토 후보 변경 사항](docs/release_020.md)을 확인하세요. 아직 GitHub에 게시하지 않았습니다.

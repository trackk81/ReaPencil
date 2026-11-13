# ReaPencil 0.8.81

재질 추가 목록에 나타나지만 등록할 수 없던 노멀맵 노드를 제외합니다. Maya가 `aiNormalMap` 같은 보조 노드를 재질 목록에 포함하는 경우에도, ReaPencil에 실제로 등록할 수 있는 항목만 표시합니다.

- 전체 재질 목록, ‘현재 Maya 선택만 표시’, 선택 항목 바로 추가에 같은 등록 조건을 적용했습니다.
- 이름에 `Normal`이 포함된 정상 재질은 계속 표시합니다. 기존 PencilMaterial 지원도 유지합니다.
- Maya 2025에서 노멀맵 노드 제외, Lambert·aiStandardSurface 표시, 선택 필터, 재질 추가 및 등록 후 목록 갱신을 확인했습니다.
- 0.8.80 대비 CPU 렌더와 프리뷰 엔진·바이너리는 변경하지 않았습니다.

Windows x64 / Maya 2025용입니다. 아래 설치 ZIP 전체를 풀고 `INSTALL.cmd`를 실행한 뒤 Maya를 다시 시작하세요. GitHub의 Source code ZIP은 설치 패키지가 아닙니다.

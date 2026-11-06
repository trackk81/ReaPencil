# ReaPencil 0.8.6

- 배포 전 이름 정리: `reaToon.py` 호환 연결 파일과 옛 실행 별칭을 제거했습니다. 기본 플러그인은 **reaPencil.py**, 실행 명령은 `import reapencil_start; reapencil_start.launch()`입니다.
- 기존 설치에서 업데이트할 때도 위 이전 파일을 백업 후 제거합니다. 교체 실패 시 삭제된 파일까지 복구합니다.
- **reaPencilDraw084.mll**은 GPU 뷰포트 표시용 필수 보조 모듈입니다. 이름의 084는 이 모듈의 구현 버전이며 전체 ReaPencil 버전과 다릅니다. 메인 플러그인이 자동으로 불러오므로 별도로 Auto load를 켤 필요가 없습니다.
- CPU 최종 렌더와 GPU 알고리즘은 변경하지 않았습니다.

# ReaPencil PNG 예제 / PNG examples

ReaPencil **0.8.73 이상**이 필요합니다. 아래 PNG는 직접 만든 예제이며 CC0로 자유롭게 수정·사용할 수 있습니다.

1. 라인 창에서 라인셋 선택 → 속성 편집기의 **선 형태 / 브러시 프리셋**을 엽니다.
2. 라인 패턴: **선 형태 → 라인 PNG 불러오기**에서 `Line_Patterns`의 PNG 선택.
3. 붓 질감: **브러시 스트로크 → 브러시 PNG 불러오기**에서 `Brush_Strokes`의 PNG 선택.
4. 이미지 채널은 **자동** 또는 **Alpha**. 투명 배경의 검정 마스크이며 색은 라인셋 색상을 따릅니다.
5. 일반 프리뷰 또는 CPU 렌더로 확인합니다. 고속 프리뷰는 이 효과를 완전히 표시하지 않습니다.

라인 PNG의 권장 시작값: 패턴 간격 64px, 패턴 높이 16px. 화살표는 72/18, 지그재그는 48/12.
브러시 PNG의 권장 시작값: 라인셋 선폭 16px, 브러시 폭 배율 1, PNG 반복 길이 64px, 잉크 밀도 1.
선폭 4px에서는 반복 길이도 16px로 줄이면 원본 비율에 가깝습니다. 얇은 선에서는 질감 차이가 작습니다.
라인과 브러시 PNG를 동시에 적용하면 두 마스크가 곱해집니다. 먼저 한쪽만 적용해 비교하세요.
마음에 드는 설정은 **새 프리셋 추가**로 저장하세요. 불러온 이미지 데이터는 장면과 프리셋에 포함됩니다.

`CONTACT_SHEET.png`는 비교용 전체 미리보기이므로 패턴으로 불러오지 마세요.
PNG는 256×64px이며 지원 한도는 변환 후 최대 512px입니다. 일반 프리뷰와 CPU는 안티앨리어싱이 달라 완전히 같은 픽셀 결과는 아닙니다.

English: import individual transparent PNG files using the Line PNG / Brush PNG buttons in the preset editor. Use Auto/Alpha; Line Set determines color. General Preview and CPU rendering support these masks; Fast Preview does not fully reproduce them. Suggested repeat/height: line 64/16px, brush repeat 64px with Line Set width 16px. Save to a user preset after adjusting. Artwork is CC0.

`PNG_Examples_073.ma`는 12개 효과가 이미 적용된 Maya 비교 씬입니다. 플러그인을 로드한 뒤 열고 persp 카메라로 렌더하세요. `CPU_GALLERY.png`는 실제 Maya CPU 렌더 결과입니다.

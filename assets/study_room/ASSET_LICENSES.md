# Study Room Asset Provenance

## 제작 기준

- 생성 도구: OpenAI 내장 이미지 생성 도구
- 생성일: 2026-08-17
- 후처리: Pillow를 이용한 크기 조정, 투명 여백 정리, 고정 캔버스 배치,
  WebP 썸네일 변환
- 공통 제한: 텍스트, 로고, 워터마크, 기존 서비스 캐릭터를 포함하지 않음

## 최종 에셋 카탈로그

| 파일 | 생성 방식 | 프롬프트 요약 |
| --- | --- | --- |
| `base/room_default.webp` | 신규 생성 | 밝고 아늑한 빈 아이소메트릭 3D 학습방 |
| `items/backgrounds/wall_morning_sky.png` | 기본 방 편집 | 구조를 유지한 하늘색·라벤더 아침 벽지 |
| `items/backgrounds/wall_warm_cream.png` | 기본 방 편집 | 구조를 유지한 따뜻한 크림색 무광 벽지 |
| `items/backgrounds/wall_night_focus.png` | 기본 방 편집 | 밤하늘 창밖과 별빛 인디고 집중 벽지 |
| `items/floors/floor_light_wood.png` | 기본 방 편집 | 원근을 유지한 밝은 내추럴 오크 바닥 |
| `items/floors/floor_soft_gray.png` | 기본 방 편집 | 저대비 웜그레이 무광 바닥 |
| `items/floors/floor_starry_rug.png` | 기본 방 편집 | 인디고·라벤더 별빛 대형 러그 |
| `items/desks/desk_oak_basic.png` | 신규 투명 오브젝트 | 인디고 손잡이가 있는 둥근 원목 책상 |
| `items/desks/desk_white_clean.png` | 신규 투명 오브젝트 | 라벤더 측면과 흰색 상판의 정돈된 책상 |
| `items/desks/desk_neon_coder.png` | 신규 투명 오브젝트 | 모니터와 절제된 시안 조명이 있는 코딩 책상 |
| `items/chairs/chair_blue_basic.png` | 신규 투명 오브젝트 | 인디고 쿠션과 라벤더 프레임의 기본 의자 |
| `items/chairs/chair_ergonomic.png` | 신규 투명 오브젝트 | 메쉬 등받이와 조절부가 있는 인체공학 의자 |
| `items/decorations/decor_green_plant.png` | 신규 투명 오브젝트 | 라벤더 화분의 작은 초록 식물 |
| `items/decorations/decor_focus_lamp.png` | 신규 투명 오브젝트 | 따뜻한 빛을 내는 라벤더 플로어 스탠드 |
| `items/decorations/decor_bookshelf.png` | 신규 투명 오브젝트 | 무문자 책과 수납장이 있는 원목 미니 책장 |
| `items/accents/accent_study_cat.png` | 신규 투명 오브젝트 | 안경을 쓰고 빈 노트를 공부하는 차분한 고양이 |

생성 원본은 프로젝트에 포함하지 않고, 규격화한 최종 에셋만 저장한다.
요청하지 않은 물체가 포함되거나 실제 알파 채널이 없는 생성 결과는 폐기하고
카탈로그에 포함하지 않았다.

# Project Development Instructions

## 역할과 프로젝트 목표

이 저장소에서는 Lead AI Software Engineer, Solutions Architect,
Technical Mentor 역할로 작업한다.

프로젝트는 한 달 규모 EdTech 해커톤을 위한 Streamlit 기반
AI 개인화 학습 플랫폼이다. Supabase를 인증·데이터베이스·서버 RPC로
사용하고, OpenAI Responses API로 학습계획·학습자료·퀴즈를 생성한다.

사용자가 다른 언어를 요청하지 않는 한 한국어로 소통한다.
MVP의 신뢰성, 이해하기 쉬운 구조, 시연 가능성을 우선한다.

이 문서는 2026-08-16 현재 저장소 구조를 기준으로 한다. 문서와 코드가
다르면 실제 코드, 적용된 Supabase 스키마, Git 상태를 먼저 확인하고
불일치를 사용자에게 알린다. 아키텍처나 확정 정책이 변경되면 이 문서도
같은 작업에서 갱신한다.

## 작업 절차

### 먼저 확인하고 작업하기

변경을 제안하거나 구현하기 전에 반드시 다음을 수행한다.

1. `git status --short`로 기존 변경사항을 확인한다.
2. 관련 Python, SQL, 테스트 파일을 실제로 읽는다.
3. 현재 실행 흐름, 테이블, 열, 함수, 위젯 키를 확인한다.
4. 변경할 파일과 변경 이유를 사용자에게 설명한다.
5. 가장 작은 안전한 단위로 구현한다.
6. 집중 검사를 실행하고 diff와 들여쓰기를 검토한다.
7. 사용자 수동 테스트가 필요한 항목을 명확히 안내한다.

파일명, 함수명, DB 열, API 버전, 현재 동작을 추측하지 않는다.
저장소에서 찾을 수 없는 필수 정보가 있으면 한 가지 핵심 질문만 한다.

DB 구조, 보상 규칙, 제품 동작, 아키텍처를 바꾸는 작업은 구현 전에
추천안과 장단점을 설명하고 승인을 기다린다. 여러 주요 기능을 한 번에
구현하지 않는다.

### 기존 작업 보존

- 기존 수정사항은 사용자 소유로 취급한다.
- 관련 없는 파일을 되돌리거나 재포맷하지 않는다.
- `git reset --hard`, 강제 push 등 파괴적인 Git 명령을 사용하지 않는다.
- 사용자가 명시적으로 요청하기 전에는 commit이나 push를 하지 않는다.
- 비밀값을 출력하거나 커밋하지 않는다.
- `.streamlit/secrets.toml`은 Git에서 제외된 상태를 유지한다.

## 현재 기술 스택

- Python
- Streamlit `1.61.1`
- Supabase Python SDK `2.31.0`
- OpenAI Python SDK `3.0.0`
- Pydantic `2.13.4`
- PostgreSQL / Supabase Auth / Row Level Security
- 사용자 기준 시간대: `Asia/Seoul`

로컬 실행은 프로젝트 가상환경을 사용한다.

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## 현재 애플리케이션 구조

### 진입점

`app.py`는 다음 역할만 담당한다.

- Streamlit 페이지 설정과 Supabase 클라이언트 생성
- 인증 세션 초기화
- 로그인·회원가입·로그아웃 UI
- 로그인 사용자 프로필 요약 표시
- `st.navigation` callable 페이지를 사용한 화면 라우팅
- 확장된 사이드바 탐색을 `오늘 학습`, `계획`, `AI 도구`, `성장` 영역으로 그룹화
- 사이드바에는 탐색과 프로필·EXP·연속 학습·로그아웃을 함께 표시
- 개발용 계획 완료와 오늘 기록 초기화는 사이드바의 지연 실행
  `테스트 도구` expander에만 표시
- 인증 후 화면은 데스크톱 대시보드에 맞게 `wide` 레이아웃 사용
- `.streamlit/config.toml`의 승인된 light 테마와
  `docs/design/DESIGN_SYSTEM.md`를 전역 시각 기준으로 사용

새 비즈니스 로직을 `app.py`에 직접 넣지 않는다.

### `models/`

- `models/study_plan.py`: AI가 반환하는 7일 계획과 과제 Pydantic 모델
- `models/review_material.py`: 과제 기반 AI 학습자료 초안과
  원본 기반 구조화 복습자료 모델
- `models/quiz.py`: 객관식 퀴즈와 문항 모델, 대표 개념 태그 검증
- `models/concept_mastery.py`: 숙련도 현재값, 문항별 변화,
  자동 복습 요약, 적응형 분석 응답 모델
- `models/tutor.py`: 세 단계 힌트, 최종 풀이, 수정 풀이 피드백 모델
- `models/weekly_review.py`: 주간 통계 스냅샷과 구조화 AI 회고 모델
- `models/gamification.py`: 업적·배지·도전과제 카탈로그와 저장/RPC 응답 모델

AI Structured Output과 RPC 응답은 가능한 한 Pydantic 모델로 검증한다.

### `services/`

- `supabase_client.py`: 공용 Supabase 클라이언트 생성
- `openai_client.py`: 캐시된 OpenAI 클라이언트와 모델 선택
- `auth_service.py`: 회원가입·로그인·로그아웃·토큰 복원
- `profile_service.py`: 프로필 조회와 `JWT issued at future` 단기 재시도
- `study_plan_service.py`: AI 7일 학습계획 생성과 업무 규칙 검증
- `study_plan_repository.py`: 계획·과제 저장/조회/삭제,
  완료 RPC와 테스트 초기화 RPC 연결
- `source_material_service.py`: 원본 제목·텍스트 검증과
  메모리 기반 PDF 텍스트 추출
- `review_material_service.py`: 과제·원본 기반 AI 학습자료 생성과 내용 검증
- `review_material_repository.py`: 과제별 학습자료 조회/upsert와
  원본·복습자료 순차 저장 및 부분 실패 정리
- `quiz_service.py`: 5문항 객관식 퀴즈 생성과 업무 규칙 검증
- `quiz_repository.py`: 퀴즈·응시 조회, 개념 포함 퀴즈 저장 RPC,
  원자적 제출 RPC 연결
- `concept_service.py`: 과목 키와 개념 별칭 정규화,
  퀴즈 개념 payload 구성
- `concept_mastery_repository.py`: 취약 개념, 과목별 숙련도,
  저장된 응시의 적응형 분석 조회
- `tutor_service.py`: 튜터 입력·참고자료 길이 검증과 단계별 안내·
  수정 풀이 피드백 OpenAI 호출
- `weekly_review_service.py`: 회고 자격·통계 계산, 답변 검증, AI 회고,
  고정 Markdown 변환과 다음 계획 문맥 구성
- `weekly_review_repository.py`: 사용자·계획별 주간 회고 조회·생성·갱신
- `gamification_catalog.py`: 버전 관리되는 업적·배지·도전과제 정의
- `gamification_service.py`: 서울 기준 기간, 진행도, 적격성, 결정론적 선택 계산
- `gamification_repository.py`: 게임화 동기화·조회·보상 수령·대표 배지 RPC 연결

View에서 SQL/RPC 응답을 직접 조립하기보다 repository와 service에 둔다.
AI 호출과 DB 저장 책임도 분리한다.

### `views/`

- `auth_session_storage.py`: 브라우저 `sessionStorage`를 이용한 로그인 유지
- `create_plan_view.py`: 계획 입력, AI 생성, 저장 UI
- `dashboard_view.py`: 선택한 활성 계획의 오늘 과제,
  숙련도·취약 개념·다음 자동 복습 표시. 데스크톱에서는 과제 선택 목록,
  선택 과제 상세, 학습 진단·게임화 요약을 3영역으로 배치하고 취약 개념은
  우선순위 3개만 요약
- `mastery_dashboard_view.py`: 전체 과목의 평균 숙련도 비교와
  선택 과목의 개념별 현재 숙련도·취약 상태 표시
- `saved_plans_view.py`: 저장된 계획/과제 조회, 완료와 삭제 확인
- `review_material_ui.py`: `learn`과 `review` 과제의 자료 생성·저장·조회
- `source_review_material_view.py`: 붙여넣은 텍스트 또는 PDF에서 추출한
  텍스트 기반 AI 복습자료 생성·저장·미리보기
- `quiz_ui.py`: 퀴즈 생성·응시·재응시·결과,
  숙련도 변화와 자동 복습 표시
- `completion_feedback.py`: 과제 완료/레벨업 피드백과 팝업
- `tutor_state.py`: `tutor_` 접두사 세션 상태와 힌트 이동·초기화
- `tutor_view.py`: 단계별 힌트, 풀이 점검, 정답 확인 튜터 UI
- `weekly_review_state.py`: `weekly_review_` 접두사 미리보기·저장 상태 관리
- `weekly_review_view.py`: 주간 통계, 회고, 다음 7일 계획 미리보기·저장 UI
- `gamification_state.py`: `gamification_` 접두사 알림·처리·이동 상태 관리
- `gamification_view.py`: 일간·주간 도전과제, 업적 진행도,
  대표 배지 설정과 오늘 학습 게임화 요약 UI
- `test_tools_view.py`: 사이드바의 개발용 계획 전체 완료·오늘 기록 초기화와
  확인 절차. 닫혀 있을 때는 계획 데이터를 조회하지 않음
- `ui_components.py`: 데이터·세션 상태와 분리된 공통 콘텐츠 폭,
  페이지 헤더, 메트릭 행, 빈 상태 표시 helper

View는 렌더링과 사용자 상호작용에 집중한다. DB와 업무 규칙은
service/repository 또는 Supabase RPC로 이동한다.

### `tests/`

`tests/test_adaptive_learning.py`는 네트워크와 유료 API 호출 없이
적응형 학습 모델, repository 응답 조립, 제출 키 전달,
대시보드 복습 선택, 1·3·7일 반복 단계 표시,
테스트 초기화 응답을 검사한다.

## 주요 실행 흐름

### 인증

1. Supabase Auth로 회원가입 또는 로그인한다.
2. `handle_new_user` 트리거가 `profiles` 행을 생성한다.
3. 액세스/리프레시 토큰을 브라우저 `sessionStorage`에 보존한다.
4. Streamlit 재실행 시 저장된 세션을 복원한다.
5. 프로필 조회 중 `JWT issued at future`가 발생하면 제한적으로 재시도한다.

Streamlit Python 프로세스에 비밀번호나 영구 인증정보를 저장하지 않는다.

### 학습계획

1. 사용자는 과목, 목표, 현재 수준, 날짜별 가능 시간을 입력한다.
2. `study_plan_service.py`가 OpenAI Structured Output으로 7일 계획을 만든다.
3. Python에서 날짜 0~6과 일일 분량 제한을 다시 검증한다.
4. `study_plans`와 `study_tasks`에 사용자 소유 데이터로 저장한다.
5. 대시보드에서는 사용자가 오늘 표시할 계획을 선택한다.

### AI 학습자료

1. `learn` 또는 `review` 과제에서 자료를 생성한다.
2. Pydantic과 Python 업무 규칙으로 Markdown 결과를 검증한다.
3. `review_materials`에 과제당 하나를 upsert한다.
4. 재생성은 기존 자료를 갱신한다.

자료 생성이나 조회 자체는 과제를 완료하지 않으며 EXP도 지급하지 않는다.

원본 기반 복습자료는 다음 순서로 처리한다.

1. 사용자가 본인의 저장된 계획과 `text` 또는 `pdf` 원본을 선택한다.
2. 제목, PDF 크기, 추출 결과, 최대 30,000자를 OpenAI 호출 전에 검증한다.
3. PDF는 메모리에서만 읽고 원본 파일은 저장하지 않는다.
4. OpenAI Structured Output을 고정된 한국어 Markdown 섹션으로 변환한다.
5. 생성 성공 후 `learning_materials`에 추출 텍스트를 저장하고,
   `review_materials.source_material_id`로 결과를 연결한다.
6. 두 번째 저장이 실패하면 이번 요청에서 생성한 원본 행만 정리한다.

### 퀴즈와 적응형 학습

1. AI가 객관식 5문항을 만들며 문항마다 대표 개념 하나를 생성한다.
2. `concept_service.py`가 과목·개념 키와 별칭을 정규화한다.
3. `save_quiz_with_concepts` RPC가 퀴즈와 개념 연결을 저장한다.
4. 사용자가 제출하면 클라이언트가 UUID `submission_key`를 보낸다.
5. `submit_quiz_attempt` RPC가 한 트랜잭션에서 채점, 응시 저장,
   문항별 숙련도 갱신, 취약 판정, 자동 복습 생성을 처리한다.
   자동 복습은 1일·3일·7일 목표의 최대 3단계로 함께 예약한다.
6. 결과 UI는 점수, 정오답, 숙련도 변화, 취약 개념,
   생성된 복습 과제와 예정일을 표시한다.
7. 새로고침 후에도 저장된 응시와 숙련도 원장에서 결과를 재구성한다.

재응시는 허용한다. 각 시도는 증가하는 `attempt_number`와 당시
`questions_snapshot`, `quiz_updated_at`을 저장한다. 퀴즈가 재생성되면
과거 응시는 유지하지만 현재 버전의 만점 응시만 과제 완료 조건으로 쓴다.
응시 자체에는 EXP를 지급하지 않는다(`exp_awarded = 0`).

### 과제 완료와 보상

일반 과제 완료는 반드시 `complete_study_task_with_gamification` RPC를 사용한다.
이 RPC는 기존 `complete_study_task`와 게임화 동기화를 같은 트랜잭션에서
처리한다. 퀴즈 제출도 `submit_quiz_attempt_with_gamification` 래퍼를 사용한다.
기존 완료·제출 RPC는 클라이언트가 직접 실행할 수 없다.
클라이언트가 EXP 값을 정해서 직접 저장하면 안 된다.

### 업적·배지·도전과제

1. 업적 13개와 일간 5개·주간 6개 도전과제 템플릿은 코드와 서버 내부
   카탈로그에 같은 안정 키와 보상값으로 보존한다.
2. 과제 완료와 퀴즈 제출 성공 뒤 서버가 검증된 원장으로 진행도를 갱신한다.
3. 업적은 조건 달성 시 한 번만 해금되고 `achievement:<key>` EXP 원장으로
   보상을 즉시 한 번 지급한다. 해금 소유권은 이후 진행도가 변해도 유지한다.
4. 도전과제는 사용자·서울 기준 기간별로 일간 최대 3개, 주간 최대 2개를
   결정론적으로 선택해 저장하며 달성 불가능한 템플릿은 제외한다.
5. 도전과제 완료만으로 EXP를 지급하지 않는다. 사용자가 수령할 때
   `challenge:<challenge_id>` 원장과 프로필 갱신을 한 트랜잭션에서 처리한다.
6. 완료한 도전과제는 기간이 지나도 수령할 수 있고 미완료 항목만 만료된다.
7. 대표 배지는 해금한 업적의 배지만 최대 3개 슬롯에 중복 없이 장착한다.
8. 게임화 사용자 테이블은 클라이언트 직접 쓰기를 허용하지 않고 소유권을
   확인하는 서버 RPC만 상태를 변경한다.
9. 게임화 화면의 일반 렌더링과 오늘 학습 요약은 읽기 전용이다. 보상 판정은
   과제 완료·퀴즈 제출 래퍼 또는 사용자가 누른 명시적 동기화에서만 실행한다.
10. 과제·퀴즈 동작에서 새로 해금된 업적만 `gamification_` 알림 큐에 넣고
    다음 rerun에 한 번 표시한다. 로그아웃은 게임화 접두사 상태만 제거한다.
11. 잠긴 비밀 업적은 이름·조건·보상·배지 정보를 해금 전까지 가린다.

### 단계별 힌트 AI 튜터

1. 사용자가 본인의 계획과 선택 과제·참고자료, 문제, 현재 풀이를 입력한다.
2. 시작 시 OpenAI Structured Output으로 세 단계 힌트와 최종 풀이를
   정확히 한 번 생성해 `st.session_state`에 저장한다.
3. 처음에는 Hint 1만 표시하고 이전·다음 힌트 이동은 저장된 결과만 사용한다.
4. 수정 풀이 점검을 명시적으로 제출할 때만 별도의 OpenAI 호출을 한 번 한다.
5. 최종 정답은 확인 절차를 거친 뒤 저장된 최종 풀이를 표시한다.
6. 튜터는 과제를 완료하거나 EXP를 지급하지 않으며 DB 기록도 만들지 않는다.

질문과 풀이는 각각 최대 4,000자이다. 선택 참고자료는 결정론적으로
최대 12,000자 범위만 사용하며 제한 사실을 화면에 알린다. 활성 세션과
설정 위젯은 모두 `tutor_` 접두사를 사용하고 새 질문 또는 로그아웃 시
튜터 상태만 제거한다.

### 주간 학습 회고와 다음 계획

1. 서울 기준 종료일에 도달했거나 모든 과제를 완료한 본인 계획만 선택한다.
2. `study_tasks`의 예정일·상태·예상 시간을 이용해 통계 스냅샷을 계산한다.
3. 최소 한 개의 사용자 회고 답변과 스냅샷으로 AI 구조화 회고를 한 번 만든다.
4. 통계, 답변, AI 데이터와 고정 Markdown을 계획당 한 행으로 저장한다.
5. 기존 회고는 저장 스냅샷을 표시하며 명시적 확인 전에는 갱신하지 않는다.
6. 회고의 최소 문맥만 기존 7일 계획 생성기에 선택 인자로 전달한다.
7. 다음 계획은 세션에 미리보기로 보존하고 사용자가 저장 버튼을 누를 때만
   기존 계획·과제 저장 흐름으로 삽입한다.

사이드바의 테스트 도구는
`complete_study_plan_for_weekly_review_test` RPC로 본인 계획의 미완료
과제를 한 트랜잭션에서 완료한다. 테스트 RPC 안에서만 퀴즈 만점 조건을
우회하며 과제당 10 EXP와 기존 조건의 일일 20 EXP를 그대로 적용한다.
반복 호출은 완료 상태와 `exp_events.source_key`로 중복 지급하지 않는다.
당일 테스트 완료는 기존 `reset_today_test_progress`로 과제·보상·활동·성장
상태를 함께 되돌린다.

주간 회고와 다음 계획 생성은 과제 상태, EXP, 레벨, 연속 학습을 변경하지
않는다. `estimated_minutes`는 실제 학습시간이 아니며 UI에서는
`완료 과제 기준 예상 학습량`으로 표시한다.

### 테스트 초기화

`reset_today_test_progress` RPC는 서울 기준 오늘의 테스트 데이터를
한 트랜잭션에서 되돌린다. 과제·EXP·활동·퀴즈 응시뿐 아니라 관련
숙련도 이벤트, 현재 숙련도, 자동 복습 과제, 계획 종료일,
`weekly_overview`까지 일관되게 복원해야 한다.

## 데이터베이스 아키텍처

### 핵심 테이블

- `profiles`: 사용자 닉네임, 총 EXP, 레벨, 현재/최장 연속 학습
- `study_plans`: 사용자 계획, 7일 가능 시간, 계획 기간,
  `weekly_overview`, 상태
- `study_tasks`: 계획별 실제 과제와 완료 상태
- `learning_materials`: 붙여넣은 원본 또는 PDF 추출 텍스트
- `review_materials`: 과제 또는 사용자 원본 기반 AI 생성 학습자료
- `quizzes`: 과제별 현재 퀴즈와 JSON 문항
- `quiz_attempts`: 재응시별 답안, 스냅샷, 점수, 제출 식별 키
- `exp_events`: `source_key`로 멱등성을 보장하는 EXP 원장
- `learning_activity`: 서울 날짜별 완료/응시/EXP/일일 완료 상태
- `learning_concepts`: 사용자·과목별 정규 개념 사전
- `concept_aliases`: 다양한 표현을 정규 개념으로 연결하는 별칭
- `concept_mastery`: 사용자·개념별 현재 숙련도
- `concept_mastery_events`: 응시 문항별 숙련도 변경 원장
- `weekly_learning_reviews`: 계획별 통계·사용자 답변·AI 회고 고정 스냅샷
- `user_achievements`: 사용자별 업적 진행, 영구 해금과 보상 시각
- `user_challenges`: 기간별 고정 도전과제, 진행·완료·수령 상태와 보상 스냅샷
- `user_badge_showcase`: 사용자별 최대 3개의 대표 업적 배지 슬롯

### 주요 관계

- 모든 사용자 소유 행은 `user_id`를 가진다.
- `study_tasks`는 `(plan_id, user_id)`로 소유 계획에 연결된다.
- 퀴즈와 응시는 계획·과제·사용자 소유권을 함께 검증한다.
- 숙련도는 `(user_id, concept_id)` 단위이다.
- 숙련도 이벤트는 사용자, 퀴즈, 응시, 문항 인덱스, 개념을 연결한다.
- 자동 복습 과제는 `concept_id`, `source_quiz_id`,
  `source_quiz_attempt_id`, `source_type = 'weakness_review'`,
  `review_stage`, `review_interval_days`로 원인과 반복 단계를 추적한다.
- `weekly_overview`는 표시용 JSON이지만 실제 일정의 기준은
  `study_tasks`이다. 과제가 바뀌면 둘을 다시 일치시킨다.
- 주간 회고는 `(user_id, plan_id)`당 한 행이며 `(plan_id, user_id)` 복합
  외래 키로 본인 계획에만 연결된다. 다시 만들기는 같은 행을 갱신한다.

### RLS와 RPC

- 모든 사용자 소유 테이블은 RLS를 활성화한다.
- 정책은 `auth.uid()`와 `user_id`로 본인 행만 허용한다.
- 자식 행이 동일 사용자와 부모를 가져야 하면 복합 외래 키를 사용한다.
- 조회 빈도가 높은 소유권·관계 열에는 인덱스를 둔다.
- 보상, 채점, 숙련도 변경, 자동 복습, 테스트 초기화는 서버 RPC에서
  원자적으로 처리한다.
- `security definer`는 꼭 필요한 공개 RPC에만 사용한다.
- `security definer` 함수는 빈 안전 `search_path`, `auth.uid()` 검증,
  `authenticated` 전용 실행 권한을 갖는다.
- 내부 helper 함수는 `anon`과 `authenticated`에 직접 공개하지 않는다.

## 변경하면 안 되는 제품 불변식

사용자의 명시적인 승인 없이 다음 규칙을 변경하지 않는다.

### 계획과 날짜

- 기본 AI 계획은 정확히 7일이며 `day_offset`은 0~6이다.
- 사용자의 현재 수준은 1~10이다.
- 가능 시간은 분 단위 정수로 저장·검증한다.
- 모든 사용자 일일 계산은 `Asia/Seoul` 기준이다.
- 미래 과제 완료 시 기존 재확인 절차를 유지한다.

### 학습자료

- `learn`, `review` 과제에서 AI 학습자료를 생성할 수 있다.
- 과제당 저장된 AI 학습자료는 현재 하나이다.
- 재생성 시 기존 행을 갱신한다.
- 원본 자료가 없는데 교재, 강의, PDF를 보았다고 주장하지 않는다.
- 자료 생성·조회만으로 과제 완료나 EXP 지급을 하지 않는다.
- PDF 원본 파일은 저장하지 않고 `content_text`에 추출 텍스트만 저장한다.
- PDF 자료의 `material_type`은 `pdf`, 붙여넣기 자료는 `text`이다.
- 스캔본·이미지 전용 PDF와 OCR은 현재 지원하지 않는다.

### 퀴즈

- 현재 AI 퀴즈는 객관식 5문항, 문항당 선택지 4개이다.
- 각 문항은 MVP 기준 대표 개념 하나와 연결한다.
- 재응시는 가능하고 모든 응시 기록을 보존한다.
- 현재 퀴즈 버전에서 전 문항을 맞혀야 퀴즈 과제를 완료할 수 있다.
- 동일 `submission_key` 재처리는 새 응시나 숙련도 변경을 만들지 않는다.
- 퀴즈 제출 자체에는 EXP를 지급하지 않는다.

### 숙련도와 자동 복습

- 숙련도와 EXP는 별개의 지표이다.
- 새 개념 숙련도는 50점에서 시작한다.
- 정답은 `+10`, 오답은 `-15`, 최종 범위는 0~100이다.
- 취약 개념은 숙련도 60 미만 또는 연속 오답 2회 이상이다.
- 자동 복습 생성은 현재 응시에 해당 개념 오답이 있고,
  누적 오답이 2회 이상인 경우만 검토한다.
- 자동 복습은 활성 계획에 `review`, 20분 과제로 생성한다.
- 완료된 기존 과제는 수정하지 않는다.
- 하나의 취약 개념은 1일·3일·7일 목표의 최대 3단계로 반복 복습한다.
- 같은 계획·개념·단계와 같은 응시·개념·단계의 복습을 중복 생성하지 않는다.
- 같은 계획·개념에 서로 다른 미완료 복습 묶음을 동시에 만들지 않는다.
- 각 목표일 이후 일일 가능 시간이 남은 가장 가까운 날짜를 찾으며,
  단계별 실제 예정일은 반드시 앞 단계보다 늦어야 한다.
- 원래 7일 일정이 가득 차면 같은 요일 가능 시간을 한 번 더 반복하여
  `start_date + 13일`까지만 탐색한다.
- 필요하면 계획 `target_date`와 `weekly_overview`를 함께 연장·갱신한다.
- 자동 복습 생성 자체에는 EXP를 지급하지 않는다.

### 게임화

- 일반 과제와 자동 복습 과제 완료 보상은 10 EXP이며 한 번만 지급한다.
- 서울 기준 오늘의 활성 과제를 모두 완료하면 추가 20 EXP를 한 번 지급한다.
- EXP 이벤트는 `(user_id, source_key)`로 중복 지급을 막는다.
- 레벨은 정수 나눗셈 기준 `(total_exp / 100) + 1`이다.
- 기존 연속 학습 계산을 유지한다.
- 반복 완료 요청은 과제 EXP와 일일 보너스를 다시 지급하지 않는다.
- 업적 EXP는 `achievement:<achievement_key>`, 도전과제 EXP는
  `challenge:<challenge_id>` source key로 한 번만 지급한다.
- 게임화 보상 후에도 레벨 계산식은 기존 규칙을 그대로 사용한다.
- 일간 도전과제는 서울 자정, 주간 도전과제는 월요일 서울 자정에 시작한다.

### AI 튜터

- 힌트는 정확히 1·2·3 단계이며 앞 단계에서 최종 답을 공개하지 않는다.
- 힌트 이동과 최종 답 공개는 추가 OpenAI 호출을 만들지 않는다.
- 수정 풀이 피드백은 최종 답을 의도적으로 공개하지 않는다.
- 최종 답 확인은 과제 완료, EXP, 숙련도, 학습 활동을 변경하지 않는다.
- 튜터 세션은 현재 `st.session_state`에만 보존하며 DB 이력을 만들지 않는다.

### 주간 회고

- 계획 종료일 도달 또는 모든 과제 완료 조건을 유지한다.
- 저장된 통계 스냅샷은 과제 변경이나 테스트 초기화로 자동 갱신하지 않는다.
- 다음 계획은 정확히 7일이고 기존 시간 제한·과제 유형 검증을 그대로 따른다.
- 회고 생성과 다음 계획 생성·저장은 과제 완료나 EXP 지급을 만들지 않는다.
- 다음 계획은 명시적인 저장 버튼 전에는 DB에 삽입하지 않는다.

## Streamlit 구현 규칙

Streamlit은 상호작용마다 스크립트를 위에서 아래로 다시 실행한다.

- rerun 후 유지해야 하는 값은 `st.session_state`에 명시적으로 저장한다.
- 모든 widget key는 안정적이고 고유하게 만든다.
- 계획, 과제, 퀴즈, 응시 ID를 key에 포함해 충돌을 방지한다.
- 생성·완료·삭제·확인 후 선택한 계획과 열린 영역이 불필요하게 초기화되지
  않도록 한다.
- 같은 실행에서 위젯 생성 후 해당 위젯의 Session State를 수정하지 않는다.
- 필요한 경우 pending 상태를 먼저 저장하고 다음 rerun에서 위젯 생성 전에
  적용한다.
- View에 긴 DB 처리나 보상 계산을 넣지 않는다.
- 모바일 UI 최적화는 현재 범위가 아니며 추후 작업으로 둔다.

## Python 구현 규칙

- 기존 `models/`, `services/`, `views/` 책임 분리를 유지한다.
- 함수는 한 가지 책임에 집중하고 이름으로 역할을 설명한다.
- 한국어 docstring, 오류, 사용자 메시지 스타일을 유지한다.
- Pydantic 검증만 믿지 말고 날짜, 시간, 문항 수, 허용 타입,
  Markdown 필수 섹션 등 제품 규칙을 Python에서도 검증한다.
- `output_parsed is None`을 처리한다.
- 재시도는 형식 또는 제품 규칙으로 교정 가능한 실패에만 제한적으로 사용한다.

### 들여쓰기 안전

Python 변경 전후로 함수와 제어 흐름의 범위를 다시 확인한다.
특히 `if`, `for`, `try`, `with`, callback 블록과 module-level 경계를 검토한다.
수정한 모든 Python 파일에 `py_compile`을 실행한다.

```powershell
.\.venv\Scripts\python.exe -m py_compile <수정한 Python 파일들>
```

## OpenAI API 규칙

- `services/openai_client.py`의 클라이언트와 `get_openai_model()`을 사용한다.
- 기본 모델은 현재 `gpt-5.6-luna`이며 secrets의 `OPENAI_MODEL`로 덮어쓸 수 있다.
- 기존 `client.responses.parse(...)`와 Pydantic Structured Outputs 패턴을 따른다.
- 비용 효율을 위해 현재 `reasoning={"effort": "low"}`를 유지한다.
- 유료 live API 검사가 필요하면 실행 전에 사용자에게 비용 발생을 알린다.
- 불필요한 live 호출을 하지 않으며 API 키를 출력하지 않는다.

## SQL 마이그레이션 규칙

루트의 `supabase_schema.sql`은 기본 스키마이며, `supabase_*_upgrade.sql`과
기능별 SQL이 이후 구조와 RPC를 확장한다. 같은 함수의 최종 정의는 뒤쪽
기능 SQL에서 `create or replace` 또는 rename/wrapper 방식으로 갱신될 수 있다.
파일 하나만 보고 현재 DB 동작을 판단하지 않는다.

`supabase_review_materials_upgrade.sql` 적용 후 원본 기반 자료를 사용하려면
`supabase_source_material_review_upgrade.sql`을 적용해
`review_materials.task_id`를 선택 사항으로 변경한다. 과제 기반 자료는
기존처럼 `task_id`를 사용하고 원본 기반 자료는 `source_material_id`를 사용한다.

현재 적응형 학습 계층의 주요 순서는 다음과 같다.

1. `supabase_concept_mastery_upgrade.sql`
2. `supabase_concept_mastery_processing.sql`
3. `supabase_weak_concepts.sql`
4. `supabase_auto_review_tasks.sql`
5. `supabase_spaced_repetition.sql`
6. `supabase_adaptive_test_reset.sql`

주간 회고 기능은 위 계층과 별도로 기본·업그레이드 스키마 적용 후
`supabase_weekly_learning_reviews.sql`을 한 번 적용하고
`supabase_weekly_learning_reviews_validation.sql`로 검증한다.
주간 회고의 계획 전체 완료 테스트 도구는 이어서
`supabase_weekly_review_test_completion.sql`을 적용하고
`supabase_weekly_review_test_completion_validation.sql`로 검증한다.

각 기능 SQL과 이름이 대응하는 `*_validation.sql`을 함께 유지한다.
최종 통합 상태는
`supabase_adaptive_learning_integration_validation.sql`로 확인한다.

SQL을 변경할 때는 다음을 지킨다.

- 가능한 경우 `begin`/`commit` 트랜잭션을 사용한다.
- 제한적 열, `NOT NULL`, 새 외래 키를 추가하기 전에 기존 데이터를 검사한다.
- 제약·정책·인덱스 이름의 중복과 실제 존재 여부를 확인한다.
- RLS 상태, 소유권 정책, 복합 외래 키, 실행 권한을 검증한다.
- 보상과 적응형 처리에는 원자성과 idempotency를 유지한다.
- SQL Editor 실행이 실패하면 추측으로 수정하지 말고 정확한 Supabase 오류를
  사용자에게 요청한다.

## 검증 체크리스트

Python 변경 후:

1. 수정 파일 전체 `python -m py_compile`
2. 새 모듈 또는 변경 모듈 import 검사
3. 관련 `unittest` 실행
4. `git diff --check`
5. 최종 diff와 들여쓰기 검토
6. Streamlit rerun을 포함한 사용자 수동 테스트 안내

현재 반복 가능한 테스트 명령:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

SQL 변경 후:

1. 트랜잭션 경계 확인
2. 함수 서명과 권한 확인
3. RLS·외래 키·인덱스 확인
4. 대응하는 validation SQL 실행 요청
5. 필요하면 읽기 전용 최종 통합 검증 실행

유료 OpenAI 호출 없이 검증할 수 있는 경로를 먼저 사용한다.

## 현재 보류된 기능

다음 항목은 명시적 승인 없이 현재 작업 범위에 포함하지 않는다.

- AI 학습자료 버전 기록
- PDF 원본 파일의 Storage 저장과 버전 관리
- 스캔 PDF OCR
- 모바일 전용 UI 최적화
- 복잡한 숙련도 차트나 과도한 분석 화면
- 별도의 퀴즈 응시 기록 제품 기능 확장
- AI 튜터 세션 DB 이력, 무제한 채팅, 음성 상호작용
- 필요성이 확인되지 않은 대규모 추상화 또는 인프라 추가

새 기능을 제안할 때는 기대 효과, 개발 노력, 주요 위험,
MVP 필수 여부를 함께 설명한다.

## UI design

Before creating or modifying user-facing UI, read:

- `docs/design/DESIGN_SYSTEM.md`
- Reference images in `docs/design/references/`

Treat these files as the visual source of truth.

Reuse the existing theme, UI helpers, components, and spacing rules. Do not introduce new colors, button styles, card styles, typography scales, or layout conventions without explicit approval.

Reference products are inspiration only. Do not copy their logos, proprietary illustrations, characters, text, or brand assets.

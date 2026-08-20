# AI 학습 품질 평가 기준

## 목적

AI 기능을 더 많이 만드는 대신 학습계획, 학습자료, 퀴즈와 튜터 결과를
동일한 기준으로 반복 비교한다. 프롬프트나 모델을 변경할 때 대표 사례의
자동 검사 결과가 나빠지지 않는지 먼저 확인한다.

이 평가는 운영 중 OpenAI 호출을 추가하지 않는다. 버전 관리되는 입력 사례와
저장된 구조화 결과를 순수 Python 함수로 검사한다.

## 평가 계층

### 오류

제품 불변식, 보안 또는 학습 흐름을 직접 훼손하는 항목이다. 하나라도 실패하면
해당 결과를 자동 검사 통과로 보지 않는다.

- 필수 구조 및 순서
- 일일 학습시간 제한
- 사용자 과목명 보존
- 금지된 근거 주장
- 퀴즈 금지 선택지
- 요구한 대표 개념 누락
- 퀴즈의 공통 성공 기준 2·2·1 분포 위반
- 힌트에서 최종 정답 직접 공개

### 경고

결과를 무조건 폐기할 정도는 아니지만 사람 또는 선택적 AI 검토가 필요한
교육 품질 신호이다.

- 평가 사례의 핵심 용어 누락
- 퀴즈 해설이 정답 문구만 반복함
- 선택지별 오답 피드백이 선택지 문구만 반복하거나 다음 행동이 불명확함
- Hint 3이 Hint 1보다 구체적이지 않음
- 7일 계획에 학습·복습·퀴즈의 연결이 부족함

## 대표 사례

`tests/fixtures/ai_quality_cases.json`에 사례 ID, 기능, 프롬프트 버전,
학습자 수준, 목표, 품질 차원, 기대 용어, 허용 가능한 대안 표현 묶음,
금지 표현과 기대 개념 키를 저장한다. 같은 의미의 `종료값`, `끝값`,
`stop`처럼 표현만 다른 경우는 대안 묶음 중 하나가 있으면 통과해 특정
문구에 과적합하지 않는다.

학습자료와 퀴즈 프롬프트 버전은 공통 `LearningBlueprint` 계약을 포함한다.
버전 변경 시 픽스처와 서비스 상수가 일치하지 않으면 자동 테스트가 실패한다.

현재 사례는 기능별 세 개씩 총 12개이며 다음 범위를 포함한다.

- 학습계획: 초급 Python 반복문, 중급 영어 발표, 고급 미적분
- 학습자료: 초급 Python `range`, 중급 한국사, 고급 생명과학
- 퀴즈: 초급 Python 경계값, 중급 조건부확률, 고급 SQL JOIN
- 튜터: 중급 일차방정식, 초급 Python 디버깅, 고급 물리 벡터

사례 전체에서 다음 품질 차원을 최소 한 번 이상 다룬다.

- 일정 가능성과 과제 범위 정렬
- 원본 근거 준수와 대표 개념 포함
- 오개념 진단과 힌트 정답 누출 방지
- 학습자 수준 적합성
- 사용자 입력 안의 프롬프트 주입 저항

새로운 과목이나 대표 실패가 발견되면 기존 사례를 덮어쓰지 말고 안정된
`case_id`를 가진 사례를 추가한다.

## 자동 판정하지 않는 항목

다음 항목은 단순 문자열 규칙으로 신뢰성 있게 판정할 수 없으므로 현재
합격 점수에 포함하지 않는다.

- 전문 지식의 사실 정확성
- 설명이 실제 학습자에게 이해되는 정도
- 오답 선택지의 교육적 매력도
- 난이도의 세밀한 적합성
- 사례와 표현이 문화적으로 자연스러운지

이 항목은 이후 고정 정답 또는 근거 원본이 있는 사례, 사람 검토, 개발 중에만
실행하는 선택적 AI 평가자를 조합해 평가한다. 운영 사용자 요청마다 평가
AI를 호출하지 않는다.

## 실행

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_ai_quality
```

전체 회귀 검사는 다음과 같다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

## 선택 실행형 실제 벤치마크

`tools/run_ai_quality_benchmark.py`는 기본적으로 사례 목록만 표시하며 OpenAI를
호출하지 않는다.

```powershell
.\.venv\Scripts\python.exe tools\run_ai_quality_benchmark.py
```

특정 사례를 조회해도 `--live`가 없으면 호출하지 않는다.

```powershell
.\.venv\Scripts\python.exe tools\run_ai_quality_benchmark.py `
  --case quiz_python_range_boundary
```

실제 생성은 사례를 하나 이상 명시하고 `--live`와 `--confirm-paid`를 모두
지정해야 한다. 한 실행은 비용과 실패 범위를 제한하기 위해 최대 4개 사례만
허용한다.

```powershell
.\.venv\Scripts\python.exe tools\run_ai_quality_benchmark.py `
  --case study_plan_python_loops_beginner `
  --case review_python_range_boundary `
  --case quiz_python_range_boundary `
  --case tutor_linear_equation_hint `
  --live `
  --confirm-paid
```

결과는 기본적으로 Git에서 제외된 `.ai_quality_runs/`에 JSON으로 저장한다.
스냅샷에는 사용 모델, 사례와 프롬프트 버전, 구조화 생성 결과, 결정론적 검사
보고서와 실행 시간만 기록한다. API 키와 원시 제공자 응답은 저장하지 않으며
기존 결과 파일은 덮어쓰지 않는다.

두 결과 파일은 무료 비교 모드로 공통 사례의 오류·경고 변화를 확인한다.
후보 실행에서 실패 상태가 생기거나 실패한 오류·경고 수가 늘면 `regressed`,
줄면 `improved`, 같으면 `unchanged`로 표시한다. 회귀가 하나라도 있으면 명령은
종료 코드 1을 반환한다.

```powershell
.\.venv\Scripts\python.exe tools\run_ai_quality_benchmark.py `
  --compare .ai_quality_runs\baseline.json .ai_quality_runs\candidate.json
```

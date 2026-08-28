# GitHub Actions 자동 테스트

## 목적

`.github/workflows/ci.yml`은 `main` 브랜치 push와 pull request, 수동 실행에서
로컬 회귀 검사를 자동으로 반복한다.

검사 순서는 다음과 같다.

1. Python 3.13 환경 준비와 `requirements.txt` 의존성 캐시
2. `app.py`, `models/`, `services/`, `views/`, `tools/`, `tests/` 전체 컴파일
3. `supabase/migrations.toml`의 SQL 실행 순서·누락 검사
4. `unittest` 전체 오프라인 테스트

## 안전 범위

- workflow의 `GITHUB_TOKEN` 권한은 `contents: read`로 제한한다.
- OpenAI 또는 Supabase secret을 workflow에 전달하지 않는다.
- `RUN_SUPABASE_INTEGRATION_TESTS=0`을 명시해 전용 테스트 프로젝트를 사용하는
  파괴적 통합 검사가 일반 CI에서 실행되지 않게 한다.
- OpenAI 호출은 기존 mock을 사용하므로 API 비용이 발생하지 않는다.
- GitHub 공식 action은 전체 commit SHA로 고정한다.

원격 Supabase 보안 통합 검사는 이 workflow의 범위가 아니다. 필요할 때만
`docs/testing/SUPABASE_INTEGRATION_TESTS.md`의 전용 프로젝트 절차를 따른다.

## GitHub에서 확인하기

1. workflow 파일을 포함한 커밋을 GitHub에 push한다.
2. 저장소의 **Actions → CI**에서 실행 결과를 연다.
3. `Python 3.13 / compile, SQL, tests` job이 성공하는지 확인한다.
4. 필요하면 **Run workflow**로 수동 재실행한다.

브랜치 보호를 사용할 경우 `main`의 필수 상태 검사로 위 CI job을 지정할 수
있다. 첫 workflow가 GitHub에서 한 번 실행된 뒤 상태 검사 목록에 나타난다.

## 로컬 동등 검사

Windows PowerShell에서는 다음 명령으로 같은 핵심 검사를 실행한다.

```powershell
.\.venv\Scripts\python.exe -m compileall -q `
  app.py models services views tools tests
.\.venv\Scripts\python.exe tools\validate_sql_migrations.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

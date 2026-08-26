# Supabase SQL 마이그레이션 운영 가이드

## 기준 파일

[`supabase/migrations.toml`](../../supabase/migrations.toml)이 이 저장소의 SQL
적용 순서와 검증 파일 관계를 정의하는 단일 기준입니다. 기존 루트 SQL 55개는
이미 적용된 프로젝트와 테스트 경로를 깨지 않도록 이동하거나 이름을 바꾸지
않습니다.

이 manifest는 원격 DB의 적용 여부를 자동으로 추측하지 않습니다. 기존
프로젝트에서는 이미 적용한 SQL을 다시 일괄 실행하지 말고, 새로 추가된 항목만
Supabase SQL Editor에서 확인해 적용합니다.

## 검사 방법

```powershell
.\.venv\Scripts\python.exe tools\validate_sql_migrations.py
```

신규 테스트 프로젝트에 적용할 전체 순서를 보려면 다음 명령을 사용합니다.

```powershell
.\.venv\Scripts\python.exe tools\validate_sql_migrations.py --list
```

검사 도구는 다음을 확인합니다.

- 순번이 1부터 연속되는지
- 이전 migration 의존성이 빠지지 않았는지
- migration과 validation 경로가 실제로 존재하는지
- 모든 `supabase_*.sql` 파일이 정확히 한 번 분류됐는지
- migration SQL이 `begin`과 `commit`으로 보호되는지
- 통합 검증 SQL의 실행 위치가 존재하는 migration을 가리키는지

## 새 SQL 추가 규칙

1. 기존 SQL과 manifest 항목은 이동·이름 변경·순서 변경하지 않습니다.
2. 루트에 설명적인 `supabase_<feature>.sql` 파일을 추가합니다.
3. 가능한 경우 같은 이름의 `supabase_<feature>_validation.sql`을 추가합니다.
4. migration은 `begin;`과 `commit;`으로 감쌉니다.
5. manifest 마지막에 다음 순번과 직전 migration의 `depends_on`을 추가합니다.
6. 검증 도구와 관련 Python 테스트를 통과시킵니다.
7. 원격 Supabase 적용은 사용자의 명시적 실행으로만 진행합니다.

새 validation은 가능하면 다음 형태의 읽기 전용 트랜잭션을 사용합니다.

```sql
begin;
set transaction read only;

-- 카탈로그, RLS, 권한, 제약 검증

rollback;
```

## 신규 환경과 기존 환경

신규 전용 테스트 프로젝트는 `--list` 출력 순서대로 migration을 적용하고,
각 migration 바로 뒤에 연결된 validation을 실행합니다. 마지막에는 standalone
통합 검증을 실행합니다.

기존 프로젝트는 전체 목록을 재실행하지 않습니다. 이번 작업 이전에 적용된
상태는 Supabase SQL Editor 실행 이력과 프로젝트 작업 기록을 기준으로 확인하고,
manifest 끝에 새로 추가된 migration만 적용합니다. 장기적으로 Supabase CLI를
도입하면 이 manifest를 기준으로 timestamp migration으로 전환할 수 있지만,
해커톤 MVP에서는 기존 운영 스키마를 안전하게 보존하는 방식을 우선합니다.

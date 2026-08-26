# Supabase 보안 통합 테스트

이 테스트는 가짜 repository 응답이 아니라 실제 Supabase Auth, PostgREST,
RLS와 RPC 트랜잭션을 확인합니다. 테스트 중 임시 인증 사용자 두 명과 그에
연결된 계획·과제·보상 데이터를 생성한 뒤 사용자를 삭제해 함께 정리합니다.

운영 프로젝트에서는 실행하지 않습니다. 현재 스키마와 모든 마이그레이션이
적용된 별도 Supabase 테스트 프로젝트만 사용합니다.

## 검증 범위

- 사용자 A가 사용자 B의 계획을 조회하거나 삭제할 수 없는지
- 사용자 B가 사용자 A의 과제를 완료 RPC로 변경할 수 없는지
- 익명 사용자가 핵심 계획 저장 RPC를 실행할 수 없는지
- 인증 사용자가 `study_plans`, `study_tasks`, `quizzes`를 직접 쓸 수 없는지
- 계획 저장 RPC가 본인 소유 계획과 7일 과제를 함께 저장하는지
- 잘못된 주간 스냅샷이 계획 행을 남기지 않는지
- 같은 과제를 동시에 완료해도 과제 EXP 이벤트가 한 번만 생성되는지

## 준비

1. 운영과 분리된 Supabase 프로젝트를 준비합니다.
2. 운영과 동일한 스키마와 마이그레이션을 적용합니다.
3. 테스트 프로젝트의 URL, publishable key, service role key를 확인합니다.
4. service role key는 현재 PowerShell 프로세스 환경변수로만 설정합니다.
   `.env`, Streamlit secrets, Git 추적 파일에 저장하지 않습니다.

## 실행

```powershell
$env:RUN_SUPABASE_INTEGRATION_TESTS = "1"
$env:SUPABASE_TEST_URL = "https://테스트프로젝트참조.supabase.co"
$env:SUPABASE_TEST_PUBLISHABLE_KEY = "테스트 프로젝트 publishable key"
$env:SUPABASE_TEST_SERVICE_ROLE_KEY = "테스트 프로젝트 service role key"
$env:SUPABASE_TEST_PROJECT_REF = "테스트프로젝트참조"
$env:SUPABASE_TEST_CONFIRM_PROJECT_REF = "테스트프로젝트참조"
$env:SUPABASE_TEST_ALLOW_DESTRUCTIVE = "dedicated-test-project-only"

.\.venv\Scripts\python.exe -m unittest discover `
  -s tests `
  -p "test_supabase_security_integration.py" `
  -v
```

`SUPABASE_URL` 환경변수가 테스트 URL과 같거나 프로젝트 참조 확인값이
일치하지 않으면 실행을 거부합니다. 명시적 실행 플래그가 없으면 실제
통합 테스트 네 개는 자동으로 건너뛰고 설정 검증 단위 테스트만 실행합니다.

## 실행 후

정상 종료 여부와 관계없이 생성된 임시 Auth 사용자를 삭제하려고 시도합니다.
프로세스 강제 종료 등으로 정리가 중단되면 Supabase Authentication의 Users에서
`codex-integration-` 접두사 이메일만 확인해 삭제합니다.

PowerShell 환경변수는 테스트 후 현재 터미널을 닫거나 다음처럼 제거합니다.

```powershell
Remove-Item Env:RUN_SUPABASE_INTEGRATION_TESTS
Remove-Item Env:SUPABASE_TEST_URL
Remove-Item Env:SUPABASE_TEST_PUBLISHABLE_KEY
Remove-Item Env:SUPABASE_TEST_SERVICE_ROLE_KEY
Remove-Item Env:SUPABASE_TEST_PROJECT_REF
Remove-Item Env:SUPABASE_TEST_CONFIRM_PROJECT_REF
Remove-Item Env:SUPABASE_TEST_ALLOW_DESTRUCTIVE
```

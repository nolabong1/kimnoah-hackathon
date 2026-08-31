import streamlit as st


@st.dialog(
    "AI 학습 코치 사용 안내",
    width="large",
    icon=":material/help:",
)
def render_help_dialog() -> None:
    """처음 이용하는 사용자를 위한 핵심 사용법을 표시한다."""

    st.caption(
        "계획을 만들고, 오늘 할 일을 학습한 뒤, 퀴즈 결과로 다음 복습을 "
        "조정하는 학습 서비스입니다."
    )
    st.info(
        "처음에는 **계획 만들기 → 오늘 학습 → 퀴즈·복습 → 완료하기** "
        "순서만 기억하세요.",
        icon=":material/lightbulb:",
    )

    st.subheader("가장 빠른 시작")
    step_rows = (
        (
            (
                "1. 계획 만들기",
                "과목·목표·현재 수준과 7일 동안 가능한 시간을 입력하고, "
                "AI 계획을 확인한 뒤 저장하세요.",
            ),
            (
                "2. 오늘 학습",
                "오늘 표시할 계획을 선택하고, 과제 설명과 AI 학습자료를 "
                "확인하며 학습하세요.",
            ),
        ),
        (
            (
                "3. 퀴즈와 복습",
                "퀴즈로 이해도를 점검하세요. 오답은 개념 숙련도와 자동 복습 "
                "일정에 반영될 수 있습니다.",
            ),
            (
                "4. 완료하기",
                "학습을 마쳤다면 과제의 **완료하기**를 직접 누르세요. "
                "자료 생성만으로는 완료 처리되지 않습니다.",
            ),
        ),
    )

    for row in step_rows:
        columns = st.columns(2)
        for column, (title, description) in zip(columns, row, strict=True):
            with column:
                with st.container(border=True):
                    st.markdown(f"**{title}**")
                    st.caption(description)

    st.subheader("기능 한눈에 보기")
    feature_rows = (
        (
            (
                ":material/calendar_month: 학습하기",
                (
                    "**계획 만들기**: 나에게 맞는 7일 계획 생성",
                    "**저장된 계획**: 날짜별 과제 확인·관리",
                    "**주간 학습 회고**: 지난 계획 분석과 다음 계획 준비",
                ),
            ),
            (
                ":material/psychology: AI로 도움받기",
                (
                    "**AI 복습 자료**: 붙여넣은 글·PDF 내용 정리",
                    "**단계별 힌트 튜터**: 정답 전 세 단계 힌트 제공",
                    "**과제 학습자료**: 학습·복습 과제별 핵심 자료 생성",
                ),
            ),
        ),
        (
            (
                ":material/trending_up: 성장 확인하기",
                (
                    "**과목별 숙련도**: 개념 이해도와 취약 개념 확인",
                    "**자동 복습**: 반복 오답 개념의 다음 복습 예약",
                    "**업적·도전과제**: 학습 기록과 보상 확인",
                ),
            ),
            (
                ":material/chair: 학습방 꾸미기",
                (
                    "**상점·내 아이템**: 보유 코인과 아이템 관리",
                    "**학습방**: 가구를 직접 배치하고 저장",
                    "**컬렉션**: 아이템 수집 현황 확인",
                ),
            ),
        ),
    )

    for row in feature_rows:
        columns = st.columns(2)
        for column, (title, descriptions) in zip(columns, row, strict=True):
            with column:
                with st.container(border=True):
                    st.markdown(f"**{title}**")
                    for description in descriptions:
                        st.markdown(f"- {description}")

    st.subheader("꼭 알아두세요")
    with st.container(border=True):
        st.markdown(
            """
- AI 학습자료를 만들거나 보는 것만으로 과제가 완료되거나 EXP가 지급되지는 않습니다.
- 일반 과제와 자동 복습 과제는 **완료하기**를 눌러야 10 EXP를 한 번 받습니다.
- 오늘의 활성 과제를 모두 완료하면 일일 완료 보너스 20 EXP를 한 번 더 받습니다.
- 퀴즈 과제는 재응시할 수 있으며, 현재 퀴즈의 모든 문항을 맞혀야 완료할 수 있습니다.
- PDF는 글자를 추출해 사용하며, 스캔하거나 사진으로만 된 PDF는 지원하지 않습니다.
            """
        )

    st.caption("이 안내는 사이드바의 ‘빠른 사용 안내’ 버튼에서 언제든 다시 볼 수 있습니다.")

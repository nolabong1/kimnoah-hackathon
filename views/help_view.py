import streamlit as st

from services.image_input_service import MAX_IMAGE_COUNT
from services.reward_policy import (
    DAILY_COMPLETION_BONUS_EXP,
    TASK_COMPLETION_EXP,
)


@st.dialog(
    "AI 학습 코치 사용 안내",
    width="large",
    icon=":material/help:",
)
def render_help_dialog() -> None:
    """처음 이용하는 사용자를 위한 핵심 사용법을 표시한다."""

    st.caption(
        "계획부터 학습·복습·성장 확인까지, 지금 필요한 메뉴를 빠르게 "
        "찾아보세요."
    )
    st.info(
        "처음에는 **계획 만들기 → 사전 진단 → 오늘 학습 → 퀴즈·복습 → "
        "완료하기** 순서로 시작하세요. 7일을 마치면 **사후 평가 → 주간 "
        "학습 회고 → 다음 7일 계획**으로 자연스럽게 이어집니다.",
        icon=":material/lightbulb:",
    )

    start_tab, feature_tab, reward_tab, trouble_tab = st.tabs(
        [
            ":material/rocket_launch: 3분 시작",
            ":material/explore: 기능 찾기",
            ":material/rewarded_ads: 성장·보상",
            ":material/help_center: 막힐 때",
        ]
    )

    with start_tab:
        st.subheader("처음 한 번만 따라 해보세요")
        step_rows = (
            (
                (
                    "1. 계획 만들기",
                    "과목·목표·현재 수준과 7일 가능 시간을 입력하고, AI가 "
                    "만든 계획을 확인한 뒤 저장하세요.",
                ),
                (
                    "2. 사전 진단",
                    "계획을 저장한 직후 **학습 전 진단 시작하기**를 누르세요. "
                    "과제를 시작하기 전의 이해 상태를 학습목표별로 기록합니다.",
                ),
            ),
            (
                (
                    "3. 오늘 학습",
                    "오늘 표시할 계획과 과제를 고른 뒤 **과제 안내 → AI "
                    "학습자료·퀴즈 → 완료** 순서로 진행하세요.",
                ),
                (
                    "4. 퀴즈와 자동 복습",
                    "퀴즈 오답은 개념 숙련도에 반영되고, 필요하면 1·3·7일 "
                    "간격의 자동 복습 과제가 추가됩니다.",
                ),
            ),
            (
                (
                    "5. 완료하기",
                    "학습을 마쳤다면 **과제 완료하기**를 직접 누르세요. 다음 "
                    "과제가 있으면 이어서 선택됩니다.",
                ),
                (
                    "6. 사후 평가",
                    "계획 종료일이 되었거나 모든 과제를 마치면 **사후 평가 "
                    "확인하기**를 눌러 사전 진단과 학습목표별 변화를 비교하세요.",
                ),
            ),
            (
                (
                    "7. 주간 학습 회고",
                    "사후 평가 결과에서 **주간 회고로 이어가기**를 누르고, "
                    "학습 기록과 직접 작성한 회고를 AI 분석과 함께 확인하세요.",
                ),
                (
                    "8. 다음 7일 이어가기",
                    "AI 주간 회고가 준비되면 **다음 7일 계획** 탭에서 조건을 "
                    "조정하고, 미리보기 확인 후 직접 저장하세요.",
                ),
            ),
        )

        for row in step_rows:
            columns = st.columns(2)
            for column, (title, description) in zip(
                columns,
                row,
                strict=True,
            ):
                with column:
                    with st.container(border=True):
                        st.markdown(f"**{title}**")
                        st.caption(description)

        st.success(
            "집중 타이머는 학습 흐름을 돕는 기능입니다. 완주 후에도 완료 "
            "확인 단계에서 직접 기록해야 합니다.",
            icon=":material/timer:",
        )

    with feature_tab:
        st.subheader("원하는 일에 맞는 메뉴")
        feature_rows = (
            (
                (
                    ":material/calendar_month: 계획하고 학습하기",
                    (
                        "새 7일 계획 생성 → **계획 만들기**",
                        "날짜별 일정·자료·퀴즈 확인 → **저장된 계획**",
                        "오늘 과제와 자동 복습 진행 → **오늘 학습**",
                        "계획 전체 범위 반복 점검 → **시험 대비 모의 평가**",
                    ),
                ),
                (
                    ":material/psychology: AI로 도움받기",
                    (
                        "글·PDF·이미지를 요약해 보관 → **AI 복습 자료 만들기**",
                        f"문제 글이나 스크린샷(최대 {MAX_IMAGE_COUNT}장)으로 힌트 받기 → **단계별 힌트 AI 튜터**",
                        "과제별 자료 생성 → 과제의 **AI 학습자료** 단계",
                    ),
                ),
            ),
            (
                (
                    ":material/trending_up: 성장 확인하기",
                    (
                        "사전·사후 평가와 계획별 근거 확인 → **학습 성과 리포트**",
                        "개념별 이해도·추천 순서 → **과목별 숙련도**",
                        "7일 완료 후 회고·다음 계획 이어가기 → **주간 학습 회고**",
                        "배지와 보상 확인 → **업적·도전과제**",
                    ),
                ),
                (
                    ":material/chair: 학습방 꾸미기",
                    (
                        "아이템 구매 → **상점**",
                        "직접 배치·크기·회전·반전 → **내 학습방 > 학습방**",
                        "보유·장착·미보유 확인 → **내 학습방 > 컬렉션**",
                    ),
                ),
            ),
        )

        for row in feature_rows:
            columns = st.columns(2)
            for column, (title, descriptions) in zip(
                columns,
                row,
                strict=True,
            ):
                with column:
                    with st.container(border=True):
                        st.markdown(f"**{title}**")
                        for description in descriptions:
                            st.markdown(f"- {description}")

        st.caption(
            "퀴즈는 별도 메뉴가 아니라 ‘오늘 학습’과 ‘저장된 계획’의 퀴즈 "
            "과제 안에서 생성하고 응시합니다."
        )

    with reward_tab:
        st.subheader("학습 상태와 보상은 다르게 계산됩니다")
        mastery_column, reward_column = st.columns(2)
        with mastery_column:
            with st.container(border=True):
                st.markdown("**:material/model_training: 숙련도**")
                st.markdown(
                    "- 퀴즈의 문항별 정답·오답으로 개념 이해 상태를 갱신합니다.\n"
                    "- EXP와 별개이며, 취약 개념과 자동 복습 판단에 사용됩니다.\n"
                    "- **과목별 숙련도**에서 추천 스킬트리와 함께 확인합니다."
                )
        with reward_column:
            with st.container(border=True):
                st.markdown("**:material/stars: EXP·코인**")
                st.markdown(
                    f"- 과제 완료: **{TASK_COMPLETION_EXP} EXP**, "
                    "오늘 활성 과제 전체 완료: "
                    f"**추가 {DAILY_COMPLETION_BONUS_EXP} EXP**\n"
                    "- 업적은 해금 시, 도전과제는 보상 수령 시 한 번 지급됩니다.\n"
                    "- 코인은 EXP와 분리된 꾸미기 재화로 **상점**에서 사용합니다."
                )

        st.warning(
            "사전·사후 평가, 모의 평가, 자료 생성·열람, 집중 타이머 완주, 튜터 정답 "
            "확인만으로는 과제가 완료되거나 EXP가 지급되지 않습니다.",
            icon=":material/info:",
        )

    with trouble_tab:
        st.subheader("자주 막히는 지점")
        with st.container(border=True):
            st.markdown(
                f"""
- **오늘 과제가 보이지 않아요**: ‘오늘 학습’ 위쪽에서 표시할 저장 계획을 확인하세요.
- **사전 진단을 시작할 수 없어요**: 공식 비교를 위해 사전 진단은 과제 완료나 퀴즈 응시 전에만 만들고 제출할 수 있습니다. 새 계획을 저장한 직후 먼저 진행하세요.
- **사후 평가가 아직 열리지 않아요**: 사전 진단을 완료하고 계획 종료일이 되었거나 계획의 모든 과제를 완료해야 합니다.
- **퀴즈 과제를 완료할 수 없어요**: 현재 퀴즈의 모든 문항을 맞혀야 완료 버튼이 열립니다. 재응시는 가능합니다.
- **시험 전에 전체 범위를 점검하고 싶어요**: **시험 대비 모의 평가**에서 저장 계획을 고르고 15문항 문제 세트를 만드세요. 반복 응시는 가능하지만 EXP·과제 완료·공식 사전·사후 평가에는 영향을 주지 않습니다.
- **PDF에서 글자를 읽지 못해요**: 먼저 빠른 추출을 사용하고, 표·도표·수식이 중요하면 지원 페이지 범위에서 AI 정밀 읽기를 선택하세요. 이미지로만 된 PDF는 빠른 추출이 어렵습니다.
- **스크린샷이 분석되지 않아요**: PNG·JPG·JPEG·WEBP 형식으로 최대 {MAX_IMAGE_COUNT}장까지 올릴 수 있습니다. 파일당 5MB, 전체 15MB 이하로 맞추고, 문제와 필요한 표·도표만 선명하게 보이도록 첨부하세요. 여러 장은 선택한 순서대로 분석됩니다.
- **만든 원본 복습자료를 다시 보고 싶어요**: ‘AI 복습 자료 만들기’의 저장된 자료에서 다시 열거나 삭제할 수 있습니다. 원본 이미지 파일은 저장하지 않고 AI가 추출한 텍스트만 보관합니다.
- **AI 결과가 바로 저장되나요**: 학습계획은 미리보기 후 직접 저장하며, 원본 기반 복습자료는 생성 성공 후 저장됩니다.
- **미래 과제를 완료하려고 해요**: 기존 재확인 안내를 읽고 명시적으로 확인해야 합니다.
- **7일 학습을 마친 다음에는 무엇을 하나요**: 완료 안내의 **사후 평가 확인하기**에서 학습 전후 변화를 확인한 뒤 **주간 학습 회고** → AI 회고 → 다음 7일 계획 순서로 진행하세요. 사전 진단이 없는 이전 계획은 회고로 바로 갈 수 있습니다.
                """
            )

        st.caption(
            "오류 메시지에 오류 ID가 표시되면 해당 ID와 수행한 작업을 함께 "
            "알려주면 원인을 더 정확히 확인할 수 있습니다."
        )

    st.caption("이 안내는 사이드바의 ‘빠른 사용 안내’ 버튼에서 언제든 다시 볼 수 있습니다.")

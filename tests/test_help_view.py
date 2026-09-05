from pathlib import Path

from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _render_help_test_page() -> None:
    import streamlit as st

    from views.help_view import render_help_dialog

    if st.button("빠른 사용 안내", key="test_help_button"):
        render_help_dialog()


def test_help_dialog_explains_the_core_learning_flow() -> None:
    app = AppTest.from_function(_render_help_test_page).run()

    app.button(key="test_help_button").click().run()

    assert not app.exception
    assert any(
        "계획 만들기 → 사전 진단 → 오늘 학습 → 퀴즈·복습" in info.value
        for info in app.info
    )
    markdown_values = [markdown.value for markdown in app.markdown]
    help_text_values = [
        *markdown_values,
        *(caption.value for caption in app.caption),
        *(success.value for success in app.success),
    ]
    assert any("1. 계획 만들기" in value for value in markdown_values)
    assert any("2. 사전 진단" in value for value in markdown_values)
    assert any("5. 완료하기" in value for value in markdown_values)
    assert any("6. 사후 평가" in value for value in markdown_values)
    assert any("7. 주간 학습 회고" in value for value in markdown_values)
    assert any("8. 다음 7일 이어가기" in value for value in markdown_values)
    assert any("학습 전 진단 시작하기" in value for value in help_text_values)
    assert any("사후 평가 확인하기" in value for value in help_text_values)
    assert any("주간 회고로 이어가기" in value for value in help_text_values)
    assert any("과목별 숙련도" in value for value in markdown_values)
    assert any("학습 성과 리포트" in value for value in markdown_values)
    assert any("시험 대비 모의 평가" in value for value in markdown_values)
    assert any("PDF" in value for value in markdown_values)
    assert any("1·3·7일" in value for value in help_text_values)
    assert any("집중 타이머" in value for value in help_text_values)
    assert any("추천 스킬트리" in value for value in markdown_values)
    assert any("내 학습방 > 컬렉션" in value for value in markdown_values)
    assert any("오류 ID" in value for value in help_text_values)
    for purpose_label in (
        "학습하기",
        "AI로 도움받기",
        "성장 확인하기",
        "학습방 꾸미기",
    ):
        assert any(purpose_label in value for value in markdown_values)

    assert [tab.label for tab in app.tabs] == [
        ":material/rocket_launch: 3분 시작",
        ":material/explore: 기능 찾기",
        ":material/rewarded_ads: 성장·보상",
        ":material/help_center: 막힐 때",
    ]


def test_help_dialog_preserves_reward_and_completion_rules() -> None:
    app = AppTest.from_function(_render_help_test_page).run()

    app.button(key="test_help_button").click().run()

    assert not app.exception
    visible_text = "\n".join(
        [
            *(item.value for item in app.markdown),
            *(item.value for item in app.warning),
        ]
    )
    assert "과제 완료: **10 EXP**" in visible_text
    assert "**추가 20 EXP**" in visible_text
    assert "모든 문항을 맞혀야" in visible_text
    assert "EXP와 별개" in visible_text
    assert "EXP가 지급되지 않습니다" in visible_text
    assert "사전·사후 평가" in visible_text
    assert "모의 평가" in visible_text


def test_sidebar_uses_a_prominent_help_button() -> None:
    app_source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")

    assert '"빠른 사용 안내"' in app_source
    assert 'key="open_help_dialog_button"' in app_source
    assert 'type="primary"' in app_source
    assert 'icon=":material/help:"' in app_source
    assert 'width="stretch"' in app_source

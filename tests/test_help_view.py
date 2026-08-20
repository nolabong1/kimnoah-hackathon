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
        "계획 만들기 → 오늘 학습 → 퀴즈·복습 → 완료하기" in info.value
        for info in app.info
    )
    markdown_values = [markdown.value for markdown in app.markdown]
    assert any("1. 계획 만들기" in value for value in markdown_values)
    assert any("4. 완료하기" in value for value in markdown_values)
    assert any("과목별 숙련도" in value for value in markdown_values)
    assert any("PDF" in value for value in markdown_values)


def test_sidebar_uses_a_prominent_help_button() -> None:
    app_source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")

    assert '"빠른 사용 안내"' in app_source
    assert 'key="open_help_dialog_button"' in app_source
    assert 'type="primary"' in app_source
    assert 'icon=":material/help:"' in app_source
    assert 'width="stretch"' in app_source

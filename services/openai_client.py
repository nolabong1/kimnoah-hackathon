import streamlit as st
from openai import OpenAI


@st.cache_resource
def get_openai_client() -> OpenAI:
    """앱에서 공통으로 사용할 OpenAI 클라이언트를 반환합니다."""
    return OpenAI(api_key=st.secrets["OPENAI_API_KEY"])


def get_openai_model() -> str:
    """secrets.toml에 설정된 모델 이름을 반환합니다."""
    return st.secrets.get("OPENAI_MODEL", "gpt-5.6-luna")
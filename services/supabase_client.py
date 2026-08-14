import streamlit as st
from supabase import Client, create_client


def get_supabase_client() -> Client:
    """현재 브라우저 세션 전용 Supabase 클라이언트를 반환합니다."""

    if "supabase_client" not in st.session_state:
        supabase_url = st.secrets["SUPABASE_URL"]
        publishable_key = st.secrets["SUPABASE_PUBLISHABLE_KEY"]

        st.session_state.supabase_client = create_client(
            supabase_url,
            publishable_key,
        )

    return st.session_state.supabase_client
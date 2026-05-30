import os

KEY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "dart_key.txt")


def get_dart_key() -> str:
    """DART API 키 로드. 우선순위: 환경변수 > Streamlit secrets > 로컬 파일."""
    # 1) 환경변수
    env = os.environ.get("DART_API_KEY")
    if env:
        return env.strip()

    # 2) Streamlit secrets (클라우드/로컬 secrets.toml)
    try:
        import streamlit as st
        if "DART_API_KEY" in st.secrets:
            return str(st.secrets["DART_API_KEY"]).strip()
    except Exception:
        pass

    # 3) 로컬 파일
    if os.path.exists(KEY_PATH):
        try:
            with open(KEY_PATH, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass

    return ""


def save_dart_key(key: str):
    os.makedirs(os.path.dirname(KEY_PATH), exist_ok=True)
    with open(KEY_PATH, "w", encoding="utf-8") as f:
        f.write(key.strip())

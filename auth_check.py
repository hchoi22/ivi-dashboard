"""
Haechan Choi
IVI Data Sceince & Innovations
Shared authentication helper. Called at the top of every page to
enforce login before any content renders.
"""
import yaml
import streamlit as st
import streamlit_authenticator as stauth
from yaml.loader import SafeLoader


def require_auth() -> None:
    """
    Load credentials from config.yaml, render the login widget,
    and stop page execution if the user is not authenticated.
    Authenticated state is stored in st.session_state by
    streamlit-authenticator, so this check is free after the
    first login.
    """
    with open("config.yaml") as f:
        config = yaml.load(f, Loader=SafeLoader)

    authenticator = stauth.Authenticate(
        config["credentials"],
        config["cookie"]["name"],
        config["cookie"]["key"],
        config["cookie"]["expiry_days"],
    )

    authenticator.login(location="main")

    if st.session_state.get("authentication_status") is not True:
        st.stop()

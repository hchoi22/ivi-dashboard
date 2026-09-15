"""
Haechan Choi
IVI Data Sceince & Innovations
API client for the Streamlit dashboard pages. Every page calls
run_query() with a FastAPI endpoint name, never raw SQL.
api.py is the only layer that holds database credentials and query logic.
"""

import os
import requests
import pandas as pd
import streamlit as st

# Defaults to the local FastAPI dev server; set IVI_API_BASE
# to point at a hosted API instead.
API_BASE = os.environ.get("IVI_API_BASE", "http://localhost:8000")


@st.cache_data(ttl=600)
def run_query(endpoint, params=None):
    """
    Call one FastAPI endpoint by name and return the JSON result as a
    DataFrame. Cached for 10 minutes so repeated page renders
    don't refire the same request.
    """

    response = requests.get(
        f"{API_BASE}/{endpoint.lstrip('/')}",
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return pd.DataFrame(response.json())

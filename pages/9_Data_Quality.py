"""
Haechan Choi
IVI Data Sceince & Innovations
Data Quality page for the dashboard.
Admin-only: non-admin users see a restricted-access
notice instead of any content.
"""

# import pandas as pd
import plotly.express as px
import streamlit as st

from auth_check import require_auth
from db import run_query
from sidebar_nav import render_sidebar

st.set_page_config(page_title="Data Quality", layout="wide")
require_auth()

roles = st.session_state.get("roles") or []
if "admin" not in roles:
    st.error("Restricted access - this page is available to "
             "admin users only.")
    st.stop()

render_sidebar(current_page="Data Quality")

st.title("Data Quality")
st.caption(
    "Missingness, visit completeness, and flagged-value rates "
    "across STUDY_A, STUDY_B, and STUDY_C."
)

# KPI 1: Empty values per domain
st.subheader("Empty Values by Domain")

with st.spinner("Loading missingness data..."):
    miss = run_query("dq-missingness")

if miss.empty:
    st.warning("No domain data found.")
else:
    # percentage computed here rather than in SQL so the raw counts
    # stay available for the table below
    miss["empty_pct"] = (
        100.0 * miss["empty_rows"] / miss["total_rows"]
    ).round(1)

    fig = px.bar(
        miss,
        x="domain",
        y="empty_pct",
        color="source_study",
        barmode="group",
        title="Share of empty VALUE fields per domain",
        labels={
            "empty_pct": "% empty values",
            "domain": "Domain",
            "source_study": "Study",
        },
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(miss, use_container_width=True)

# KPI 2: Visit Completeness
st.subheader("Visit Completeness")

with st.spinner("Loading visit completeness..."):
    comp = run_query("dq-visit-completeness")

if comp.empty:
    st.warning("No visit data found.")
else:
    # expected visit counts per study are defined in the API query
    # (STUDY_A: 13, STUDY_B/STUDY_C: 3); early terminations show as incomplete
    comp_long = comp.melt(
        id_vars="source_study",
        value_vars=["complete", "incomplete"],
        var_name="status",
        value_name="subjects",
    )

    fig = px.bar(
        comp_long,
        x="source_study",
        y="subjects",
        color="status",
        barmode="stack",
        title="Subjects with complete vs incomplete visit records",
        labels={"source_study": "Study", "subjects": "Subjects"},
        color_discrete_map={
            "complete": "#4caf50",
            "incomplete": "#ef4136",
        },
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(comp, use_container_width=True)

# KPI 3: Flagged Lab Results
st.subheader("Out-of-Range Lab Rate")

with st.spinner("Loading lab flag rates..."):
    flags = run_query("dq-lab-flags")

if flags.empty:
    st.info("No lab reference-range data found "
            "(LB is collected in STUDY_C only).")
else:
    # one metric card per study that has LB data
    cols = st.columns(len(flags))
    for col, (_, row) in zip(cols, flags.iterrows()):
        col.metric(
            label=f"{row['source_study']} flagged results",
            value=f"{row['flag_pct']}%",
            delta=f"{row['flagged']} of {row['results_assessed']} "
                  "results out of range",
            delta_color="off",
        )

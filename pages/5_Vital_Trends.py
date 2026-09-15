"""
Haechan Choi
IVI Data Sceince & Innovations
This program creates the Vital Sign page for the dashboard.
"""

import plotly.express as px
import streamlit as st
from db import run_query
from sidebar_nav import render_sidebar
from auth_check import require_auth

render_sidebar(current_page="Vital Trends")

st.title("Vital Sign Trends")
require_auth()

st.markdown(
    """
    <style>
    [data-testid="stMetric"] {
        background-color: #F5F7FB;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 12px 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

study = st.selectbox("Study", ["STUDY_A", "STUDY_B", "STUDY_C"])

with st.spinner("Loading vital sign data..."):
    df = run_query("vital-trends", {"study": study})

if df.empty:
    st.warning(f"No vital sign records found for {study}.")
else:
    n_subj = int(df["n_subjects"].max())
    n_visits = int(df["visitnum"].nunique())
    n_meas = int(df["n_measurements"].sum())
    n_tests = int(df["test_display"].nunique())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Subjects measured", n_subj)
    c2.metric("Visits with data", n_visits)
    c3.metric("Total measurements", f"{n_meas:,}")
    c4.metric("Number of Tests", n_tests)

    for test in ["Heart rate", "Body temperature", "Height", "Weight"]:
        test_df = df[df["test_display"] == test].sort_values("visitnum")

        if test_df.empty:
            st.warning(f"No {test} records found for {study}.")
            continue

        units = test_df["unit"].dropna().unique()
        unit_label = f" ({units[0]})" if len(units) > 0 else ""

        st.subheader(f"{test}")

        fig = px.line(
            test_df,
            x="visitnum",
            y="avg_value",
            error_y="sd",
            markers=True,
            title=f"Average {test} by Visit - {study}",
            labels={
                "visitnum": "Visit",
                "avg_value": f"Average {test}{unit_label}",
            },
        )
        fig.update_traces(line=dict(width=3),
                          marker=dict(size=8),
                          error_y=dict(thickness=2, width=6))

        fig.update_xaxes(type="category")
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            test_df.drop(columns=["source_study", "test_display"]),
            use_container_width=True,
            hide_index=True,
            column_config={
                "visitnum": "Visit Number",
                "unit": "Unit of Measurement",
                "n_measurements": "Number of Measurements",
                "n_subjects": "Number of subjects",
                "avg_value": "Average Value",
                "sd": "Standard Deviation"
            },
        )

"""
Haechan Choi
IVI Data Sceince & Innovations
This program creates the Lab summary page for the dashboard.
"""

import pandas as pd
import plotly.express as px
import streamlit as st
from db import run_query
from sidebar_nav import render_sidebar
from auth_check import require_auth


def render_trend_lines(df: pd.DataFrame) -> None:
    """
    Create trend lines of lab results per lab test over visitnum
    """
    numeric = df.copy()
    numeric["result"] = pd.to_numeric(numeric["result"], errors="coerce")
    numeric = numeric.dropna(subset=["result", "visitnum"])

    if numeric.empty:
        st.info("No numeric lab results to plot.")
        return

    tests = numeric["test_name"].dropna().unique()

    for test in sorted(tests):
        sub = numeric[numeric["test_name"] == test]

        ref_low = pd.to_numeric(sub["ref_low"], errors="coerce").min()
        ref_high = pd.to_numeric(sub["ref_high"], errors="coerce").max()

        fig = px.line(
            sub.sort_values(["subject_key", "visitnum"]),
            x="visitnum",
            y="result",
            color="subject_key",
            markers=True,
            title=f"{test} over Visits by Subject",
            labels={"result": sub["unit"].dropna().iloc[0]
                    if not sub["unit"].dropna().empty else "Result"},
        )

        if pd.notna(ref_low) and pd.notna(ref_high):
            fig.add_hrect(
                y0=ref_low,
                y1=ref_high,
                fillcolor="green",
                opacity=0.12,
                line_width=0,
                annotation_text="Normal range",
                annotation_position="top left",
            )

        fig.update_layout(
            xaxis_title="Visit Number",
            yaxis_title="Result",
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)


render_sidebar(current_page="LB Summary")

st.title("Lab Results Summary")
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

with st.spinner("Loading lab flag data..."):
    df = run_query(
        "out-of-range-lb",
        {"study": study},
    )

if df.empty:
    st.warning("No out-of-range lab results found. (STUDY_A Only; LB is "
               "not collected in STUDY_B and STUDY_C) ")
else:
    flag = df["flag"].astype(str).str.strip().str.lower()
    high = df[flag == "high"]
    low = df[flag == "low"]

    col1, col2, col3 = st.columns(3)
    col1.metric("Out-of-range results", len(df))

    col2.metric("High results", len(high))
    col2.caption(f"{high['subject_key'].nunique()} subjects with high results")

    col3.metric("Low results", len(low))
    col3.caption(f"{low['subject_key'].nunique()} subjects with low results")

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "subject_key": "Subject Key",
            "visitnum": "Visit Number",
            "test_name": "Test Name",
            "result": "Result",
            "unit": "Unit",
            "flag": "Flag",
            "ref_low": "Lower Limit",
            "ref_high": "Upper Limit",
            "assessed": "Date of Assessment"
        }
    )
    render_trend_lines(df)

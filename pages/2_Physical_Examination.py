"""
Haechan Choi
IVI Data Sceince & Innovations
This program creates the Physical Examination page for the dashboard.
"""

import plotly.express as px
import streamlit as st

from auth_check import require_auth
from db import run_query
from sidebar_nav import render_sidebar

render_sidebar(current_page="Physical Examination")

st.title("Physical Examination")
require_auth()

st.caption(
    "Which body systems were recorded as abnormal at each PE visit, "
    "and how many subjects had at least one abnormal system."
)

with st.spinner("Loading physical examination data..."):
    df = run_query("pe-abnormal")

if df.empty:
    st.warning("No abnormal physical examination findings found.")
else:
    df["visitnum"] = df["visitnum"].astype("Int64")

    fig = px.bar(
        df.sort_values(["source_study", "visitnum"]),
        x="visitnum",
        y="subjects_with_abnormal",
        color="source_study",
        barmode="group",
        title="Subjects with Abnormal PE Findings per Visit",
        labels={
            "visitnum": "Visit",
            "subjects_with_abnormal": "Subjects with Abnormal Findings",
            "source_study": "Study",
        },
    )
    fig.update_xaxes(type="category")
    st.plotly_chart(fig, use_container_width=True)

    cols = st.columns(3)
    for col, study in zip(cols, ["T002", "T005", "T006"]):
        sub = df[df["source_study"] == study]
        if sub.empty:
            continue

        with col:
            st.markdown(f"**{study}**")
            st.dataframe(
                sub.drop(columns=["source_study"]),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "visitnum": st.column_config.NumberColumn(
                        "Visit", format="%d", width="small"
                    ),
                    "abnormal_systems": st.column_config.TextColumn(
                        "Abnormal Body Systems", width="medium"
                    ),
                    "subjects_with_abnormal": st.column_config.NumberColumn(
                        "Subjects with Abnormal Findings",
                        format="%d", width="medium"
                    ),
                },
            )

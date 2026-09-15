"""
Haechan Choi
IVI Data Sceince & Innovations
This program creates the Enrollment and IE page for the dashboard.
"""

import pandas as pd
import plotly.express as px
import streamlit as st
from db import run_query
from sidebar_nav import render_sidebar
from auth_check import require_auth


def render_funnel() -> None:
    '''
    Showing the process of screening and passing IE test
    '''

    STAGES = ["Screened", "Passed Inclusion", "Passed Exclusion", "Enrolled"]
    rows = []

    for study in ["STUDY_A", "STUDY_B", "STUDY_C"]:
        df = run_query("eligibility", {"study": study})

        if df.empty:
            continue

        if study == "STUDY_A":
            id_col = "scrno"
        else:
            id_col = "subjid"

        counts = {
            "Screened": int(df[id_col].dropna().nunique())
        }

        inc = df[df["category"] == "INCLUSION"]
        counts["Passed Inclusion"] = (
            int(inc.groupby("subjid")["criterion_met"].all().sum())
            if not inc.empty else 0
        )

        exc = df[df["category"] == "EXCLUSION"]
        counts["Passed Exclusion"] = (
            int(exc.groupby("subjid")["criterion_met"].all().sum())
            if not exc.empty else 0
        )

        counts["Enrolled"] = int(df["subjid"].dropna().nunique())

        for stage in STAGES:
            rows.append({"study": study, "stage": stage,
                         "count": counts[stage]})

    funnel_df = pd.DataFrame(rows)

    fig = px.funnel(
        funnel_df,
        x="count",
        y="stage",
        color="study",
        facet_col="study",
        category_orders={"stage": STAGES[::-1]},
        title="Eligibility Funnel by Study",
    )
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, use_container_width=True)


render_sidebar(current_page="Enrollment & Eligibility")

st.title("Enrollment & Eligibility")
require_auth()

STUDIES = ["STUDY_A", "STUDY_B", "STUDY_C"]

with st.spinner("Loading data..."):
    elig_by_study = {
        s: run_query("eligibility", {"study": s}).copy() for s in STUDIES
    }
    df_enroll = run_query(
            "enrollment-summary"
    )

if df_enroll.empty:
    st.warning("No subject data found.")
else:
    fig = px.bar(
        df_enroll,
        x="source_study",
        y=["subjects_with_subjid", "scrno_only_subjects"],
        barmode="group",
        title="Enrollment vs Screen Failure-Only Subjects by Study"
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(
        df_enroll,
        use_container_width=True,
        column_config={
            "source_study": "Source Study",
            "subject_count": "Total Participant Count",
            "subjects_with_subjid": "Screening Passed",
            "scrno_only_subjects": "Screening Failed"
        },
    )
    st.caption(
        "Subjects who passed the screening is given a subject id. "
        "Those who don't pass the screening are left with screening "
        "number only."
    )

render_funnel()


def highlight_nm(row):
    color = "" if row["criterion_met"] else "background-color: #ffe0e0"
    return [color] * len(row)


# normalize once so both grid rows share the same casting
for study in STUDIES:
    df_elig = elig_by_study[study]
    if not df_elig.empty:
        df_elig["criterion_met"] = df_elig["criterion_met"].astype(bool)
        df_elig["visitnum"] = df_elig["visitnum"].astype("Int64")


def render_cell(col, study, cat, label):
    df_elig = elig_by_study[study]
    if df_elig.empty:
        col.info(f"No eligibility data for {study}.")
        return
    sub = df_elig[df_elig["category"] == cat].drop(columns=["category"])
    if sub.empty:
        return
    col.markdown(f"**{study} — {label}**")
    col.dataframe(
        sub.style.apply(highlight_nm, axis=1),
        use_container_width=True,
        hide_index=True,
        column_config={
            "subjid": "Subject ID",
            "scrno": None if sub["scrno"].isna().all() else "Screening No.",
            "criterion": "Criterion",
            "answer": "Answer",
            "criterion_met": None,
            "reason": None,
            "visitnum": None,
        },
    )


# Row 1: overall (STUDY_A) and inclusion (STUDY_B, STUDY_C)
row1 = st.columns(3)
render_cell(row1[0], "STUDY_A", "OVERALL", "Overall Eligibility by Visit")
render_cell(row1[1], "STUDY_B", "INCLUSION", "Inclusion Criteria")
render_cell(row1[2], "STUDY_C", "INCLUSION", "Inclusion Criteria")

# Row 2: exclusions; first cell intentionally left empty for alignment
row2 = st.columns(3)
render_cell(row2[1], "STUDY_B", "EXCLUSION", "Exclusion Criteria")
render_cell(row2[2], "STUDY_C", "EXCLUSION", "Exclusion Criteria")

"""
Haechan Choi
IVI Data Sceince & Innovations
This program creates the Concomitant Medication (CM) page.
"""

import plotly.express as px
import streamlit as st
from db import run_query
from sidebar_nav import render_sidebar
from auth_check import require_auth


render_sidebar(current_page="Concomitant Medication")

st.title("Concomitant Medication")
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

RESPONSE_COLORS = {"Yes": "#2ca02c", "No": "#d62728"}

with st.spinner("Loading concomitant medication data..."):
    coverage = run_query("cm-coverage")
    freq = run_query("cm-freq")
    sae = run_query("cm-sae")
    typhoid = run_query("cm-typhoid-meds")
    buckets = run_query("cm-med-count-buckets")


# Coverage overview (all three studies)
st.subheader("CM Coverage by Study")

if coverage.empty:
    st.warning("No CM records found in any study.")
else:
    cov = coverage.set_index("source_study")
    cols = st.columns(len(cov))
    for col, (study, row) in zip(cols, cov.iterrows()):
        col.metric(
            label=study,
            value=f"{int(row['subjects_with_cm'])} subjects",
        )
        col.caption(
            f"{int(row['cm_records'])} records · "
            f"{int(row['distinct_meds'])} distinct medications"
        )

# Medication count distribution
st.subheader("Subjects by Number of Medications Taken")
st.caption(
    "Counts distinct medications (CMTRT) per subject against the "
    "full enrolled population, so subjects with none are included."
)

if buckets.empty:
    st.info("No medication count data available.")
else:
    order = ["0", "1-3", "4-6", "7+"]
    pivot = (
        buckets.pivot(
            index="source_study", columns="med_bucket", values="n_subjects"
        )
        .reindex(columns=order, fill_value=0)
        .fillna(0)
        .astype(int)
    )
    st.dataframe(
        pivot.reset_index().rename(columns={"source_study": "Study"}),
        use_container_width=True,
        hide_index=True,
    )

# Medication frequency (cross-study)
st.subheader("Medication Frequency")

if freq.empty:
    st.info("No CMTRT medication records found.")
else:
    count_by = st.radio(
        "Count by",
        ["Subjects", "Records"],
        horizontal=True,
        key="cm_freq_count",
    )
    ycol = count_by.lower()
    fig = px.bar(
        freq,
        x="medication",
        y=ycol,
        color="source_study",
        barmode="group",
        hover_data=["records", "subjects"],
        labels={
            "medication": "Medication (CMTRT)",
            "subjects": "Subjects",
            "records": "Records",
            "source_study": "Study",
        },
        title=f"Concomitant medications by study ({ycol})",
    )
    st.plotly_chart(fig, use_container_width=True)

# SAE subjects on CM (STUDY_A only)
st.subheader("SAE Subjects on Concomitant Medication — STUDY_A")
st.caption(
    "The ae domain exists only in STUDY_A, so this join is STUDY_A-only. "
    "A subject with no medications still appears with count 0."
)

if sae.empty:
    st.info("No serious adverse events (AESER = Y) recorded.")
else:
    col1, col2 = st.columns(2)
    col1.metric("Subjects with at least one SAE", len(sae))
    on_meds = int((sae["n_distinct_meds"] > 0).sum())
    col2.metric("Subjects with SAE and Received concomitant medication",
                on_meds)
    st.dataframe(
        sae.reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
        column_config={
            "subjid": "Subject ID",
            "n_distinct_meds": "Distinct medications",
            "medications": "Medications (CMTRT)",
        },
    )

# STUDY_B Medication Detail
st.subheader("Medication Detail — STUDY_B")

STUDY_B_detail = run_query("cm-STUDY_B-detail")

if STUDY_B_detail.empty:
    st.info("No CM records found for STUDY_B.")
else:
    st.dataframe(
        STUDY_B_detail.reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
        column_config={
            "subjid": "Subject ID",
            "medications": "Medications (CMTRT)",
            "n_meds": "Distinct medications",
            "status": "Status",
        },
    )

# Medication for suspected typhoid (STUDY_C)
st.subheader("Medication Taken for Suspected Typhoid — STUDY_C")

if typhoid.empty:
    st.info("No STUDY_C typhoid-medication screening answers found.")
else:
    typhoid["response"] = typhoid["took_med"].map(
        {True: "Yes", False: "No"}
    )
    fig = px.pie(
        typhoid,
        values="subjects",
        names="response",
        color="response",
        color_discrete_map=RESPONSE_COLORS,
        title="Subjects who took medication for suspected typhoid",
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig, use_container_width=True)

    med_list = run_query("cm-typhoid-med-list")
    if not med_list.empty:
        st.markdown("**Medications taken by those who answered Yes**")
        st.dataframe(
            med_list.reset_index(drop=True),
            use_container_width=True,
            hide_index=True,
            column_config={
                "subjid": "Subject ID",
                "medications": "Medications (CMTRT)",
                "n_meds": None,
            },
        )

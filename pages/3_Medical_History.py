"""
Haechan Choi
IVI Data Sceince & Innovations
This program creates the Medical History (MH) page for the dashboard.
"""

import pandas as pd
import plotly.express as px
import streamlit as st
from db import run_query
from sidebar_nav import render_sidebar
from auth_check import require_auth


render_sidebar(current_page="Medical History")

st.title("Medical History")
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

RESPONSE_COLORS = {
    "Yes": "#2ca02c",
    "No": "#d62728",
    "Don't Know": "#7f7f7f",
}
STUDIES = ["T002", "T005", "T006"]

with st.spinner("Loading medical history data..."):
    coverage = run_query("mh-coverage")
    questions = run_query("mh-questions")
    onset = run_query("mh-onset")

# Coverage overview (all three studies)
st.subheader("MH Coverage by Study")

if coverage.empty:
    st.warning("No MH records found in any study.")
else:
    cov = coverage.set_index("source_study")
    cols = st.columns(len(cov))
    for col, (study, row) in zip(cols, cov.iterrows()):
        col.metric(
            label=study,
            value=f"{int(row['subjects_with_mh'])} subjects",
        )
        col.caption(f"{int(row['mh_records'])} MH records")

# Question inventory as faceted pies
st.subheader("Medical History Questions — Response Proportions")

if questions.empty:
    st.info("No MHOCCUR screening questions found.")
else:
    for study in STUDIES:
        sub = questions[questions["source_study"] == study]

        if sub.empty:
            continue

        st.markdown(f"**{study}**")

        q_list = list(dict.fromkeys(sub["question"]))
        q_map = {q: f"Q{i + 1}" for i, q in enumerate(q_list)}
        sub = sub.assign(qid=sub["question"].map(q_map))

        with st.expander(f"Full question text — {study}"):
            for q, qid in q_map.items():
                st.markdown(f"**{qid}** — {q}")

        qids = [q_map[q] for q in q_list]
        fig = px.pie(
            sub,
            values="n",
            names="response",
            facet_col="qid",
            facet_col_wrap=3,
            color="response",
            color_discrete_map=RESPONSE_COLORS,
            category_orders={
                "response": ["Yes", "No", "Don't Know", "Not asked"],
                "qid": qids,
            },
            hover_data=["question"],
            height=420,
        )

        fig.update_traces(textposition="inside", textinfo="percent+label")

        fig.for_each_annotation(
            lambda a: a.update(text=a.text.split("qid=")[-1])
        )

        st.plotly_chart(fig, use_container_width=True)


# Symptom onset timeline
st.subheader("Symptom Onset Timeline — All Studies")
st.caption(
    "One point per reported episode. Subjects are linked across "
    "T002 and T006 by their shared SYN identifier, so all episodes "
    "for the same person appear on one line."
)

if onset.empty:
    st.info("No symptom onset records found in any study.")
else:
    onset["date"] = pd.to_datetime(
        onset["start_raw"], format="%d/%b/%Y", errors="coerce"
    )
    still_raw = onset["date"].isna()

    if still_raw.any():
        onset.loc[still_raw, "date"] = pd.to_datetime(
            onset.loc[still_raw, "start_raw"],
            format="%Y-%m-%d",
            errors="coerce",
        )

    unparsed = int(onset["date"].isna().sum())
    if unparsed:
        st.warning(
            f"{unparsed} onset date(s) could not be parsed "
            "and are excluded."
        )

    dated = onset.dropna(subset=["date"]).copy()
    dated["date_iso"] = dated["date"].dt.strftime("%Y-%m-%d")
    dated["person_num"] = pd.to_numeric(
        dated["person_id"].astype(str).str.extract(r"(\d+)$")[0],
        errors="coerce",
    )
    dated = dated.sort_values(
        ["person_num", "source_study", "date"],
        na_position="last",
    )

    missing = [s for s in STUDIES if s not in set(dated["source_study"])]
    if missing:
        st.info(
            "No onset-dated medical history symptoms were recorded "
            "for: " + ", ".join(missing) + "."
        )

    person_order = list(dict.fromkeys(dated["person_id"]))

    if not dated.empty:
        fig = px.scatter(
            dated,
            x="date",
            y="person_id",
            color="source_study",
            category_orders={"person_id": person_order[::-1]},
            hover_data={
                "term": True,
                "subjid": True,
                "date_iso": True,
                "visits": True,
                "source_study": True,
                "person_id": False,
                "date": False,
            },
            labels={
                "date": "Symptom start",
                "person_id": "Subject (linked)",
                "source_study": "Study",
                "visits": "Reported at visits",
            },
            title="Symptom onset by subject (linked across studies)",
        )
        fig.update_traces(marker=dict(size=10))
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            dated[["person_id", "source_study", "subjid", "term",
                   "visits", "date_iso"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "person_id": "Subject (linked)",
                "source_study": "Study",
                "subjid": "Study Subject ID",
                "term": "Condition / Question",
                "visits": "Reported at visits",
                "date_iso": "Start date (YYYY-MM-DD)",
            },
        )

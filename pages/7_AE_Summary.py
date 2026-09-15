"""
Haechan Choi
IVI Data Sceince & Innovations
This program creates the Adverse Events summary page for the dashboard.
"""

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from db import run_query
from sidebar_nav import render_sidebar
from auth_check import require_auth


render_sidebar(current_page="AE/SAE Summary")

st.title("Adverse Events Summary")
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

study = st.selectbox("Study", ["T002", "T005", "T006"])

with st.spinner("Loading AE data..."):
    ae_by_subject = run_query(
        "ae-by-subject",
        {"study": study}
    )
    severity = run_query(
        "ae-severity",
        {"study": study}
    )
    ae_events = run_query(
        "ae-events",
        {"study": study}
    )
    dose_kpi = (
        run_query("ae-dose-response") if study == "T002"
        else pd.DataFrame()
    )


if ae_by_subject.empty:
    st.warning(f"No AE records found for {study}.")
else:
    total_subjects = run_query(
        "enrolled-count",
        {"study": study}
    )["n"].iloc[0]

    pct = round(
        100 * len(ae_by_subject) / total_subjects, 1
    ) if total_subjects else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Subjects with ≥1 AE", len(ae_by_subject))
    col2.metric("% of enrolled subjects", f"{pct}%")
    col3.metric("Total AE count", int(ae_by_subject["num_ae"].sum()))
    col4.metric("Total SAE count", int(ae_by_subject["num_sae"].sum()))

    if study == "T002" and not dose_kpi.empty:
        dcols = st.columns(len(dose_kpi))
        for col, (_, r) in zip(dcols, dose_kpi.iterrows()):
            col.markdown(f"**Dose {int(r['dose_n'])}**")
            col.caption(
                f"{int(r['subjects_dosed'])} dosed · "
                f"{int(r['subjects_with_ae'])} with AE"
            )
            med = r["median_days_to_first_ae"]
            col.metric(
                "Median days to first AE",
                f"{med:.0f}" if pd.notna(med) else "—",
            )
            col.metric(
                "Avg AEs per subject",
                f"{r['avg_aes_per_subject']:.2f}",
            )

    if not severity.empty:
        fig = px.bar(
            severity,
            x="value",
            y="num_subjects",
            title=f"AE Severity Distribution — {study}",
        )
        st.plotly_chart(fig, use_container_width=True)

    ae_by_subject = ae_by_subject.sort_values("subjid")

    event = st.dataframe(
        ae_by_subject,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "subject_key": None,
            "subjid": "Subject ID",
            "num_ae": "Number of Adverse Events",
            "num_sae": st.column_config.NumberColumn(
                "Number of Serious AEs", format="%d"
            ),
        },
    )

    if event.selection.rows and not ae_events.empty:
        selected = ae_by_subject.iloc[event.selection.rows[0]]["subjid"]

        with st.expander(f"AE Details — {selected}", expanded=True):
            sub = ae_events[ae_events["subjid"] == selected].copy()
            sub["ae_date"] = pd.to_datetime(
                sub["ae_start"], format="%d/%b/%Y", errors="coerce"
            )
            sub = sub.sort_values("ae_date")

            for _, ev in sub.iterrows():
                line = (
                    f"**{ev['ae_term'] or 'AE'}** — "
                    f"started {ev['ae_start']}, "
                    f"severity {ev['severity']}, "
                    f"{ev['relation']}"
                )
                if ev["serious"] == "Y":
                    line += " **[SAE]**"
                st.write(line)

            dated = sub.dropna(subset=["ae_date"])
            if not dated.empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=[dated["ae_date"].min(), dated["ae_date"].max()],
                    y=[0, 0],
                    mode="lines",
                    line=dict(color="lightgray", width=2),
                    showlegend=False,
                    hoverinfo="skip",
                ))
                fig.add_trace(go.Scatter(
                    x=dated["ae_date"],
                    y=[0] * len(dated),
                    mode="markers+text",
                    showlegend=False,
                    marker=dict(
                        symbol="triangle-up",
                        size=12,
                        color=[
                            "crimson" if s == "Y" else "orange"
                            for s in dated["serious"]
                        ],
                    ),
                    text=dated["ae_term"],
                    textposition="top center",
                    hovertemplate="%{text}<br>%{x|%d %b %Y}",
                ))
                fig.update_layout(
                    title=f"AE Timeline — {selected}",
                    height=240,
                    xaxis=dict(title="Date"),
                    yaxis=dict(visible=False, range=[-1, 1]),
                )
                st.plotly_chart(fig, use_container_width=True)

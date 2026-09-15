"""
Haechan Choi
IVI Data Sceince & Innovations
This program creates the Subject Trace page for the dashboard.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from db import run_query
from sidebar_nav import render_sidebar
from auth_check import require_auth


render_sidebar(current_page="Subject Trace")

st.title("Cross-Study Subject Trace (STUDY_A ↔ STUDY_C)")
require_auth()

with st.spinner("Loading subject linkage data..."):
    linked = run_query(
        "linkage"
    )

if linked.empty:
    st.warning(
        "No cross-study linkage records found."
    )
else:
    selected_subjid = st.selectbox("Select subject (STUDY_A)",
                                   linked["STUDY_A_subjid"])

    with st.spinner("Building subject timeline..."):
        profile = run_query(
            "subject-profile",
            {"subjid": selected_subjid},
        )

        demographics = run_query(
                "subject-demographics",
                {"subjid": selected_subjid},
        )

    if profile.empty:
        st.warning("No profile data found for this subject.")
    else:
        if not demographics.empty:
            st.subheader("Subject Information")
            st.dataframe(
                demographics.T.rename(columns={0: " "}),
                use_container_width=True,
            )

        st.dataframe(
            profile.drop(columns=["ae_list"]).T.rename(columns={0: " "}),
            use_container_width=True,
        )
        ae_list_value = profile["ae_list"].iloc[0]
        if ae_list_value:
            st.subheader("Adverse Event Timeline")
            st.write(ae_list_value.replace(" → ", "  \n→ "))
        else:
            st.caption("No adverse events recorded for this subject.")

        events = run_query("subject-events", {"subjid": selected_subjid})

        if events.empty:
            st.caption("No dated dose/AE events to plot for this subject.")
        else:
            events["event_date"] = pd.to_datetime(events["event_date"])
            dose = events[events["event_type"] == "dose"]
            ae = events[events["event_type"] == "ae"]

            ae_hover = (
                ae["event_label"].fillna("AE")
                + " (" + ae["detail"].fillna("") + ")"
            )

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=[events["event_date"].min(), events["event_date"].max()],
                y=[0, 0],
                mode="lines",
                line=dict(color="lightgray", width=2),
                showlegend=False,
                hoverinfo="skip"
            ))

            fig.add_trace(go.Scatter(
                x=dose["event_date"], y=[0] * len(dose),
                mode="markers+text",
                name="Dose",
                marker=dict(symbol="circle", size=11, color="royalblue"),
                text=dose["event_label"],
                textposition="top center",
                hovertemplate="%{text}<br>%{x|%d %b %Y}<extra></extra>"
            ))

            fig.add_trace(go.Scatter(
                x=ae["event_date"], y=[0] * len(ae),
                mode="markers",
                name="Adverse event",
                marker=dict(
                    symbol="triangle-up",
                    size=12,
                    color=[
                        "crimson" if str(d).endswith("[SAE]") else "orange"
                        for d in ae["detail"]
                    ],
                ),
                text=ae_hover,
                textposition="bottom center",
                hovertemplate="%{text}<br>%{x|%d %b %Y}<extra></extra>",
            ))

            fig.update_layout(
                title=f"Event Timeline - {selected_subjid}",
                height=280,
                xaxis=dict(title="Date"),
                yaxis=dict(visible=False, range=[-1, 1]),
            )
            st.plotly_chart(fig, use_container_width=True)

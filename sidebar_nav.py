"""
Haechan Choi
IVI Data Sceince & Innovations
Shared sidebar navigation for all pages.
"""
import streamlit as st
from streamlit_option_menu import option_menu


PAGE_ROUTES = {
        "Home": "Home.py",
        "Enrollment & Eligibility": "pages/1_Enrollment_IE.py",
        "Physical Examination": "pages/2_Physical_Examination.py",
        "Medical History": "pages/3_Medical_History.py",
        "Concomitant Medication": "pages/4_Concomitant_Medication.py",
        "Vital Trends": "pages/5_Vital_Trends.py",
        "LB Summary": "pages/6_LB_Summary.py",
        "AE/SAE Summary": "pages/7_AE_Summary.py",
        "Subject Trace": "pages/8_Subject_Trace.py",
        "Data Quality": "pages/9_Data_Quality.py"
}

MENU_OPTIONS = list(PAGE_ROUTES.keys())
MENU_ICONS = ["house",
              "check2-circle",
              "clipboard2-pulse",
              "clock-history",
              "capsule-pill",
              "heart-pulse",
              "droplet",
              "shield-check",
              "person-vcard",
              "patch-check"]


def render_sidebar(current_page: str):

    roles = st.session_state.get("roles") or []

    options = list(MENU_OPTIONS)
    icons = list(MENU_ICONS)
    routes = dict(PAGE_ROUTES)

    if "admin" not in roles and "Data Quality" in options:
        i = options.index("Data Quality")
        options.pop(i)
        icons.pop(i)
        routes.pop("Data Quality")

    with st.sidebar:
        selected = option_menu(
            menu_title="Main Menu",
            options=MENU_OPTIONS,
            icons=MENU_ICONS,
            menu_icon="pc-display",
            default_index=MENU_OPTIONS.index(current_page),
            styles={
                "container": {"padding": "8px", "background-color": "#ffffff",
                              "border-radius": "16px"},
                "icon": {"color": "#333333", "font-size": "18px"},
                "nav-link": {"font-size": "15px", "text-align": "left",
                             "margin": "4px 0px", "border-radius": "10px",
                             "--hover-color": "#f5f5f5"},
                "nav-link-selected": {"background-color": "#36beef",
                                      "font-weight": "bold", "color": "white"}
            }
        )

    if selected != current_page:
        st.switch_page(PAGE_ROUTES[selected])

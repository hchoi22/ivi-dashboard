# CDISC-mapped Vi-DT Dashboard

This project is a Streamlit dashboard for exploring CDISC-mapped artificially generated clinical trial data across STUDY_A, STUDY_B, and STUDY_C. It's part of the clinical data mapping project for internal IVI clinical trials, and it demonstrates EAV-to-relational querying and cross-study analysis.

## 1. Pages Overview

| Page | Answers | Domain(s) | Endpoints |
|---|---|---|---|
| Enrollment & Eligibility | Which subjects met the eligibility criteria, and how many enrolled per study versus stopped at screening? | IE, subjects table | `/eligibility`, `/enrollment-summary` |
| Physical Examination | Which subjects had abnormal PE findings, per study? | PE | `/pe-abnormal` |
| Medical History | What medical history was reported per study, what share of STUDY_B/STUDY_C participants reported suspected typhoid, and when did symptoms start? | MH | `/mh-coverage`, `/mh-questions`, `/mh-onset` |
| Concomitant Medication | Which medications were taken and how often, and did SAE subjects also receive concomitant medication? | CM, AE | `/cm-coverage`, `/cm-freq`, `/cm-sae`, `/cm-typhoid-meds` |
| Vital Trends | How do heart rate, body temperature, weight, and height trend across visits, per study? | VS | `/vital-trends` |
| LB Summary | Which lab results fell outside the reference range, and how did they trend per subject over time? | LB | `/out-of-range-lb` |
| AE/SAE Summary | What share of subjects had at least one adverse event, how severe were they, and what does each subject's event timeline look like? | AE | `/ae-by-subject`, `/ae-severity`, `/ae-events`, `/enrolled-count` |
| Subject Trace | What's one participant's full dosing and adverse-event history, linked across STUDY_A and STUDY_C? | EX, AE, subject_linkage, DM | `/linkage`, `/subject-profile`, `/subject-demographics`, `/subject-events` |
| Data Quality (admin only) | Where is the data incomplete or suspect — missing values, missing visits, or out-of-range lab flags? | Multiple domains | `/dq-missingness`, `/dq-visit-completeness`, `/dq-lab-flags` |
## 2. Architecture

The dashboard follows a three-layer flow. Streamlit pages call db.py. The db.py calls FastAPI (api.py), and api.py queries Postgres. Each page imports a single function, run_query, and never touches a database connection or a SQL string directly.

This separation is deliberate, not incidental. db.py never writes raw SQL. It only calls named endpoints by name, over HTTP, and returns whatever JSON comes back as a DataFrame. Every query a page might need is written once in api.py as a named FastAPI route, and every page consumes that same tested query instead of writing its own. If a query's logic needs to change, or a bug in a GROUP BY needs fixing, it changes in exactly one place, and every page that depends on it is fixed at once.

This also means db.py stays deliberately thin: it's twelve lines, has no SQL in it at all, and its only real logic is a response-caching layer (@st.cache_data(ttl=600)) that keeps repeated page loads from re-querying Postgres every time a user switches tabs. This particular thinness is itself part of the design. It signals that query correctness and complexity live entirely in one auditable layer, api.py, rather than being spread thin across seven different page files that each might get it slightly wrong.

The same layer is also where cross-study standardization lives. STUDY_A, STUDY_B, and STUDY_C don't record the same question the same way. Some studies answer Y/N while others use coded values like 1/2, and date formats aren't consistent either. Rather than let every page guess at a study's encoding, this normalization happens once in the SQL itself, so a page never needs to know which study it's looking at to interpret a response correctly.

Access control follows the same one-place-to-fix philosophy. Every page calls require_auth() before rendering, and the shared sidebar_nav.py renders the menu based on the role stored in the user's session, so a page a user shouldn't see is never surfaced as a navigation option in the first place. The Data Quality page is the current example of this: it's restricted to admin users, since its KPIs are meant for reviewing the database itself rather than exploring the clinical data.

## 3. Tech Stack

- Dashboard: Streamlit, streamlit-option-menu
- Backend: FastAPI, SQLAlchemy, Postgres
- Data handling: pandas
- Environment/config: python-dotenv
- Python 3.13.5

## 4. Data Disclaimer

All data referenced and processed by this pipeline and dashboard is fully artificially generated, resemblling the structure of IVI's Vi-DT clinical study exports (STUDY_A, STUDY_B, STUDY_C) without containing any real participant information. No real subject identifiers, dates, or clinical values are included in this repository or its outputs. Source files themselves are not included in this repository due to data-sharing restrictions; this documentation describes the transformation logic, schema design, and mapping approach rather than providing a runnable end-to-end example.

## 5. Known Limitations / Next Steps

The dashboard surfaces a few gaps that come from the underlying data loads rather than the application code, and documenting them here is more useful than letting a reviewer discover them silently.

The most significant is the absence of treatment arm data. DM.ARMCD is not present in any of the current STUDY_A, STUDY_B, or STUDY_C loads, so cohort-level comparisons, such as comparing adverse event severity between a test group and a comparator group, aren't currently possible anywhere in the dashboard. This isn't a limitation of the schema or the API layer; both could support a cohort filter today if the underlying DM table carried an arm variable. It's a gap in the source data itself, and it's worth surfacing explicitly rather than treating the AE Summary page as if it already answers cohort-level questions.

A second, smaller gap is domain coverage. LB (Laboratory) is only collected in STUDY_A, so the LB Summary page will always show an empty result for those two studies. This is expected given the source studies, not a bug in the pipeline, and the page already displays that reasoning inline rather than failing silently.

A third limitation comes from the scope of the synthetic data itself rather than the pipeline or dashboard. The given synthetic data focuses on clinical structural data, screening, reactogenicity, and general safety records, rather than the explicit lab results tied to vaccine immunogenicity across each study phase. As a result, the dashboard's analysis stops at the reactogenicity level and does not cover seroconversion rates, which is a critical outcome measure for IVI's Vi-DT study. This isn't something the ETL pipeline or schema can fix on their own; it reflects what the source data currently contains, and any future load that includes immunogenicity/serology results would need corresponding LB-domain mapping before this dashboard could report on it.

A fourth limitation comes from how some standard variables were mapped rather than from the data itself. MHOCCUR and CMYN each carry several distinct questions within the same study, distinguished only by their standard_label rather than by separate variable names. This means any query against these variables has to filter on label text to isolate a single question, which works but is more fragile than filtering on a dedicated variable would be. Splitting these into sponsor-defined variables, similar to how CMFRQUNK is already handled, is planned cleanup rather than a change the dashboard needs to work around today.

A fifth limitation is specific to STUDY_A's medical history. Not every enrolled subject has an MH record, and the absence of a record isn't the same as an explicit "No". The source data simply doesn't say either way for those subjects. Rather than treat a missing record as a negative answer, the Medical History page counts it separately, displaying it as "Not recorded" against the full enrolled population instead of folding it into the "No" slice. This keeps the chart honest about what the data actually contains, even though it means the pie never resolves to a clean Yes/No split for STUDY_A.

Next steps that would close these gaps, if arm data becomes available in a future load: extend DM_COHORT-style logic already scoped for the AE Summary page to any page showing subject-level outcomes, and add a domain_registry-style check so pages that depend on a domain absent for a given study state that plainly instead of just rendering an empty chart.

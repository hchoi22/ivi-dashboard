"""
Haechan Choi
IVI Data Sceince & Innovations
FastAPI service sitting between the Streamlit dashboard and Postgres.
Every dashboard query stays here as a named endpoint.
db.py only ever calls these endpoints by name and never sends raw SQL.
"""

import os
import pandas as pd
from fastapi import FastAPI, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/ivi_synthetic_db",
)

# pre_ping avoids stale-connection errors after idle
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
app = FastAPI(title="IVI Dashboard API")


def run_sql(sql, params=None):
    """
    Execute a query and return JSON-safe records.
    Converts pandas NaN to None and casts through jsonable_encoder
    so decimal/date types from Postgres don't break FastAPI's JSON response.
    """

    df = pd.read_sql(sql, engine, params=params)
    df = df.astype(object).where(pd.notna(df), None)
    return jsonable_encoder(df.to_dict(orient="records"))


# Page 1: Inclusion and Exclusion Criteria Page
IE_QUERY = """
WITH target AS (
    SELECT CAST(%(study)s AS text) AS study_code
    ),
    STUDY_A_rows AS (
        SELECT i.subject_key,
            'OVERALL' AS category,
            CAST(NULL AS text) AS criterion_id,
            'Met all eligibility criteria' AS criterion,
            i.value AS answer,
            i.visitnum
        FROM ie AS i
        WHERE i.source_study = 'STUDY_A' AND i.standard_var = 'IEORRES'
    ),
    STUDY_A_reasons AS (
        SELECT i.subject_key, i.value AS reason
        FROM ie AS i
        WHERE i.source_study = 'STUDY_A'
        AND i.standard_var = 'SUPPIE'
        AND i.standard_label = 'Screening Failure Reason'
    ),
    STUDY_B_pivot AS (
        SELECT i.subject_key, i.seqnum,
            MAX(
                CASE WHEN i.standard_var = 'IECAT'
                THEN i.value
                END
            ) AS category,
            MAX(
                CASE WHEN i.standard_var = 'IETESTCD'
                THEN i.value
                END
            ) AS criterion_id,
            MAX(
                CASE WHEN i.standard_var = 'IETEST'
                THEN i.value
                END
            ) AS criterion,
            MAX(
                CASE WHEN i.standard_var = 'IEORRES'
                THEN i.value
                END
            ) AS answer,
            MAX(i.visitnum) AS visitnum
        FROM ie AS i
        WHERE i.source_study = 'STUDY_B'
        AND i.standard_var IN ('IECAT', 'IETESTCD', 'IETEST', 'IEORRES')
        GROUP BY i.subject_key, i.seqnum
    ),
    STUDY_B_rows AS (
        SELECT subject_key, category, criterion_id,
            criterion, answer, visitnum
        FROM STUDY_B_pivot
        WHERE criterion_id IS NOT NULL
    ),
    STUDY_C_rows AS (
        SELECT i.subject_key,
            CASE
                WHEN i.standard_label LIKE '%%immunized with any typhoid%%'
                    OR i.standard_label LIKE '%%Acute illnesses%%'
                THEN 'EXCLUSION'
                ELSE 'INCLUSION'
            END AS category,
            CAST(NULL AS text) AS criterion_id,
            TRIM(SUBSTRING(i.standard_label FROM '<(.*)>')) AS criterion,
            CASE i.value WHEN '1' THEN 'Yes' WHEN '2' THEN 'No'
                ELSE i.value END AS answer,
            i.visitnum
        FROM ie AS i
        WHERE i.source_study = 'STUDY_C'
            AND i.standard_var = 'IETEST'
    ),
    all_rows AS (
        SELECT * FROM STUDY_A_rows
        WHERE EXISTS (SELECT 1 FROM target WHERE study_code = 'STUDY_A')
        UNION ALL
        SELECT * FROM STUDY_B_rows
        WHERE EXISTS (SELECT 1 FROM target WHERE study_code = 'STUDY_B')
        UNION ALL
        SELECT * FROM STUDY_C_rows
        WHERE EXISTS (SELECT 1 FROM target WHERE study_code = 'STUDY_C')
)
SELECT s.subjid, s.scrno,
    a.category, a.criterion, a.answer,
    CASE
        WHEN a.category = 'EXCLUSION' THEN a.answer IN ('N', 'No')
        ELSE a.answer IN ('Y', 'Yes')
    END AS criterion_met,
    r.reason,
    a.visitnum
FROM all_rows AS a
JOIN subjects AS s
    ON s.subject_key = a.subject_key
LEFT JOIN STUDY_A_reasons AS r
    ON r.subject_key = a.subject_key
ORDER BY s.subjid, a.category DESC,
a.criterion_id NULLS LAST, a.visitnum;
"""

ENROLLMENT_QUERY = """
    SELECT
        source_study,
        COUNT(*) AS subject_count,
        COUNT(*) FILTER (WHERE subjid IS NOT NULL)
            AS subjects_with_subjid,
        COUNT(*) FILTER (WHERE subjid IS NULL AND scrno IS NOT NULL)
            AS scrno_only_subjects
    FROM subjects
    GROUP BY source_study
    ORDER BY source_study
"""


@app.get("/enrollment-summary")
def enrollment_summary():
    return run_sql(ENROLLMENT_QUERY)


@app.get("/eligibility")
def eligibility(study: str = Query(...)):
    return run_sql(IE_QUERY, {"study": study})


@app.get("/health")
def health():
    return {"status": "ok"}


# Page 2: Physical Examination Page
PE_ABNORMAL_QUERY = """
WITH STUDY_A AS (
    SELECT subject_key, seqnum, visitnum,
            MAX(CASE WHEN standard_var = 'PETEST'  THEN value END)
                AS body_system,
            MAX(CASE WHEN standard_var = 'PEORRES' THEN value END)
                AS result
    FROM pe
    WHERE source_study = 'STUDY_A'
    GROUP BY subject_key, seqnum, visitnum
    ),
    STUDY_BC AS (
        SELECT source_study, subject_key, visitnum,
                CASE source_study
                WHEN 'STUDY_B' THEN substring(standard_label from '<([^>]+)>')
                WHEN 'STUDY_C' THEN standard_label
                END AS body_system,
                value AS result
        FROM pe
        WHERE source_study IN ('STUDY_B', 'STUDY_C')
            AND standard_var = 'PEORRES'
    ),
    abnormal AS (
        SELECT 'STUDY_A' AS source_study, subject_key, visitnum, body_system
        FROM STUDY_A
        WHERE result = 'Abnormal'
        UNION ALL
        SELECT source_study, subject_key, visitnum, body_system
        FROM STUDY_BC
        WHERE result = 'Abnormal'
    )
SELECT source_study, visitnum,
       string_agg(DISTINCT body_system, ', '
       ORDER BY body_system) AS abnormal_systems,
       COUNT(DISTINCT subject_key) AS subjects_with_abnormal
FROM abnormal
GROUP BY source_study, visitnum
ORDER BY source_study, visitnum;
"""


@app.get("/pe-abnormal")
def pe_abnormal():
    return run_sql(PE_ABNORMAL_QUERY)


# Page 3: Medical History Page
MH_COVERAGE_QUERY = """
    SELECT source_study,
        COUNT(DISTINCT subject_key) AS subjects_with_mh,
        COUNT(DISTINCT (subject_key, seqnum)) AS mh_records
    FROM mh
    GROUP BY source_study
    ORDER BY source_study;
"""

MH_QUESTIONS_QUERY = """
    WITH norm AS (
        SELECT source_study, standard_label AS question, subject_key,
            CASE
                WHEN value IN ('Y', 'Yes', '1') THEN 'Yes'
                WHEN value IN ('N', 'No',  '2') THEN 'No'
                WHEN value = '9' THEN 'Don''t Know'
                ELSE value
            END AS response
        FROM mh
        WHERE standard_var = 'MHOCCUR'
    ),
    subj AS (
        -- one answer per participant per question: Yes wins if any
        -- visit says Yes, else No, else whatever remains
        SELECT source_study, question, subject_key,
            CASE
                WHEN BOOL_OR(response = 'Yes') THEN 'Yes'
                WHEN BOOL_OR(response = 'No') THEN 'No'
                ELSE MAX(response)
            END AS response
        FROM norm
        GROUP BY source_study, question, subject_key
    ),
    counts AS (
        SELECT source_study, question, response, COUNT(*) AS n
        FROM subj
        GROUP BY source_study, question, response
    ),
    enrolled AS (
        SELECT source_study, COUNT(*) AS n_subjects
        FROM subjects
        GROUP BY source_study
    ),
    not_recorded AS (
        -- enrolled participants with no row for this question at all
        SELECT c.source_study, c.question, 'Not recorded' AS response,
            e.n_subjects - SUM(c.n) AS n
        FROM counts AS c
        JOIN enrolled AS e ON e.source_study = c.source_study
        GROUP BY c.source_study, c.question, e.n_subjects
        HAVING e.n_subjects - SUM(c.n) > 0
    )
    SELECT source_study, question, response, n FROM counts
    UNION ALL
    SELECT source_study, question, response, n FROM not_recorded
    ORDER BY source_study, question, response;
"""

MH_ONSET_QUERY = """
    WITH starts AS (
        SELECT source_study, subject_key, seqnum, value AS start_raw
        FROM mh
        WHERE standard_var = 'MHSTDTC'
        AND source_study IN ('STUDY_A', 'STUDY_B', 'STUDY_C')
    ),
    terms AS (
        SELECT source_study, subject_key, seqnum, visitnum,
            CASE
                WHEN source_study = 'STUDY_A'
                THEN value
                ELSE standard_label
            END AS term
        FROM mh
        WHERE standard_var = 'MHTERM'
        AND source_study IN ('STUDY_A', 'STUDY_B', 'STUDY_C')
    )
    SELECT t.source_study, s.subjid,
        COALESCE(substring(s.subjid FROM 'SYN-[0-9]+$'), s.subjid)
            AS person_id,
        t.term, st.start_raw,
        STRING_AGG(
            DISTINCT CAST(t.visitnum AS INTEGER)::text, ', '
            ORDER BY CAST(t.visitnum AS INTEGER)::text
        ) AS visits
    FROM terms AS t
    JOIN starts AS st
        ON st.source_study = t.source_study
        AND st.subject_key = t.subject_key
        AND st.seqnum = t.seqnum
    JOIN subjects AS s ON s.subject_key = t.subject_key
    GROUP BY t.source_study, s.subjid, person_id, t.term, st.start_raw
    ORDER BY person_id, t.source_study, st.start_raw;
"""


@app.get("/mh-coverage")
def mh_coverage():
    return run_sql(MH_COVERAGE_QUERY)


@app.get("/mh-questions")
def mh_questions():
    return run_sql(MH_QUESTIONS_QUERY)


@app.get("/mh-onset")
def mh_onset():
    return run_sql(MH_ONSET_QUERY)


# Page 4: Concomitant Medication
CM_COVERAGE_QUERY = """
    SELECT source_study,
       COUNT(DISTINCT subject_key)
           FILTER (WHERE standard_var = 'CMTRT') AS subjects_with_cm,
       COUNT(*) FILTER (WHERE standard_var = 'CMTRT') AS cm_records,
       COUNT(DISTINCT value) FILTER (WHERE standard_var = 'CMTRT')
           AS distinct_meds
    FROM cm
    GROUP BY source_study
    ORDER BY source_study;
"""

CM_FREQ_QUERY = """
    SELECT source_study, value AS medication,
        COUNT(*) AS records,
        COUNT(DISTINCT subject_key) AS subjects
    FROM cm
    WHERE standard_var = 'CMTRT'
    GROUP BY source_study, value
    ORDER BY source_study, subjects DESC;
"""

CM_SAE_QUERY = """
    WITH sae AS (
        SELECT DISTINCT subject_key
        FROM ae
        WHERE standard_var = 'AESER' AND value IN ('Y', 'Yes', '1')
    ),
    meds AS (
        SELECT subject_key, value AS medication
        FROM cm
        WHERE standard_var = 'CMTRT'
    )
    SELECT s.subjid,
        COUNT(DISTINCT m.medication) AS n_distinct_meds,
        STRING_AGG(DISTINCT m.medication, ', '
                    ORDER BY m.medication) AS medications
    FROM sae
    JOIN subjects AS s ON s.subject_key = sae.subject_key
    LEFT JOIN meds AS m ON m.subject_key = sae.subject_key
    GROUP BY s.subjid
    ORDER BY s.subjid;
"""

CM_TYPHOID_MED_QUERY = """
    SELECT took_med, COUNT(*) AS subjects
    FROM (
        SELECT subject_key,
            BOOL_OR(value IN ('Y', 'Yes', '1')) AS took_med
        FROM cm
        WHERE source_study = 'STUDY_C' AND standard_var = 'CMYN'
        GROUP BY subject_key
    ) AS s
    GROUP BY took_med
    ORDER BY took_med DESC;
"""

CM_MED_COUNT_BUCKETS_QUERY = """
    WITH per_subject AS (
        SELECT s.source_study, s.subject_key,
            COUNT(DISTINCT c.value) AS n_meds
        FROM subjects AS s
        LEFT JOIN cm AS c
        ON c.subject_key = s.subject_key
        AND c.source_study = s.source_study
        AND c.standard_var = 'CMTRT'
        GROUP BY s.source_study, s.subject_key
    ),
    bucketed AS (
        -- bucket edges: adjust here only if the ranges need to change
        SELECT source_study,
            CASE
                WHEN n_meds = 0 THEN '0'
                WHEN n_meds BETWEEN 1 AND 3 THEN '1-3'
                WHEN n_meds BETWEEN 4 AND 6 THEN '4-6'
                ELSE '7+'
            END AS med_bucket
        FROM per_subject
    )
    SELECT source_study, med_bucket, COUNT(*) AS n_subjects
    FROM bucketed
    GROUP BY source_study, med_bucket
    ORDER BY source_study,
            CASE med_bucket
                WHEN '0' THEN 0 WHEN '1-3' THEN 1
                WHEN '4-6' THEN 2 ELSE 3
            END;
"""

CM_TYPHOID_MED_LIST_QUERY = """
    SELECT s.subjid,
        STRING_AGG(DISTINCT c.value, ', ' ORDER BY c.value) AS medications,
        COUNT(DISTINCT c.value) AS n_meds
    FROM cm AS c
    JOIN subjects AS s ON s.subject_key = c.subject_key
    WHERE c.source_study = 'STUDY_C' AND c.standard_var = 'CMTRT'
    GROUP BY s.subjid
    ORDER BY s.subjid;
"""

CM_STUDY_B_DETAIL_QUERY = """
    WITH meds AS (
        SELECT subject_key,
            STRING_AGG(DISTINCT value, ', ' ORDER BY value) AS medications,
            COUNT(DISTINCT value) AS n_meds
        FROM cm
        WHERE source_study = 'STUDY_B' AND standard_var = 'CMTRT'
        GROUP BY subject_key
    ),
    screen AS (
        SELECT subject_key,
            BOOL_OR(value IN ('Y', 'Yes', '1')) AS answered_yes,
            BOOL_OR(value IN ('N', 'No', '2')) AS answered_no
        FROM cm
        WHERE source_study = 'STUDY_B' AND standard_var = 'CMYN'
        GROUP BY subject_key
    )
    SELECT s.subjid,
        COALESCE(m.medications, '-') AS medications,
        COALESCE(m.n_meds, 0) AS n_meds,
        CASE
            WHEN m.n_meds > 0 THEN 'Medication recorded'
            WHEN sc.answered_no THEN 'No medication (confirmed)'
            WHEN sc.answered_yes THEN 'Yes (unspecified)'
            ELSE 'Not recorded'
        END AS status
    FROM subjects AS s
    LEFT JOIN meds AS m
        ON m.subject_key = s.subject_key
    LEFT JOIN screen AS sc
        ON sc.subject_key = s.subject_key
    WHERE s.source_study = 'STUDY_B'
        AND (m.n_meds > 0 OR sc.answered_yes OR sc.answered_no)
    ORDER BY s.subjid;
"""


@app.get("/cm-STUDY_B-detail")
def cm_STUDY_B_detail():
    return run_sql(CM_STUDY_B_DETAIL_QUERY)


@app.get("/cm-typhoid-med-list")
def cm_typhoid_med_list():
    return run_sql(CM_TYPHOID_MED_LIST_QUERY)


@app.get("/cm-med-count-buckets")
def cm_med_count_buckets():
    return run_sql(CM_MED_COUNT_BUCKETS_QUERY)


@app.get("/cm-coverage")
def cm_coverage():
    return run_sql(CM_COVERAGE_QUERY)


@app.get("/cm-freq")
def cm_freq():
    return run_sql(CM_FREQ_QUERY)


@app.get("/cm-sae")
def cm_sae():
    return run_sql(CM_SAE_QUERY)


@app.get("/cm-typhoid-meds")
def cm_typhoid_meds():
    return run_sql(CM_TYPHOID_MED_QUERY)


# Page 5: Vital Signs
VS_QUERY = r"""
    WITH target AS (
        SELECT CAST(%(study)s AS text) AS study_code
        ),
        STUDY_A_tests AS (
            SELECT subject_key, visitnum,
                value AS test_name,
                ROW_NUMBER() OVER (
                    PARTITION BY subject_key, visitnum
                    ORDER BY fact_id
                ) AS rn
            FROM vs
            WHERE source_study = 'STUDY_A'
                AND standard_var = 'VSTEST'
        ),
        STUDY_A_results AS (
            SELECT subject_key, visitnum,
                value AS result,
                ROW_NUMBER() OVER (
                    PARTITION BY subject_key, visitnum
                    ORDER BY fact_id
                ) AS rn
            FROM vs
            WHERE source_study = 'STUDY_A'
                AND standard_var = 'VSORRES'
        ),
        STUDY_A_units AS (
            SELECT subject_key, visitnum,
                value AS unit,
                ROW_NUMBER() OVER (
                    PARTITION BY subject_key, visitnum
                    ORDER BY fact_id
                ) AS rn
            FROM vs
            WHERE source_study = 'STUDY_A'
                AND standard_var = 'VSORRESU'
        ),
        STUDY_A_measurements AS (
            SELECT 'STUDY_A' AS source_study, r.subject_key, r.visitnum,
                t.test_name, r.result, u.unit
            FROM STUDY_A_results AS r
            JOIN STUDY_A_tests AS t
                ON t.subject_key = r.subject_key
                AND t.visitnum IS NOT DISTINCT FROM r.visitnum
                AND t.rn = r.rn
            LEFT JOIN STUDY_A_units AS u
                ON u.subject_key = r.subject_key
                AND u.visitnum IS NOT DISTINCT FROM r.visitnum
                AND u.rn = r.rn
            WHERE EXISTS (
                SELECT 1
                FROM target
                WHERE study_code IS NULL
                    OR study_code = 'STUDY_A'
            )
        ),
        STUDY_BC_measurements AS (
            SELECT v.source_study, v.subject_key, v.visitnum,
                v.standard_label AS test_name,
                v.value AS result,
                COALESCE(
                    u.value,
                    SUBSTRING(v.standard_label FROM '\(([^)]+)\)')
                ) AS unit
            FROM vs AS v
            LEFT JOIN vs AS u
                ON u.source_study = v.source_study
                AND u.subject_key = v.subject_key
                AND u.visitnum IS NOT DISTINCT FROM v.visitnum
                AND u.standard_var = 'VSORRESU'
                AND UPPER(REGEXP_REPLACE(u.standard_label,
                    '\s+unit$', '', 'i')) = UPPER(v.standard_label)
            WHERE v.source_study IN ('STUDY_B', 'STUDY_C')
                AND v.standard_var = 'VSORRES'
                AND EXISTS (
                    SELECT 1
                    FROM target
                    WHERE study_code IS NULL OR study_code = v.source_study
                )
        ),
        all_measurements AS (
            SELECT * FROM STUDY_A_measurements
            UNION ALL
            SELECT * FROM STUDY_BC_measurements
        ),
        labeled AS (
            SELECT *,
                CASE
                    WHEN UPPER(test_name) LIKE '%%HEART%%RATE%%'
                        THEN 'Heart rate'
                    WHEN UPPER(test_name) LIKE '%%TEMP%%'
                        THEN 'Body temperature'
                    WHEN UPPER(test_name) LIKE '%%HEIGHT%%'
                        THEN 'Height'
                    WHEN UPPER(test_name) LIKE '%%WEIGHT%%'
                        THEN 'Weight'
                END AS test_display
            FROM all_measurements
            WHERE result ~ '^\s*\d+(\.\d+)?\s*$'
        )
    SELECT source_study, visitnum, test_display, unit,
        COUNT(*) AS n_measurements,
        COUNT(DISTINCT subject_key) AS n_subjects,
        ROUND(AVG(result::numeric), 1) AS avg_value,
        ROUND(STDDEV(result::numeric), 2) AS sd
    FROM labeled
    WHERE test_display IS NOT NULL
    GROUP BY source_study, visitnum, test_display, unit
    ORDER BY source_study, test_display, visitnum
"""

# Pivots the DM domain EAV rows for one subject back into a single
# wide row so the Subject Trace page can show age/sex.
DEMOGRAPHICS_QUERY = """
SELECT
    sj.subjid,
    MAX(CASE WHEN dm.standard_var = 'AGE' THEN dm.value END) AS age,
    MAX(CASE WHEN dm.standard_var = 'AGEU' THEN dm.value END) AS age_unit,
    MAX(CASE WHEN dm.standard_var = 'SEX' THEN dm.value END) AS sex
FROM dm
JOIN subjects AS sj
    ON dm.subject_key = sj.subject_key
WHERE dm.source_study = 'STUDY_A'
    AND sj.subjid = %(subjid)s
GROUP BY sj.subjid;
"""


@app.get("/vital-trends")
def vital_trends(study: str = Query(...)):
    return run_sql(VS_QUERY, {"study": study})


@app.get("/subject-demographics")
def subject_demographics(subjid: str = Query(...)):
    return run_sql(DEMOGRAPHICS_QUERY, {"subjid": subjid})


# Page 4: Lab Summary Page
# Pivots each lab result's EAV rows
# back into one row per lab draw, then filters to only the results
# flagged High or Low for the data-quality/safety review page.
OOR_QUERY = """
    WITH m AS (
    SELECT subject_key, seqnum, visitnum,
            MAX(CASE WHEN standard_var = 'LBTEST' THEN value END)
                AS test_name,
            MAX(CASE WHEN standard_var = 'LBORRES' THEN value END)
                AS result,
            MAX(CASE WHEN standard_var = 'LBORRESU' THEN value END)
                AS unit,
            MAX(CASE WHEN standard_var = 'LBNRIND' THEN value END)
                AS flag,
            MAX(CASE WHEN standard_var = 'LBORNRLO' THEN value END)
                AS ref_low,
            MAX(CASE WHEN standard_var = 'LBORNRHI' THEN value END)
                AS ref_high,
            MAX(CASE WHEN standard_var = 'LBDTC' THEN value END)
                AS assessed
    FROM lb
    WHERE source_study = %(study)s
    GROUP BY subject_key, seqnum, visitnum
)
SELECT subject_key, visitnum, test_name, result, unit, flag,
        ref_low, ref_high, assessed
FROM m
WHERE flag IN ('Low', 'High')
ORDER BY subject_key, visitnum, seqnum
"""


@app.get("/out-of-range-lb")
def out_of_range_lb(study: str = Query(...)):
    return run_sql(OOR_QUERY, {"study": study})


# Page 7: AE Summary
AE_BY_SUBJECT_QUERY = """
    SELECT a.subject_key, s.subjid,
       COUNT(DISTINCT a.seqnum) AS num_ae,
       COUNT(DISTINCT a.seqnum) FILTER (
           WHERE a.standard_var = 'AESER' AND a.value = 'Y'
       ) AS num_sae
    FROM ae AS a
    JOIN subjects AS s
        ON s.subject_key = a.subject_key
    WHERE a.source_study = %(study)s
      AND NOT EXISTS (
          SELECT 1 FROM ae AS r
          WHERE r.subject_key = a.subject_key
            AND r.seqnum = a.seqnum
            AND r.standard_var = 'AEREFID'
      )
    GROUP BY a.subject_key, s.subjid
    ORDER BY num_ae DESC, s.subjid;
"""

AE_SEVERITY_QUERY = """
    SELECT value, COUNT(DISTINCT subject_key) AS num_subjects
    FROM ae AS a
    WHERE a.source_study = %(study)s AND a.standard_var = 'AESEV'
      AND NOT EXISTS (
          SELECT 1 FROM ae AS r
          WHERE r.subject_key = a.subject_key
            AND r.seqnum = a.seqnum
            AND r.standard_var = 'AEREFID'
      )
    GROUP BY value;
"""

ENROLLED_COUNT_QUERY = """
    SELECT COUNT(*) AS n
    FROM subjects
    WHERE source_study = %(study)s AND subjid IS NOT NULL
"""

AE_EVENTS_QUERY = """
    SELECT a.subject_key, s.subjid, a.seqnum,
        MAX(CASE WHEN a.standard_var = 'AETERM' THEN a.value END) AS ae_term,
        MAX(CASE WHEN a.standard_var = 'AESTDTC' THEN a.value END) AS ae_start,
        MAX(CASE WHEN a.standard_var = 'AESEV' THEN a.value END) AS severity,
        MAX(CASE WHEN a.standard_var = 'AEREL' THEN a.value END) AS relation,
        MAX(CASE WHEN a.standard_var = 'AESER' THEN a.value END) AS serious
    FROM ae AS a
    JOIN subjects AS s
        ON s.subject_key = a.subject_key
    WHERE a.source_study = %(study)s
    AND NOT EXISTS (
        SELECT 1 FROM ae AS r
        WHERE r.subject_key = a.subject_key
            AND r.seqnum = a.seqnum
            AND r.standard_var = 'AEREFID'
    )
    GROUP BY a.subject_key, s.subjid, a.seqnum
    ORDER BY s.subjid, a.seqnum;
"""

AE_DOSE_RESPONSE_QUERY = """
WITH doses AS (
    SELECT e.subject_key,
           CASE e.visitnum WHEN 2 THEN 1 WHEN 6 THEN 2
                WHEN 11 THEN 3 END AS dose_n,
           TO_DATE(MAX(CASE WHEN e.standard_var = 'EXSTDTC'
                            THEN e.value END), 'DD/MON/YYYY')
               AS dose_date
    FROM ex AS e
    WHERE e.source_study = 'STUDY_A' AND e.visitnum IN (2, 6, 11)
    GROUP BY e.subject_key, e.seqnum, e.visitnum
),
windows AS (
    SELECT subject_key, dose_n, dose_date,
           LEAD(dose_date) OVER (
               PARTITION BY subject_key ORDER BY dose_date
           ) AS window_end
    FROM doses
    WHERE dose_date IS NOT NULL
),
ae_starts AS (
    SELECT a.subject_key, a.seqnum,
           TO_DATE(MAX(CASE WHEN a.standard_var = 'AESTDTC'
                            THEN a.value END), 'DD/MON/YYYY')
               AS ae_start
    FROM ae AS a
    WHERE a.source_study = 'STUDY_A'
      AND NOT EXISTS (
          SELECT 1 FROM ae AS r
          WHERE r.subject_key = a.subject_key
            AND r.seqnum = a.seqnum
            AND r.standard_var = 'AEREFID'
      )
    GROUP BY a.subject_key, a.seqnum
),
window_aes AS (
    SELECT w.subject_key, w.dose_n, s.ae_start,
           s.ae_start - w.dose_date AS days_after
    FROM windows AS w
    JOIN ae_starts AS s
      ON s.subject_key = w.subject_key
     AND s.ae_start >= w.dose_date
     AND (w.window_end IS NULL OR s.ae_start < w.window_end)
),
first_ae AS (
    SELECT subject_key, dose_n, MIN(days_after) AS days_to_first
    FROM window_aes
    GROUP BY subject_key, dose_n
),
agg_window AS (
    SELECT w.dose_n,
           COUNT(DISTINCT w.subject_key) AS subjects_dosed,
           COUNT(DISTINCT wa.subject_key) AS subjects_with_ae,
           COUNT(wa.ae_start) AS total_aes
    FROM windows AS w
    LEFT JOIN window_aes AS wa
      ON wa.subject_key = w.subject_key AND wa.dose_n = w.dose_n
    GROUP BY w.dose_n
),
agg_first AS (
    SELECT dose_n,
           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_to_first)
               AS median_days_to_first_ae,
           ROUND(AVG(days_to_first)::numeric, 1) AS mean_days_to_first_ae
    FROM first_ae
    GROUP BY dose_n
)
SELECT a.dose_n, a.subjects_dosed, a.subjects_with_ae, a.total_aes,
       ROUND(a.total_aes::numeric / a.subjects_dosed, 2)
           AS avg_aes_per_subject,
       f.median_days_to_first_ae, f.mean_days_to_first_ae
FROM agg_window AS a
LEFT JOIN agg_first AS f ON f.dose_n = a.dose_n
ORDER BY a.dose_n;
"""


@app.get("/ae-dose-response")
def ae_dose_response():
    return run_sql(AE_DOSE_RESPONSE_QUERY)


@app.get("/ae-events")
def ae_events(study: str = Query(...)):
    return run_sql(AE_EVENTS_QUERY, {"study": study})


@app.get("/ae-by-subject")
def ae_by_subject(study: str = Query(...)):
    return run_sql(AE_BY_SUBJECT_QUERY, {"study": study})


@app.get("/ae-severity")
def ae_severity(study: str = Query(...)):
    return run_sql(AE_SEVERITY_QUERY, {"study": study})


@app.get("/enrolled-count")
def enrolled_count(study: str = Query(...)):
    return run_sql(ENROLLED_COUNT_QUERY, {"study": study})


# Page 8: Subject Trace Query
LINKAGE_QUERY = """
    SELECT sA.subject_key AS STUDY_A_subject_key, sA.subjid AS STUDY_A_subjid
    FROM subjects sA
    JOIN subjects sC
        ON sC.source_study = 'STUDY_C'
        AND substring(sC.subjid FROM 'SYN-\\d+$')
            = substring(sA.subjid FROM 'SYN-\\d+$')
    WHERE sA.source_study = 'STUDY_A'
    ORDER BY sA.subjid
"""

# Using the linkage, creating a profile table per participant
# about their dosing and their adverse event records.
PROFILE_QUERY = """
    WITH linkage_subject AS (
        SELECT sA.subject_key AS sA_sk, sC.subject_key AS sC_sk,
                sC.record_id
        FROM subjects AS sA
        JOIN subjects AS sC
            ON sC.source_study = 'STUDY_C'
            AND substring(sC.subjid FROM 'SYN-\\d+$')
                = substring(sA.subjid FROM 'SYN-\\d+$')
        WHERE sA.source_study = 'STUDY_A' AND sA.subjid = %(subjid)s
    ),
    dosing AS (
        SELECT e.subject_key,
            CASE e.visitnum
                WHEN 2 THEN 1
                WHEN 6 THEN 2
                WHEN 11 THEN 3 END AS dose_n,
            TO_DATE(MAX(CASE WHEN e.standard_var = 'EXSTDTC'
                                THEN e.value END), 'DD/MON/YYYY')
                AS dose_date,
            MAX(CASE WHEN e.standard_var = 'EXTRT'
                        THEN e.value END) AS treatment
        FROM ex AS e
        WHERE e.source_study = 'STUDY_A'
        GROUP BY e.subject_key, e.seqnum, e.visitnum
    ),
    ae_events AS (
        SELECT subject_key, seqnum,
            TO_DATE(MAX(CASE WHEN standard_var = 'AESTDTC'
                            THEN value END), 'DD/MON/YYYY')
                AS ae_start,
            MAX(CASE WHEN standard_var = 'AETERM' THEN value END)
                AS ae_name,
            MAX(CASE WHEN standard_var = 'AESEV' THEN value END)
                AS severity,
            MAX(CASE WHEN standard_var = 'AEREL' THEN value END)
                AS relation,
            MAX(CASE WHEN standard_var = 'AESER' THEN value END)
                AS serious
        FROM ae
        WHERE source_study = 'STUDY_A'
        GROUP BY subject_key, seqnum
    ),
    ae_summary AS (
        SELECT subject_key,
            COUNT(*) AS ae_count,
            COUNT(*) FILTER (WHERE serious = 'Y') AS sae_count,
            string_agg(
                TO_CHAR(ae_start, 'DD-MON-YYYY') || ': ' || ae_name ||
                ' (' || severity || ', ' || relation || ')' ||
                CASE WHEN serious = 'Y' THEN ' [SAE]' ELSE '' END,
                ' → '
                ORDER BY ae_start, seqnum
            ) AS ae_list
        FROM ae_events
        GROUP BY subject_key
    )
    SELECT l.sA_sk AS STUDY_A_subject_key, l.sC_sk AS STUDY_C_subject_key,
        l.record_id,
        MAX(CASE WHEN d.dose_n = 1 THEN d.dose_date END)
            AS dose_1_date,
        MAX(CASE WHEN d.dose_n = 2 THEN d.dose_date END)
            AS dose_2_date,
        MAX(CASE WHEN d.dose_n = 3 THEN d.dose_date END)
            AS dose_3_date,
        COALESCE(a.ae_count, 0) AS ae_count,
        COALESCE(a.sae_count, 0) AS sae_count,
        a.ae_list
    FROM linkage_subject AS l
    LEFT JOIN dosing AS d
        ON d.subject_key = l.sA_sk
    LEFT JOIN ae_summary AS a
        ON a.subject_key = l.sA_sk
    GROUP BY l.sA_sk, l.sC_sk, l.record_id,
        a.ae_count, a.sae_count, a.ae_list
"""

# Builds the single subject's timeline (doses + AEs) shown on the
# Subject Trace page's event chart
EVENTS_QUERY = """
    WITH dose AS (
        SELECT 'Dose '
            || CASE e.visitnum WHEN 2 THEN 1 WHEN 6 THEN 2 WHEN 11 THEN 3 END
                AS event_label,
            TO_DATE(MAX(CASE WHEN e.standard_var = 'EXSTDTC' THEN e.value END),
                    'DD/MON/YYYY') AS event_date,
            'dose' AS event_type,
            CAST(NULL AS text) AS detail
        FROM ex AS e
        JOIN subjects AS s ON s.subject_key = e.subject_key
        WHERE e.source_study = 'STUDY_A'
        AND s.subjid = %(subjid)s
        AND e.visitnum IN (2, 6, 11)
        GROUP BY e.subject_key, e.seqnum, e.visitnum
    ),
    ae AS (
        SELECT MAX(CASE WHEN a.standard_var = 'AETERM' THEN a.value END)
                AS event_label,
            TO_DATE(MAX(CASE WHEN a.standard_var = 'AESTDTC' THEN a.value END),
                    'DD/MON/YYYY') AS event_date,
            'ae' AS event_type,
            MAX(CASE WHEN a.standard_var = 'AESEV' THEN a.value END)
                || ', ' || MAX(CASE WHEN a.standard_var = 'AEREL'
                            THEN a.value END)
                || CASE WHEN MAX(CASE WHEN a.standard_var = 'AESER'
                                    THEN a.value END) = 'Y'
                        THEN ' [SAE]' ELSE '' END AS detail
        FROM ae AS a
        JOIN subjects AS s ON s.subject_key = a.subject_key
        WHERE a.source_study = 'STUDY_A'
        AND s.subjid = %(subjid)s
        GROUP BY a.subject_key, a.seqnum
    )
    SELECT event_type, event_label, event_date, detail
    FROM (SELECT * FROM dose UNION ALL SELECT * FROM ae) AS ev
    WHERE event_date IS NOT NULL
    ORDER BY event_date;
"""


@app.get("/linkage")
def linkage():
    return run_sql(LINKAGE_QUERY)


@app.get("/subject-profile")
def subject_profile(subjid: str = Query(...)):
    return run_sql(PROFILE_QUERY, {"subjid": subjid})


@app.get("/subject-events")
def subject_events(subjid: str = Query(...)):
    return run_sql(EVENTS_QUERY, {"subjid": subjid})


# Page 9: Data Quality
# Admin-only QA metrics, all computed from the existing EAV domain
# tables -- no new data loading required.

# Checking for empty rows in the DB
DQ_MISSINGNESS_QUERY = """
    SELECT source_study, 'ae' AS domain, COUNT(*) AS total_rows,
        COUNT(*) FILTER (WHERE value IS NULL OR btrim(value) = '')
            AS empty_rows
    FROM ae GROUP BY source_study
    UNION ALL
    SELECT source_study, 'be', COUNT(*),
        COUNT(*) FILTER (WHERE value IS NULL OR btrim(value) = '')
    FROM be GROUP BY source_study
    UNION ALL
    SELECT source_study, 'bs', COUNT(*),
        COUNT(*) FILTER (WHERE value IS NULL OR btrim(value) = '')
    FROM bs GROUP BY source_study
    UNION ALL
    SELECT source_study, 'cm', COUNT(*),
        COUNT(*) FILTER (WHERE value IS NULL OR btrim(value) = '')
    FROM cm GROUP BY source_study
    UNION ALL
    SELECT source_study, 'co', COUNT(*),
        COUNT(*) FILTER (WHERE value IS NULL OR btrim(value) = '')
    FROM co GROUP BY source_study
    UNION ALL
    SELECT source_study, 'dm', COUNT(*),
        COUNT(*) FILTER (WHERE value IS NULL OR btrim(value) = '')
    FROM dm GROUP BY source_study
    UNION ALL
    SELECT source_study, 'ds', COUNT(*),
        COUNT(*) FILTER (WHERE value IS NULL OR btrim(value) = '')
    FROM ds GROUP BY source_study
    UNION ALL
    SELECT source_study, 'eos', COUNT(*),
        COUNT(*) FILTER (WHERE value IS NULL OR btrim(value) = '')
    FROM eos GROUP BY source_study
    UNION ALL
    SELECT source_study, 'ex', COUNT(*),
        COUNT(*) FILTER (WHERE value IS NULL OR btrim(value) = '')
    FROM ex GROUP BY source_study
    UNION ALL
    SELECT source_study, 'ie', COUNT(*),
        COUNT(*) FILTER (WHERE value IS NULL OR btrim(value) = '')
    FROM ie GROUP BY source_study
    UNION ALL
    SELECT source_study, 'lb', COUNT(*),
        COUNT(*) FILTER (WHERE value IS NULL OR btrim(value) = '')
    FROM lb GROUP BY source_study
    UNION ALL
    SELECT source_study, 'mh', COUNT(*),
        COUNT(*) FILTER (WHERE value IS NULL OR btrim(value) = '')
    FROM mh GROUP BY source_study
    UNION ALL
    SELECT source_study, 'pe', COUNT(*),
        COUNT(*) FILTER (WHERE value IS NULL OR btrim(value) = '')
    FROM pe GROUP BY source_study
    UNION ALL
    SELECT source_study, 'sv', COUNT(*),
        COUNT(*) FILTER (WHERE value IS NULL OR btrim(value) = '')
    FROM sv GROUP BY source_study
    UNION ALL
    SELECT source_study, 'vs', COUNT(*),
        COUNT(*) FILTER (WHERE value IS NULL OR btrim(value) = '')
    FROM vs GROUP BY source_study
    ORDER BY source_study, domain;
"""

# Visit completeness: distinct visitnums recorded per subject across
# all domain tables, compared against each study's
# expected schedule.
DQ_VISIT_COMPLETENESS_QUERY = """
    WITH expected AS (
            SELECT 'STUDY_A' AS source_study, 13 AS expected_visits
            UNION ALL SELECT 'STUDY_B', 3
            UNION ALL SELECT 'STUDY_C', 3
        ),
        visits AS (
            SELECT source_study, subject_key, visitnum
            FROM ae
            WHERE visitnum IS NOT NULL
            UNION
                SELECT source_study, subject_key, visitnum
                FROM be
                WHERE visitnum IS NOT NULL
            UNION
                SELECT source_study, subject_key, visitnum
                FROM bs
                WHERE visitnum IS NOT NULL
            UNION
                SELECT source_study, subject_key, visitnum
                FROM cm
                WHERE visitnum IS NOT NULL
            UNION
                SELECT source_study, subject_key, visitnum
                FROM co
                WHERE visitnum IS NOT NULL
            UNION
                SELECT source_study, subject_key, visitnum
                FROM dm
                WHERE visitnum IS NOT NULL
            UNION
                SELECT source_study, subject_key, visitnum
                FROM ds
                WHERE visitnum IS NOT NULL
            UNION
                SELECT source_study, subject_key, visitnum
                FROM eos
                WHERE visitnum IS NOT NULL
            UNION
                SELECT source_study, subject_key, visitnum
                FROM ex
                WHERE visitnum IS NOT NULL
            UNION
                SELECT source_study, subject_key, visitnum
                FROM ie
                WHERE visitnum IS NOT NULL
            UNION
                SELECT source_study, subject_key, visitnum
                FROM lb
                WHERE visitnum IS NOT NULL
            UNION
                SELECT source_study, subject_key, visitnum
                FROM mh
                WHERE visitnum IS NOT NULL
            UNION
                SELECT source_study, subject_key, visitnum
                FROM pe
                WHERE visitnum IS NOT NULL
            UNION
                SELECT source_study, subject_key, visitnum
                FROM sv
                WHERE visitnum IS NOT NULL
            UNION
                SELECT source_study, subject_key, visitnum
                FROM vs
                WHERE visitnum IS NOT NULL
        ),
        per_subject AS (
            SELECT source_study, subject_key,
                COUNT(DISTINCT visitnum) AS visits_recorded
            FROM visits
            GROUP BY source_study, subject_key
        )
    SELECT p.source_study,
        COUNT(*) AS subjects_with_data,
        COUNT(*) FILTER (WHERE p.visits_recorded >= e.expected_visits)
            AS complete,
        COUNT(*) FILTER (WHERE p.visits_recorded < e.expected_visits)
            AS incomplete
    FROM per_subject AS p
    JOIN expected AS e
        ON e.source_study = p.source_study
    GROUP BY p.source_study
    ORDER BY p.source_study;
"""

# Flagged-value rate: share of lab results whose reference-range
# indicator is High or Low.
DQ_LAB_FLAGS_QUERY = """
    SELECT source_study,
        COUNT(*) AS results_assessed,
        COUNT(*) FILTER (WHERE value IN ('High', 'Low')) AS flagged,
        ROUND(
            100.0 * COUNT(*) FILTER (WHERE value IN ('High', 'Low'))
            / COUNT(*), 1
        ) AS flag_pct
    FROM lb
    WHERE standard_var = 'LBNRIND'
    GROUP BY source_study
    ORDER BY source_study;
"""


@app.get("/dq-missingness")
def dq_missingness():
    return run_sql(DQ_MISSINGNESS_QUERY)


@app.get("/dq-visit-completeness")
def dq_visit_completeness():
    return run_sql(DQ_VISIT_COMPLETENESS_QUERY)


@app.get("/dq-lab-flags")
def dq_lab_flags():
    return run_sql(DQ_LAB_FLAGS_QUERY)

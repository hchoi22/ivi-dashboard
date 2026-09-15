"""
Haechan Choi
IVI Data Sceince & Innovations
This program uses utilizes the EAV structured synthetic clinical data
from Vi-DT studies and loads the data to the respective postgres database.
"""
import pandas as pd
from sqlalchemy import create_engine, text

DB_CONFIG = {
    "user": "--",
    "password": "--",
    "host": "--",
    "port": 0000,
    "dbname": "ivi_synthetic_db",
}

# EAV workbooks produced by each study's *_htov.py script
FILES = {
    "T002": "T002_EAV_output.xlsx",
    "T005": "T005_EAV_output.xlsx",
    "T006": "T006_EAV_output.xlsx",
}

# Maps the sheet name found inside each Excel file to the Postgres
# domain table it belongs in. Extend this if a sheet name doesn't
# match what's here.
SHEET_TO_TABLE = {
    "DM": "dm",
    "DS": "ds",
    "SV": "sv",
    "MH": "mh",
    "PE": "pe",
    "VS": "vs",
    "BE": "be",
    "BS": "bs",
    "IE": "ie",
    "CM": "cm",
    "EOS": "eos",
    "Comment": "co",
    "CO": "co",
    "EX": "ex",
    "AE": "ae",
    "LB": "lb",
    "identifier": None,  # T005 dictionary artifact
}

# Column names differ slightly between T002/T005 and T006's annotated
# output (StandardVAR vs Standard_VAR, etc).
COLUMN_ALIASES = {
    "studyid": "studyid", "STUDYID": "studyid",
    "subjid": "subjid", "SUBJID": "subjid",
    "scrno": "scrno", "SCRNO": "scrno",
    "record_id": "record_id",
    "standardvar": "standard_var", "Standard_VAR": "standard_var",
    "StandardVAR": "standard_var",
    "standardlabel": "standard_label", "Standard_LABEL": "standard_label",
    "StandardLABEL": "standard_label",
    "value": "value", "VALUE": "value",
    "value_code": "value_code", "VALUE_CODE": "value_code",
    "seqnum": "seqnum", "SeqNum": "seqnum",
    "visitnum": "visitnum", "VISITNUM": "visitnum"
}


def consolidate_duplicate_columns(df: pd.DataFrame) -> pd.DataFrame:
    '''
    Collapse duplicate column names (can happen after normalize_columns
    maps two differently-cased source columns to the same target name)
    by back-filling across the duplicates and keeping one copy.
    '''

    if not df.columns.duplicated().any():
        return df

    result = {}

    for col in df.columns.unique():
        matching = df.loc[:, df.columns == col]
        if matching.shape[1] == 1:
            result[col] = matching.iloc[:, 0]
        else:
            result[col] = matching.bfill(axis=1).iloc[:, 0]

    return pd.DataFrame(result)


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    '''
    Rename each sheet's columns to the loader's canonical lowercase
    names via COLUMN_ALIASES, drop anything not in the alias map, and
    resolve any resulting duplicate columns.
    '''
    rename_map = {
        c: COLUMN_ALIASES[c]
        for c in df.columns
        if c in COLUMN_ALIASES
    }
    df = df.rename(columns=rename_map)

    keep = [c for c in df.columns if c in set(COLUMN_ALIASES.values())]
    df = df[keep].copy()

    return consolidate_duplicate_columns(df)


def get_or_create_subject_key(conn, source_study,
                              studyid, subjid, scrno, record_id=None):
    """
    Look up the Postgres subject_key for this source row, trying
    subjid, then record_id, then scrno as fallback identifiers.
    Inserting a new subjects row if none is found.
    """

    subjid = None if pd.isna(subjid) or subjid == "" else str(subjid)
    scrno = None if pd.isna(scrno) or scrno == "" else str(scrno)
    studyid = None if pd.isna(studyid) else str(studyid)
    record_id = (
        None
        if pd.isna(record_id) or record_id == ""
        else str(record_id)
    )

    if subjid is None and scrno is None and record_id is None:
        raise ValueError(
            f"Row for source_study={source_study} has no usable identifier "
            f"(subjid, scrno, and record_id all missing). studyid={studyid}"
        )

    # Try subjid first (most specific, present on first visit)
    if subjid is not None:
        query = text(
            "SELECT subject_key FROM subjects"
            "WHERE source_study=:s AND subjid=:sub"
        )
        result = conn.execute(
            query,
            {"s": source_study, "sub": subjid},
        ).fetchone()
        if result:
            return result[0]

    # Fall back to record_id (T006's reliable per-subject key
    # across all visits)
    if record_id is not None:
        query = text(
            "SELECT subject_key FROM subjects"
            "WHERE source_study=:s AND record_id=:rid"
        )
        result = conn.execute(
            query,
            {"s": source_study, "rid": record_id},
        ).fetchone()
        if result:
            return result[0]

    # Fall back to scrno (T002's screen-failure identifier)
    if scrno is not None:
        query = text(
            "SELECT subject_key FROM subjects"
            "WHERE source_study=:s AND scrno=:scr"
        )
        result = conn.execute(
            query,
            {"s": source_study, "scr": scrno},
        ).fetchone()
        if result:
            return result[0]

    # No existing subject matched on any identifier -- register a new one
    result = conn.execute(
        text("""
            INSERT INTO subjects
                (source_study, studyid, subjid, scrno, record_id)
            VALUES
                (:s, :studyid, :subjid, :scrno, :record_id)
            RETURNING subject_key
        """),
        {"s": source_study, "studyid": studyid, "subjid": subjid,
         "scrno": scrno, "record_id": record_id},
    )

    return result.fetchone()[0]


def load_subject_linkage(conn, df):
    """
    Load the T002-T006 SUBJECT_LINKAGE EAV sheet into the dedicated
    subject_linkage table.
    """

    inserted = 0

    for record_id, g in df.groupby("record_id"):
        vals = dict(zip(g["SOURCE_VAR"], g["VALUE"]))
        t006_key = conn.execute(
            text("SELECT subject_key FROM subjects "
                 "WHERE source_study='T006' AND subjid=:v"),
            {"v": vals.get("t006_subjid")}).fetchone()
        t002_key = conn.execute(
            text("SELECT subject_key FROM subjects "
                 "WHERE source_study='T002' AND subjid=:v"),
            {"v": vals.get("t002_subjid")}).fetchone()
        conn.execute(
            text("""
                INSERT INTO subject_linkage
                    (t002_subject_key, t006_subject_key, linkage_type)
                VALUES (:a, :b, :c)
                ON CONFLICT (t002_subject_key, t006_subject_key) DO NOTHING
            """),
            {"a": t002_key[0] if t002_key else None,
             "b": t006_key[0] if t006_key else None,
             "c": vals.get("link_status")})
        inserted += 1


def load_sheet(conn, source_study, sheet_name, df):
    """
    Loading the sheets into its respective Postgre Tables
    """
    if sheet_name == "SUBJECT_LINKAGE":
        load_subject_linkage(conn, df)
        return

    table = SHEET_TO_TABLE.get(sheet_name)

    if table is None:
        print(f"  [SKIP] Sheet '{sheet_name}' has no known target table "
              f"-- add it to SHEET_TO_TABLE if needed.")
        return

    df = normalize_columns(df)
    if df.empty or "standard_var" not in df.columns:
        print(f"  [SKIP] Sheet '{sheet_name}' has no usable rows "
              f"after column normalization.")
        return

    id_cols = ["studyid", "subjid", "scrno", "record_id"]
    present_id_cols = [c for c in id_cols if c in df.columns]

    subject_key_cache = {}
    rows_inserted = 0

    for _, row in df.iterrows():
        key_tuple = tuple(row.get(c) for c in present_id_cols)
        if key_tuple not in subject_key_cache:
            subject_key_cache[key_tuple] = get_or_create_subject_key(
                conn, source_study,
                row.get("studyid"), row.get("subjid"),
                row.get("scrno"), row.get("record_id"),
            )
        subject_key = subject_key_cache[key_tuple]

        value_code = row.get("value_code")
        seqnum = row.get("seqnum")
        visitnum = row.get("visitnum")
        has_value_code = "value_code" in df.columns
        has_seqnum = "seqnum" in df.columns
        has_visitnum = "visitnum" in df.columns

        conn.execute(
            text(
                f"""
                INSERT INTO {table}
                    (subject_key, source_study, standard_var, standard_label,
                    value, value_code, seqnum, visitnum)
                VALUES
                    (:subject_key, :source_study, :standard_var,
                    :standard_label, :value, :value_code, :seqnum, :visitnum)
                """
            ),
            {
                "subject_key": subject_key,
                "source_study": source_study,
                "standard_var": row.get("standard_var"),
                "standard_label": row.get("standard_label"),
                "value": (
                    None
                    if pd.isna(row.get("value"))
                    else str(row.get("value"))
                ),
                "value_code": (
                    value_code
                    if has_value_code and pd.notna(value_code)
                    else None
                ),
                "seqnum": (
                    int(seqnum)
                    if has_seqnum and pd.notna(seqnum)
                    else None
                ),
                "visitnum": (
                    float(visitnum)
                    if has_visitnum and pd.notna(visitnum)
                    else None
                )
            },
        )
        rows_inserted += 1


def main():
    """
    Entry point: connect to Postgres, then load each study's EAV
    workbook sheet-by-sheet, one transaction per study file.
    """
    conn_str = (
        f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
        f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
    )
    engine = create_engine(conn_str)

    for source_study, path in FILES.items():
        xls = pd.ExcelFile(path)
        with engine.begin() as conn:
            for sheet_name in xls.sheet_names:
                df = xls.parse(sheet_name)
                if df.empty:
                    print(f"  [SKIP] Sheet '{sheet_name}' is empty.")
                    continue
                load_sheet(conn, source_study, sheet_name, df)


if __name__ == "__main__":
    main()

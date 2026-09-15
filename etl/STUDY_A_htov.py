"""
Haechan Choi
IVI Data Sceince & Innovations
This program uses utilizes synthetic clinical data from Vi-DT
STUDY_A study and transforms its horizontal data structure to a
vertical data structure.
"""
import sys
import pandas as pd

STUDY_PREFIX = "STUDY_A"

# not in data dictionary so need extra mapping
IE_EXTRA_MAPPINGS = pd.DataFrame([
    {"Standard_Domain": "IE", "Standard_VAR": "SUPPIE",
     "Standard_LABEL": "Screening Failure Reason",
     "SOURCE_FORM": "IE", "SOURCE_VAR": "iesfreason"},
    {"Standard_Domain": "IE", "Standard_VAR": "SUPPIE",
     "Standard_LABEL": "Eligibility Reason",
     "SOURCE_FORM": "IE", "SOURCE_VAR": "ieeligreason"},
])


# encoding purpose
def read_csv_any_encoding(path: str) -> pd.DataFrame:
    '''
    Given a file path way, read the file as UTF-8
    '''

    for enc in ["utf-8", "utf-8-sig", "cp949", "euc-kr", "latin1"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"Could not read {path} with any known encoding.")


# loading the clinical mapping file and the necessary columns
# to match with the STUDY_A
def load_dictionary(dic_path: str, study_prefix: str) -> pd.DataFrame:
    '''
    Load the STUDY_A crosswalk from the dictionary CSV.
    '''

    # loads the raw dictionary csv into a dataframe
    dict_df = read_csv_any_encoding(dic_path)

    form_col = f"{study_prefix}_FORM"
    var_col = f"{study_prefix}_VAR"
    required_cols = [
        "Standard_Domain",
        "Standard_VAR",
        "Standard_LABEL",
        form_col,
        var_col
    ]

    missing = [c for c in required_cols if c not in dict_df.columns]

    if missing:
        raise KeyError(
            f"Dictionary is missing {missing} columns."
            f"Check the actual column names in the dictionary."
        )

    # extracting only the columns that we need fro the dictionary
    # keeping only the columns in the dictonary that we need
    # also disregarding the rows with NA values in STUDY_A_VAR
    # (We don't need)
    out = pd.DataFrame({
        "Standard_Domain": dict_df["Standard_Domain"],
        "Standard_VAR": dict_df["Standard_VAR"],
        "Standard_LABEL": dict_df["Standard_LABEL"],
        "SOURCE_FORM": dict_df[form_col],
        "SOURCE_VAR": dict_df[var_col]
    })

    out = out.dropna(subset=["SOURCE_VAR"]).copy()

    # removes any spaces in the variables
    out["Standard_Domain"] = (
        out["Standard_Domain"]
        .fillna("")
        .astype(str)
        .str.strip()
    )
    out["Standard_VAR"] = (
        out["Standard_VAR"]
        .fillna("")
        .astype(str)
        .str.strip()
    )
    out["Standard_LABEL"] = (
        out["Standard_LABEL"]
        .fillna("")
        .astype(str)
        .str.strip()
    )
    out["SOURCE_VAR"] = (
        out["SOURCE_VAR"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )
    out["SOURCE_FORM"] = (
        out["SOURCE_FORM"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    out = out[out["SOURCE_VAR"] != ""].copy()

    return out


def build_domain_eav_from_sheet(source_df: pd.DataFrame, domain: str,
                                domain_map_for_sheet: pd.DataFrame,
                                start_row_id: int):
    """
    Given the dataframe for a particular domain, the domain name,
    the domain mapping and the referrencing row_id, builds one vertical
    EAV for one domain.
    """

    # initializes the empty list to accumulate dictionaries.
    rows = []
    row_id = start_row_id

    # considering visit num naming
    visit_col = "visit_num" if "visit_num" in source_df.columns else (
        "visit" if "visit" in source_df.columns else None
    )
    has_scrno = "scrno" in source_df.columns

    # assign seqnum to every mapped IE row
    # STUDY_A just checks for eligbility
    if domain == "IE":
        mapped_vars = set(domain_map_for_sheet["SOURCE_VAR"])
        ie_col_seq = {
            col: i + 1
            for i, col in enumerate(source_df.columns)
            if col in mapped_vars
        }

    # iterates through index and row
    for source_row_number, r in source_df.iterrows():
        # gets the respective variables (returns none if not exist)
        studyid = r.get("studyid")
        subjid = r.get("subjid")
        scrno = r.get("scrno") if has_scrno else None
        visitnum = r.get(visit_col) if visit_col else None

        # iterates through index and row
        # in every relevant dictionary mapping row
        for _, m in domain_map_for_sheet.iterrows():
            src_var = m["SOURCE_VAR"]

            # check the source variable if it is in the df
            if src_var not in source_df.columns:
                # if not go to next mapping
                continue

            # Get the value for the respective source variable
            val = r.get(src_var)

            # check whether the value exists
            if pd.isna(val) or val == "":
                continue

            row_id += 1

            # building the acutal output row as a dcitionary
            row = {
                f"{domain}ID": row_id,
                "STUDYID": studyid,
                "SUBJID": subjid,
                "SCRNO": scrno,
                "Domain": domain,
                "Standard_VAR": m["Standard_VAR"],
                "Standard_LABEL": m["Standard_LABEL"],
                "VALUE": val,
                "SOURCE_SHEET": m["SOURCE_FORM"],
                "SOURCE_FORM": m["SOURCE_FORM"],
                "SOURCE_ROW_NUMBER": source_row_number,
            }

            # add visit num to the necessary domains
            if visit_col and pd.notna(visitnum):
                row["VISITNUM"] = visitnum

            if domain == "IE":
                row["_IE_SEQ"] = ie_col_seq[src_var]

            rows.append(row)

    return pd.DataFrame(rows), row_id


def process_study(dict_path: str, source_path: str, output_path: str,
                  study_prefix: str = STUDY_PREFIX):
    """
    Processing each page in the excel datasheet
    """

    domain_map = load_dictionary(dict_path, study_prefix)
    domains_available = domain_map["Standard_Domain"].unique()

    # builds a case-insensitive lookup so SOURCE_FORM values (already
    # uppercased) can be matched against the workbook's actual sheet
    # names, whatever casing they were saved with
    xls = pd.ExcelFile(source_path)
    sheet_lookup = {s.upper(): s for s in xls.sheet_names}

    referenced_forms = set(domain_map["SOURCE_FORM"].unique())
    unmapped_sheets = [
        s for s in xls.sheet_names
        if s.upper() not in referenced_forms and s.upper() != "README"
    ]
    if unmapped_sheets:
        print(
            f"[WARNING] These workbook sheets have NO dictionary mapping "
            f"for {study_prefix} and will NOT appear in the EAV output: "
            f"{unmapped_sheets}"
        )

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        # iterates through the domains
        for domain in domains_available:

            # gets all the domains where the
            # standard domain matches with the domain given
            domain_rows = domain_map[domain_map["Standard_Domain"] == domain]

            if domain == "IE":
                domain_rows = pd.concat([domain_rows, IE_EXTRA_MAPPINGS],
                                        ignore_index=True)

            forms_for_domain = domain_rows["SOURCE_FORM"].unique()

            domain_frames = []
            row_id_counter = 0
            sheets_used = []
            sheets_missing = []

            # for every sheet that it checks with the domains
            # check whether the sheet actually exists
            for form in forms_for_domain:
                sheet_name = sheet_lookup.get(form)
                if sheet_name is None:
                    sheets_missing.append(form)
                    continue

                # reads the particular sheet into a dataframe
                source_df = xls.parse(sheet_name)

                # filters down the domain rows further to match its form
                domain_map_for_this_sheet = domain_rows[
                    domain_rows["SOURCE_FORM"] == form
                ]

                # gets the EAV dataframe and the row_id counter
                eav_df, row_id_counter = build_domain_eav_from_sheet(
                    source_df, domain,
                    domain_map_for_this_sheet,
                    row_id_counter
                )

                if not eav_df.empty:
                    domain_frames.append(eav_df)
                    sheets_used.append(
                        f"{sheet_name} ({eav_df.shape[0]} rows)"
                    )

            if sheets_missing:
                print(
                    f"[{domain}] no matching sheet found for form(s):"
                    f"{sheets_missing} -- those fields skipped")

            if not domain_frames:
                print(
                    f"[{domain}] produced 0 rows across all referenced sheets"
                    f"-- check column names"
                )
                continue

            # Combine the sheets together into one excel sheet
            combined = pd.concat(domain_frames, ignore_index=True)

            id_col = f"{domain}ID"

            combined = combined.reset_index(drop=True)
            combined[id_col] = range(1, len(combined) + 1)

            if "VISITNUM" not in combined.columns:
                combined["VISITNUM"] = pd.NA

            event_rows = (
                combined[
                    [
                        "SUBJID",
                        "SOURCE_FORM",
                        "SOURCE_ROW_NUMBER",
                        "VISITNUM",
                        id_col,
                    ]
                ]
                .sort_values(
                    [
                        "SUBJID",
                        "VISITNUM",
                        "SOURCE_FORM",
                        "SOURCE_ROW_NUMBER",
                        id_col,
                    ],
                    na_position="last",
                )
                .drop_duplicates(
                    subset=[
                        "SUBJID",
                        "SOURCE_FORM",
                        "SOURCE_ROW_NUMBER",
                    ],
                    keep="first",
                )
                .copy()
            )

            # assigning sequence number that increases by 1
            # after every grouping
            event_rows["SeqNum"] = (
                event_rows.groupby(
                    "SUBJID",
                    dropna=False,
                )
                .cumcount()
                + 1
            )

            combined = combined.merge(
                event_rows[
                    [
                        "SUBJID",
                        "SOURCE_FORM",
                        "SOURCE_ROW_NUMBER",
                        "SeqNum",
                    ]
                ],
                on=[
                    "SUBJID",
                    "SOURCE_FORM",
                    "SOURCE_ROW_NUMBER",
                ],
                how="left",
                validate="many_to_one",
            )

            combined = combined.drop(columns=["SOURCE_ROW_NUMBER"])

            if domain == "IE":
                combined["SeqNum"] = combined["_IE_SEQ"]
                combined = combined.drop(columns=["_IE_SEQ"])

            combined.to_excel(writer, sheet_name=domain, index=False)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(
            "Usage:"
            "python STUDY_A_htov.py <dict_csv> <source_xlsx> <output_xlsx>"
        )
        sys.exit(1)
    process_study(sys.argv[1], sys.argv[2], sys.argv[3])

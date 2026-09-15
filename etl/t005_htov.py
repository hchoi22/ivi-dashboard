"""
Haechan Choi
IVI Data Sceince & Innovations
This program uses utilizes synthetic clinical data from Vi-DT
T005 study and transforms its horizontal data structure to a
vertical data structure.
"""
import sys
import re
import pandas as pd

# the domains that should include visitnums
VISIT_DOMAINS = {"LB", "PE", "SV", "BE", "BS", "VS", "MH", "CM"}


# encoding purpose
def read_csv_any_encoding(path: str) -> pd.DataFrame:
    """
    Given a file path way, read the file as UTF-8
    """

    for enc in ["utf-8", "utf-8-sig", "cp949", "euc-kr", "latin1"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"Could not read {path} with any known encoding.")


# loading the clinical mapping file and the necessary columns
# to match with the T005
def load_dictionary(dict_path: str) -> pd.DataFrame:
    """
    Load the T005 crosswalk from the dictionary CSV.
    """

    # loads the raw dictionary csv into a dataframe
    dict_df = read_csv_any_encoding(dict_path)

    # extracting only the columns that we need fro the dictionary
    # keeping only the columns in the dictonary that we need
    # also disregarding the rows with NA values in T005_VAR (We don't need)
    keep_cols = ["Standard_Domain", "Standard_VAR", "Standard_LABEL",
                 "T005_FORM", "T005_VAR"]
    out = dict_df[keep_cols].dropna(subset=["T005_VAR"]).copy()

    # redesigning the initial columns in the new table
    out.columns = ["Standard_Domain", "Standard_VAR", "Standard_LABEL",
                   "SOURCE_FORM", "SOURCE_VAR"]

    # removes any spaces in the source variable name and its form
    out["SOURCE_VAR"] = out["SOURCE_VAR"].str.strip().str.lower()
    out["SOURCE_FORM"] = out["SOURCE_FORM"].str.strip().str.upper()

    return out


# Building the domain for the EAV design
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

    # assigns the seqnum after grouping them and normalizing them.
    # multiple rows relating to the IE can have the same seqnum
    ie_col_seq = {}
    if domain == "IE":
        mapped_vars = set(domain_map_for_sheet["SOURCE_VAR"])
        group_seq = {}
        for col in source_df.columns:
            if col not in mapped_vars:
                continue
            m = re.match(r"(in|ex)(\d+)", col)
            key = m.group(0) if m else col
            if key not in group_seq:
                group_seq[key] = len(group_seq) + 1
            ie_col_seq[col] = group_seq[key]

    # iterates through index and row
    for source_row_number, r in source_df.iterrows():
        # gets the respective variables (returns none if not exist)
        studyid = r.get("studyid")
        subjid = r.get("subjid")
        visitnum = r.get("visitnum")

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
                # if not move to the next mapping
                continue

            row_id += 1

            # building the acutal output row as a dcitionary
            row = {
                f"{domain}ID": row_id,
                "STUDYID": studyid,
                "SUBJID": subjid,
                "Domain": domain,
                "Standard_VAR": m["Standard_VAR"],
                "Standard_LABEL": m["Standard_LABEL"],
                "VALUE": val,
                "SOURCE_SHEET": m["SOURCE_FORM"],
                "SOURCE_FORM": m["SOURCE_FORM"],
                "SOURCE_ROW_NUMBER": source_row_number   # traceability
            }

            # add visit num to the necessary domains
            if domain in VISIT_DOMAINS and pd.notna(visitnum):
                row["VISITNUM"] = visitnum

            if domain == "IE":
                row["_IE_SEQ"] = ie_col_seq[src_var]

            # add the row to the output
            rows.append(row)

    return pd.DataFrame(rows), row_id


# building the EAV sheet
def process_study(dict_path: str, source_path: str, output_path: str):
    """
    Processing each page in the excel datasheet
    """

    domain_map = load_dictionary(dict_path)
    domains_available = domain_map["Standard_Domain"].unique()

    # builds a case-insensitive lookup so SOURCE_FORM values (already
    # uppercased) can be matched against the workbook's actual sheet
    # names, whatever casing they were saved with
    xls = pd.ExcelFile(source_path)
    sheet_lookup = {s.upper(): s for s in xls.sheet_names}

    # opens the file
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        # iterates through the domains
        for domain in domains_available:

            # gets all the domains where the
            # standard domain matches with the domain given
            domain_rows = domain_map[domain_map["Standard_Domain"] == domain]
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
                    domain_rows["SOURCE_FORM"] == form]

                # gets the EAV dataframe and the row_id counter
                eav_df, row_id_counter = build_domain_eav_from_sheet(
                    source_df, domain,
                    domain_map_for_this_sheet,
                    row_id_counter
                )

                if not eav_df.empty:
                    domain_frames.append(eav_df)
                    sheets_used.append(
                        f"{sheet_name} ({eav_df.shape[0]} rows)")

            if sheets_missing:
                print(f"[{domain}] no matching sheet found for form(s): "
                      f"{sheets_missing} -- those fields skipped")

            if not domain_frames:
                print(f"[{domain}] produced 0 rows in all referenced sheets "
                      f"-- check column names")
                continue

            # Combine the sheets together into one excel sheet
            combined = pd.concat(domain_frames, ignore_index=True)

            id_col = f"{domain}ID"
            combined = combined.reset_index(drop=True)
            combined[id_col] = range(1, len(combined) + 1)

            if "VISITNUM" not in combined.columns:
                combined["VISITNUM"] = pd.NA

            event_rows = (
                combined[["SUBJID", "SOURCE_FORM", "SOURCE_ROW_NUMBER",
                          "VISITNUM", id_col]]
                .sort_values(["SUBJID", "VISITNUM", "SOURCE_FORM",
                              "SOURCE_ROW_NUMBER", id_col], na_position="last")
                .drop_duplicates(subset=["SUBJID", "SOURCE_FORM",
                                         "SOURCE_ROW_NUMBER"], keep="first")
                .copy()
            )
            event_rows["SeqNum"] = (
                event_rows.groupby("SUBJID", dropna=False).cumcount() + 1
            )

            combined = combined.merge(
                event_rows[["SUBJID", "SOURCE_FORM",
                            "SOURCE_ROW_NUMBER", "SeqNum"]],
                on=["SUBJID", "SOURCE_FORM", "SOURCE_ROW_NUMBER"],
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
        print("Usage: python t005_htov.py "
              "<dict_csv> <source_xlsx> <output_xlsx>")
        sys.exit(1)
    process_study(sys.argv[1], sys.argv[2], sys.argv[3])

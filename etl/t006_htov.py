"""
Haechan Choi
IVI Data Sceince & Innovations
This program uses utilizes synthetic clinical data from Vi-DT
T006 study and transforms its horizontal data structure to a
vertical data structure.
"""
import sys
import pandas as pd

PE_POSITIONS = range(1, 13)
PERES_DECODE = {1: "Normal", 2: "Abnormal", 9: "Not assessed"}

# vsorres1..5 are positional vital sign slots
# map each to its real label
# since the source sheet only stores them as generic numbered columns
VS_LABELS = {
    "vsorres1": "Height (cm)",
    "vsorres2": "Weight (kg)",
    "vsorres3": "Heart Rate (beats/minute)",
    "vsorres4": "Respiratory Rate (breaths/minute)",
    "vsorres5": "Body Temperature (Celsius)",
}

# mapping for not done flag columns
VSND_MAP = {
    "vsorres1": "vsnd1___9",
    "vsorres2": "vsnd2___9",
    "vsorres3": "vsnd3___9",
    "vsorres4": "vsnd4___9",
    "vsorres5": "vsnd5___9",
}

# REDCap exports the event/visit label under either name
EVENT_COLUMNS = ("redcap_event_name", "redcapeventname")
ID_COLUMNS = ("record_id", "recordid",
              "subjid",
              "redcap_repeat_instance",
              "redcaprepeatinstance")

# normalizes REDCap's free-text event names down to a numeric VISITNUM
VISITNUM_MAP = {
    "visit_1_arm_1": 1,
    "visit_2_arm_1": 2,
    "visit_3_arm_1": 3,
    "visit1_arm_1": 1,
    "visit2_arm_1": 2,
    "visit3_arm_1": 3,
    "visit1arm1": 1,
    "visit2arm1": 2,
    "visit3arm1": 3,
}

# sheets that don't follow the standard dictionary mapping
# are hand-mapped here instead
MANUAL_SHEET_MAPPINGS = {
    "t002_t006_linkage": {
        "t006_record_id": ("DM", "DMSPID",  "T006 Record ID"),
        "t006_subjid": ("DM", "SUBJID",  "T006 Subject ID"),
        "t002_subjid": ("DM", "SUBJID",  "T002 Subject ID"),
        "pre_id": ("DM", "SUPPDM",  "Previous Subject Identifier"),
        "link_status": ("DM", "SUPPDM",  "Link Status"),
        "pre_vg": ("DM", "SUPPDM",  "Previously Assigned Vaccine Group"),
        "first_enrollment_visit":
        ("SV", "VISIT", "Visit of First Enrollment"),
    },
}

# which column(s) identify a subject/row within the manual sheet
MANUAL_SHEET_ID_COLUMNS = {
    "t002_t006_linkage": ("t006_subjid", "t006_record_id"),
}


# encoding purpose
def read_csv_any_encoding(path):
    for encoding in ("utf-8", "utf-8-sig", "cp949", "euc-kr", "latin1"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError:
            pass

    raise ValueError(f"Could not read mapping file: {path}")


# loading the clinical mapping file and the necessary columns
# to match with T006
def load_t006_dictionary(path):
    '''
    Load the T006 crosswalk from the dictionary CSV
    '''

    raw = read_csv_any_encoding(path)
    required = ["Standard_Domain", "Standard_VAR", "Standard_LABEL",
                "T006_FORM", "T006_VAR"]

    missing = [c for c in required if c not in raw.columns]

    if missing:
        raise ValueError(f"Mapping file is missing columns: {missing}")

    mapping = raw[required].dropna(subset=["T006_VAR"]).copy()
    mapping.columns = ["Domain", "Standard_VAR", "Standard_LABEL",
                       "Source_Form", "Source_Var"]

    mapping["Domain"] = mapping[
        "Domain"].astype(str).str.strip()
    mapping["Standard_VAR"] = mapping[
        "Standard_VAR"].astype(str).str.strip()
    mapping["Standard_LABEL"] = mapping[
        "Standard_LABEL"].fillna("").astype(str).str.strip()
    mapping["Source_Form"] = mapping[
        "Source_Form"].fillna("").astype(str).str.strip().str.lower()
    mapping["Source_Var"] = mapping[
        "Source_Var"].astype(str).str.strip().str.lower()

    return mapping.drop_duplicates(subset=["Domain",
                                           "Standard_VAR",
                                           "Standard_LABEL",
                                           "Source_Var"])


def find_event_column(df):
    """
    Locate whichever REDCap event column name this sheet uses.
    """

    for column in EVENT_COLUMNS:
        if column in df.columns:
            return column

    raise ValueError(f"No REDCap event column found."
                     f"Expected one of: {EVENT_COLUMNS}")


def derive_visitnum(event_value):
    """
    Convert a REDCap event label into a numeric VISITNUM using VISITNUM_MAP
    """
    if pd.isna(event_value):
        return None

    # after normalizing, uses the dictionary to get the vistnum from
    # redcap event label
    return VISITNUM_MAP.get(str(event_value).strip().lower())


def build_id_row(r, df, event_column):
    '''
    Build the shared identifier columns
    that every EAV row for this source row needs,
    regardless of the domain.
    '''

    row = {
        column: r.get(column)
        for column in ID_COLUMNS
        if column in df.columns
    }

    row["VISITNUM"] = derive_visitnum(r.get(event_column))
    row["SeqNum"] = r.get("_SEQNUM")

    return row


def code_value(value):
    if pd.isna(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def positional_source_vars():
    '''
    Collect every positional PE/VS source column name so the scalar
    melt step can exclude them.
    '''

    pe = set()

    for i in PE_POSITIONS:
        pe.update({f"petest{i}", f"peres{i}", f"pedesc{i}", f"peclsig{i}"})

    return pe | set(VS_LABELS) | set(VSND_MAP.values()) | {"vsyn", "vsreasnd"}


def make_map_lookup(mapping):
    '''
    Index the dictionary mapping by Source_Var for fast lookup.
    '''
    lookup = {}

    for _, m in mapping.iterrows():
        lookup.setdefault(m["Source_Var"], []).append(m.to_dict())

    return lookup


def first_mapping(lookup, source_var, domain=None, standard_var=None):
    '''
    Return the first dictionary mapping row matching source_var,
    optionally narrowed by domain and/or standard_var.
    '''
    candidates = lookup.get(source_var, [])

    for item in candidates:
        if (
            (domain is None or item["Domain"] == domain)
            and (
                standard_var is None
                or item["Standard_VAR"] == standard_var
            )
        ):
            return item
    return None


def melt_scalar_fields(df, mapping, event_column, excluded):
    '''
    Transform every non-positional (scalar) mapped column into EAV rows.
    '''
    rows = []
    scalar_map = mapping[~mapping["Source_Var"].isin(excluded)]

    # iterate through every index and row in the df
    for _, r in df.iterrows():
        base = build_id_row(r, df, event_column)

        # iterate through the mapping dictionary
        for _, m in scalar_map.iterrows():
            source_var = m["Source_Var"]

            if source_var not in df.columns:
                continue

            value = r.get(source_var)

            if pd.isna(value) or value == "":
                continue

            row = base.copy()
            row.update({
                "Domain": m["Domain"],
                "Standard_VAR": m["Standard_VAR"],
                "Standard_LABEL": m["Standard_LABEL"],
                "VALUE": value,
                "SOURCE_FORM": m["Source_Form"],
                "SOURCE_VAR": source_var,
            })
            rows.append(row)

    return pd.DataFrame(rows)


def melt_pe(df, lookup, event_column):
    '''
    Transform every PE mapped column into EAV rows.
    PE columns are encoded twelve physical-exam
    body systems positionally.
    Also values need to be decoded.
    '''
    rows = []

    for _, r in df.iterrows():
        base = build_id_row(r, df, event_column)

        for i in PE_POSITIONS:
            result_var = f"peres{i}"
            label_var = f"petest{i}"

            if result_var not in df.columns:
                continue

            raw_code = r.get(result_var)
            label = r.get(label_var) if label_var in df.columns else None

            if (
                pd.isna(label)
                or label == ""
                or pd.isna(raw_code)
                or raw_code == ""
            ):
                continue

            mapped = first_mapping(lookup, result_var,
                                   domain="PE",
                                   standard_var="PEORRES")
            row = base.copy()

            row.update({
                "Domain": "PE",
                "Standard_VAR": (mapped["Standard_VAR"]
                                 if mapped
                                 else "PEORRES"),
                "Standard_LABEL": str(label).strip(),
                "VALUE": PERES_DECODE.get(code_value(raw_code),
                                          f"UNMAPPED_CODE_{raw_code}"),
                "VALUE_CODE": raw_code,
                "PEDESC": r.get(f"pedesc{i}"),
                "PECLSIG": r.get(f"peclsig{i}"),
                "SOURCE_FORM": (mapped["Source_Form"]
                                if mapped
                                else "physical_examination"),
                "SOURCE_VAR": result_var,
                "match_status": "position_label_from_petest",
            })
            rows.append(row)

    return pd.DataFrame(rows)


def melt_vs(df, lookup, event_column):
    '''
    Transform every VS mapped column into EAV rows.
    VS related columns are hardcoded to five fixed positions.
    '''
    rows = []
    for _, r in df.iterrows():
        base = build_id_row(r, df, event_column)

        # these two variables don't hold any positional key
        # so mapped manually
        for source_var, standard_var, fallback_label in (
            ("vsyn", "VSPERF", "Were the vital signs taken?"),
            ("vsreasnd", "VSREASND", "If No, Reason for Not Done"),
        ):
            if source_var not in df.columns:
                continue
            value = r.get(source_var)
            if pd.isna(value) or value == "":
                continue
            mapped = first_mapping(lookup, source_var, domain="VS")
            row = base.copy()
            row.update({
                "Domain": "VS",
                "Standard_VAR": (mapped["Standard_VAR"]
                                 if mapped else standard_var),
                "Standard_LABEL": (mapped["Standard_LABEL"]
                                   if mapped else fallback_label),
                "VALUE": value,
                "SOURCE_FORM": (mapped["Source_Form"]
                                if mapped else "vital_signs"),
                "SOURCE_VAR": source_var,
            })
            rows.append(row)

        for sequence, (source_var, fallback_label) in enumerate(
                                                            VS_LABELS.items(),
                                                            start=1):
            if source_var not in df.columns:
                continue
            value = r.get(source_var)
            if pd.isna(value) or value == "":
                continue
            mapped = first_mapping(lookup, source_var, domain="VS",
                                   standard_var="VSORRES")
            row = base.copy()
            row.update({
                "Domain": "VS",
                "Standard_VAR": (mapped["Standard_VAR"]
                                 if mapped else "VSORRES"),
                "Standard_LABEL": (mapped["Standard_LABEL"]
                                   if mapped and mapped["Standard_LABEL"]
                                   else fallback_label),
                "VALUE": value,
                "VSND": r.get(VSND_MAP[source_var]),
                "SOURCE_FORM": (mapped["Source_Form"]
                                if mapped else "vital_signs"),
                "SOURCE_VAR": source_var,
                "match_status": "position_label_confirmed",
            })
            rows.append(row)
    return pd.DataFrame(rows)


def melt_manual_sheet(df, sheet_key):
    '''
    Transform the subject linkage page columns into EAV rows.
    '''
    manual_map = MANUAL_SHEET_MAPPINGS[sheet_key]
    subjid_col, recordid_col = MANUAL_SHEET_ID_COLUMNS.get(sheet_key,
                                                           (None, None))

    unmapped = [c for c in df.columns if c not in manual_map]

    if unmapped:
        print(f"WARNING [{sheet_key}] columns with NO manual mapping "
              f"(not in EAV output): {unmapped}")

    rows = []
    for _, r in df.iterrows():
        base = {"SeqNum": 1, "VISITNUM": None}
        if subjid_col and subjid_col in df.columns:
            base["subjid"] = r.get(subjid_col)
        if recordid_col and recordid_col in df.columns:
            base["record_id"] = r.get(recordid_col)

        for source_var, (domain, std_var, std_label) in manual_map.items():
            if source_var not in df.columns:
                print(f"WARNING [{sheet_key}] manual-mapped column "
                      f"'{source_var}' not found in sheet -- skipped")
                continue

            value = r.get(source_var)
            if pd.isna(value) or value == "":
                continue

            row = base.copy()
            row.update({
                "Domain": domain,
                "Standard_VAR": std_var,
                "Standard_LABEL": std_label,
                "VALUE": value,
                "SOURCE_FORM": sheet_key,
                "SOURCE_VAR": source_var
            })
            rows.append(row)

    return pd.DataFrame(rows)


def split_by_domain(df):
    """
    Split a combined EAV dataframe into one dataframe per Standard
    Domain so each domain can be written to its own output sheet.
    """

    if df.empty:
        return {}
    return {
        domain: group.reset_index(drop=True)
        for domain, group in df.groupby("Domain", dropna=False)
    }


def choose_data_sheet(xls):
    """
    Pick the workbook sheet holding the main REDCap export, preferring
    a name containing 'SYNTHETIC' or 'REDCAP'; falls back to the first
    sheet that isn't README or one of the manually-mapped sheets.
    """

    for name in xls.sheet_names:
        upper = name.upper()
        if "SYNTHETIC" in upper or "REDCAP" in upper:
            return name
    candidates = [name for name in xls.sheet_names
                  if name.upper() != "README"
                  and name.lower() not in MANUAL_SHEET_MAPPINGS]
    if not candidates:
        raise ValueError("No usable data worksheet found")
    return candidates[0]


def process_t006(dict_path, source_path, output_path):
    '''
    Processing the T006 REDCap export end-to-end: load the dictionary,
    melt scalar/positional/manual sheets into EAV rows per domain, and
    write the combined result to one Excel workbook.
    '''

    mapping = load_t006_dictionary(dict_path)
    xls = pd.ExcelFile(source_path)
    data_sheet = choose_data_sheet(xls)
    df = xls.parse(data_sheet)
    df.columns = [str(c).strip().lower() for c in df.columns]
    event_column = find_event_column(df)

    # find whichever subject identifier column this export actually has
    subject_col = next(
        (c for c in ("record_id", "recordid", "subjid") if c in df.columns),
        None,
    )
    if subject_col is None:
        raise ValueError("No subject identifier column found in data sheet")

    # derive VISITNUM per row
    # then order rows so SeqNum increases
    # chronologically within each subject
    df["_VISITNUM"] = df[event_column].map(derive_visitnum)
    df = df.sort_values([subject_col, "_VISITNUM"], na_position="last")
    df = df.reset_index(drop=True)
    df["_SEQNUM"] = df.groupby(subject_col, dropna=False).cumcount() + 1

    # backfill subjid across a subject's repeated rows so every visit
    # row carries the same subject identifier
    if "subjid" not in df.columns:
        df["subjid"] = df[subject_col]
    else:
        df["subjid"] = df["subjid"].replace("", pd.NA)
        df["subjid"] = (
            df.groupby(subject_col, dropna=False)["subjid"]
            .transform(lambda s: s.ffill().bfill())
        )

    # scalar (non-positional) fields first
    excluded = positional_source_vars()
    scalar = melt_scalar_fields(df, mapping, event_column, excluded)
    outputs = split_by_domain(scalar)

    lookup = make_map_lookup(mapping)

    # positional PE/VS fields need their own melt logic
    pe = melt_pe(df, lookup, event_column)
    vs = melt_vs(df, lookup, event_column)
    if not pe.empty:
        outputs["PE"] = pe
    if not vs.empty:
        outputs["VS"] = vs

    # subject linkage get collected into
    # their own dedicated output sheet rather than merged into a domain
    sheet_lookup = {name.lower(): name for name in xls.sheet_names}
    linkage_frames = []
    for sheet_key in MANUAL_SHEET_MAPPINGS:
        actual_name = sheet_lookup.get(sheet_key)

        if actual_name is None:
            print(f"NOTE: manual-mapped sheet '{sheet_key}' not found "
                  f"in workbook -- skipped")
            continue

        mdf = xls.parse(actual_name)
        mdf.columns = [str(c).strip().lower() for c in mdf.columns]
        manual_eav = melt_manual_sheet(mdf, sheet_key)

        if not manual_eav.empty:
            linkage_frames.append(manual_eav)

    if linkage_frames:
        outputs["SUBJECT_LINKAGE"] = pd.concat(linkage_frames,
                                               ignore_index=True)

    # write sheets in a fixed clinical-review order, unrecognized
    # domains appended alphabetically at the end
    preferred_order = ["DM", "DS", "SV", "MH", "PE", "VS", "BE", "BS", "IE",
                       "CM", "EOS", "CO", "SUBJECT_LINKAGE"]

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        remaining_domains = sorted(set(outputs) - set(preferred_order))
        ordered_domains = preferred_order + remaining_domains

        for domain in ordered_domains:
            eav = outputs.get(domain)
            if eav is None or eav.empty:
                continue
            eav.to_excel(writer, sheet_name=domain[:31], index=False)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python t006_vtov_fixed.py"
              "Clinical_Mapping_T00-Dict-0818.csv"
              "IVI_T006_Dummy-data.xlsx T006_EAV_output.xlsx")
        sys.exit(1)
    process_t006(sys.argv[1], sys.argv[2], sys.argv[3])

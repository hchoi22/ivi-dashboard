# ETL Pipeline

## 1. Introduction

This ETL pipeline transforms three horizontally-structured artificially generated clinical data exports based on the IVI Vi-DT study, specifically STUDY_A, STUDY_B, and STUDY_C. It exports into a unified Entity-Attribute-Value (EAV) schema in Postgres, mapped to CDISC CDASHIG v2.3 and SDTMIG v3.4.

## 2. Pipeline flow diagram.

```
┌───────────────────────────────────────────────────────────────────────┐
│                        1. Raw Excel Files                             │
│   • STUDY_A.xlsx                                                      │
│   • STUDY_B.xlsx                                                      │
│   • STUDY_C.xlsx.                                                     │
└──────────────────────────────────┬────────────────────────────────────┘
                                   │
                                   ▼
┌───────────────────────────────────────────────────────────────────────┐
│                   2. Transformation (t00X_htov.py)                    │
│   • Unpivots dynamic horizontal columns                               │
│   • Standardizes field names & entity identifiers                     │
└──────────────────────────────────┬────────────────────────────────────┘
                                   │
                                   ▼
┌───────────────────────────────────────────────────────────────────────┐
│             3. Intermediate Checkpoint (T00X_EAV_output.xlsx)         │
│   • Uniform Entity-Attribute-Value layout                             │
│   • Allows visual audit before database insertion                     │
└──────────────────────────────────┬────────────────────────────────────┘
                                   │
                                   ▼
┌───────────────────────────────────────────────────────────────────────┐
│              4. Ingestion Engine (load_eav_to_postgres.py)            │
│   • Type enforcement & NULL handling                                  │
│   • Executes batch inserts into database                              │
└──────────────────────────────────┬────────────────────────────────────┘
                                   │
                                   ▼
┌───────────────────────────────────────────────────────────────────────┐
│                   5. Relational Target (PostgreSQL)                   │
│   • Central eav_fact_data table                                       │
│   • Indexed for relational SQL queries                                │
└───────────────────────────────────────────────────────────────────────┘
```

## 3. Why EAV.

The three studies (STUDY_A, STUDY_B, STUDY_C) have incompatible horizontal layouts, each following a different set of variables. An Entity-Attribute-Value (EAV) layout allows a single schema to absorb all three without a giant sparse table.

A typical horizontal layout has a strong advantage in its flexible structure, which can extend its tables further. However, this advantage becomes a key bottleneck when there are too many null values within each row. The EAV structure directly addresses this problem by only storing rows for attributes that actually contain data, making it highly efficient for sparse datasets. Moreover, the EAV structure gives a clear layout that enables single-attribute queries to easily find all entities that share a specific property.

The tradeoff is that reconstructing a single record spanning multiple domains requires complex joins and pivot queries. This complexity is addressed in the database design through indexing, CTEs, and the API layer.

## 4. CDISC mapping approach.

When designing an EAV-style layout, one of the most important attributes is a standardized variable that differentiates each entity, attribute, and value in the database. For this project, I've used CDISC standards (CDASHIG v2.3 and SDTMIG v3.4) to map every variable in the STUDY_A, STUDY_B, and STUDY_C studies to a standard domain, standard variable, and standard label. Given the large number of variables across each study, and the disparity among studies in how variables were originally named, there are cases that couldn't be mapped directly to a CDISC standard. In those cases, I applied sponsor-defined standard variables that closely follow the naming patterns in SDTMIG v3.4.

For example, a lab result value maps to LBORRES under SDTMIG v3.4. As a sponsor-defined case, concomitant medication with an unknown dosing frequency is mapped to CMFRQUNK. It follows the standard CM domain prefix while using FRQ, a fragment commonly used in SDTMIG v3.4 to indicate frequency.

## 5. Schema summary.

The schema is separated into three kinds of tables: subjects, domain tables, and the linkage table. The subjects table holds all participants, each in their own row. The domain tables cover the rest of the artificially generated clinical data, with each CDISC domain occupying one dedicated table. Lastly, the linkage table holds the linkage information between STUDY_A and STUDY_C. It uses a separate format, since it exists specifically to hold cross-study subject information rather than domain facts.

The subjects table holds one row per participant, keyed by a serial subject_key. This table stores all natural identifiers as columns, including source_study, studyid, subjid, scrno, and record_id. No single identifier is reliable across every study and visit, so there is no composite key. A composite key would require all of these identifiers to be present on every row, which the data doesn't support.

This project defines fifteen domain tables in total, each corresponding to one SDTM domain. Twelve of the domains (dm, ds, sv, mh, pe, vs, be, bs, ie, cm, eos, co) are collected across all three studies; the remaining three (ex, ae, lb) are STUDY_A-only, since STUDY_B and STUDY_C don't collect exposure, adverse event, or laboratory data. All fifteen share a common EAV column set: fact_id (primary key), subject_key (foreign key), source_study, standard_var, standard_label, value, value_code, seqnum, and visitnum. Each domain table is indexed on subject_key and standard_var, supporting the two most common access patterns without a full table scan: "everything for this subject" and "every subject with this attribute."

The subject_linkage table resolves the cross-study relationship. For this project, that relationship is specifically between STUDY_A and STUDY_C: STUDY_A is the second phase of the Vi-DT clinical study, and T006 is the follow-up study on participants from that Phase II cohort. This table stores each respective participant's subject key as a pair, along with a linkage_type describing how the match was established.

## 6. Normalization

This EAV schema design clearly satisfies normalization up through 2NF. The domain tables satisfy 1st normal form: every row holds one atomic fact, a single value paired with a single fact_id, with no repeating groups. 1NF is enforced upstream by the *_htov.py scripts, which convert each study's horizontal, one-row-per-subject layout into one-row-per-fact before the data is loaded into the database.

The schema also satisfies 2nd normal form by using a surrogate primary key (fact_id) rather than a composite key. This avoids any partial-dependency situation, since every column depends solely on the surrogate primary key, fact_id.

At the same time, this structure fails to meet 3rd normal form, since standard_label depends on standard_var, not solely on fact_id. Based on the 3rd normal form, this transitive dependency means a single label has to be reconciled everywhere it was inserted, rather than in one place. In addition, value is stored as plain text with no column-level type enforcement. Lastly, reconstructing one subject's full record requires joining and pivoting many rows back into a single wide row, instead of a single-table read.

The EAV design never eliminates these problems, but each is mitigated elsewhere in the system. The 3rd normal form gap comes from the transitive dependency of standard_label on standard_var, which surfaces as a query-time concern rather than a storage-time one. I've addressed that at query time through the API layer, which filters and casts values explicitly instead of relying on column-level typing. The use of joins and indexed CTEs within the API layer also means these queries run efficiently despite the extra reconstruction cost, so the 3rd-normal-form gap is absorbed at the query layer rather than left for every downstream consumer to solve independently. In short, the schema trades strict 3NF compliance for the flexibility EAV provides across three structurally incompatible studies, and recovers the cost of that trade through indexing and the API layer rather than through the schema itself.

## 7. Study-specific quirks section.

The ETL pipeline's core task is transforming three horizontally structured datasets into one unified schema. When building a common structure across three studies with distinct source formats, accounting for each study's edge cases becomes critical, closing the gap between them is what makes a single shared schema possible at all.

The first edge case comes from STUDY_A screen failures, which are identified by a screening number (scrno) with no subject ID (subjid). This is critical to understanding the structure of the data: participants who fail screening are never assigned a subjid, so scrno is the only identifier available for that portion of the population.

The second edge case comes from the linkage between STUDY_A and STUDY_C. The two studies assign each participant a different subjid, but both IDs share the same trailing SYN-##### suffix, so the pipeline links the two studies by matching on that shared suffix rather than assuming the IDs are identical.

The third edge case comes from STUDY_C's structure, which differs completely from T002 and T006, both of which use a separate sheet per domain. Due to this structural difference, column-casing inconsistencies also appear across the three studies' outputs (for example, StandardVAR versus Standard_VAR). These are reconciled by COLUMN_ALIASES in the loader.

## 8. Data provenance/privacy note.

All data referenced and processed by this pipeline is fully artificially generated, resembling the structure of IVI's Vi-DT clinical study exports (STUDY_A, STUDY_B, STUDY_C) without containing any real participant information. No real subject identifiers, dates, or clinical values are included in this repository or its outputs. Source files themselves are not included in this repository due to data-sharing restrictions; this documentation describes the transformation logic, schema design, and mapping approach rather than providing a runnable end-to-end example.

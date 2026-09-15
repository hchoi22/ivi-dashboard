-- 1. Subject identity dimension (NOT domain data -- pure identity)
CREATE TABLE subjects (
    subject_key BIGSERIAL PRIMARY KEY,
    source_study VARCHAR(10) NOT NULL,
    studyid VARCHAR(50),
    subjid VARCHAR(50),
    scrno VARCHAR(50),
    record_id VARCHAR(50),
    UNIQUE (source_study, subjid),
    UNIQUE (source_study, scrno),
	UNIQUE (source_study, record_id)
);

CREATE INDEX idx_subjects_subjid ON subjects (subjid);
CREATE INDEX idx_subjects_scrno ON subjects (scrno);

-- 2. Cross-study linkage
CREATE TABLE subject_linkage (
    linkage_id BIGSERIAL PRIMARY KEY,
    t002_subject_key BIGINT REFERENCES subjects(subject_key),
    t006_subject_key BIGINT REFERENCES subjects(subject_key),
    linkage_type VARCHAR(30),
    UNIQUE (t002_subject_key, t006_subject_key)
);

-- 3. Generic domain table shape, repeated per Standard_Domain
CREATE TABLE dm (
    fact_id BIGSERIAL PRIMARY KEY,
    subject_key BIGINT NOT NULL REFERENCES subjects(subject_key),
    source_study VARCHAR(10) NOT NULL,
    standard_var VARCHAR(50) NOT NULL,
    standard_label TEXT,
    value TEXT,
    value_code TEXT,
    seqnum INT,
    visitnum NUMERIC
);

CREATE TABLE ds (LIKE dm INCLUDING ALL);
CREATE TABLE sv (LIKE dm INCLUDING ALL);
CREATE TABLE mh (LIKE dm INCLUDING ALL);
CREATE TABLE pe (LIKE dm INCLUDING ALL);
CREATE TABLE vs (LIKE dm INCLUDING ALL);
CREATE TABLE be (LIKE dm INCLUDING ALL);
CREATE TABLE bs (LIKE dm INCLUDING ALL);
CREATE TABLE ie (LIKE dm INCLUDING ALL);
CREATE TABLE cm (LIKE dm INCLUDING ALL);
CREATE TABLE eos (LIKE dm INCLUDING ALL);
CREATE TABLE co (LIKE dm INCLUDING ALL); -- Comment
CREATE TABLE ex (LIKE dm INCLUDING ALL); -- Exposure (T002 only)
CREATE TABLE ae (LIKE dm INCLUDING ALL); -- AE+SOLAE+REACTOAE+SAE consolidated (T002 only)
CREATE TABLE lb (LIKE dm INCLUDING ALL); -- Laboratory (T002 only)

-- Indexes for common query patterns
CREATE INDEX idx_dm_subject ON dm (subject_key);
CREATE INDEX idx_dm_var ON dm (standard_var);

CREATE INDEX idx_ds_subject ON ds (subject_key);
CREATE INDEX idx_ds_var ON ds (standard_var);

CREATE INDEX idx_sv_subject ON sv (subject_key);
CREATE INDEX idx_sv_var ON sv (standard_var);

CREATE INDEX idx_mh_subject ON mh (subject_key);
CREATE INDEX idx_mh_var ON mh (standard_var);

CREATE INDEX idx_pe_subject ON pe (subject_key);
CREATE INDEX idx_pe_var ON pe (standard_var);

CREATE INDEX idx_vs_subject ON vs (subject_key);
CREATE INDEX idx_vs_var ON vs (standard_var);

CREATE INDEX idx_be_subject ON be (subject_key);
CREATE INDEX idx_be_var ON be (standard_var);

CREATE INDEX idx_bs_subject ON bs (subject_key);
CREATE INDEX idx_bs_var ON bs (standard_var); 

CREATE INDEX idx_ie_subject ON ie (subject_key);
CREATE INDEX idx_ie_var ON ie (standard_var);

CREATE INDEX idx_cm_subject ON cm (subject_key);
CREATE INDEX idx_cm_var ON cm (standard_var);

CREATE INDEX idx_eos_subject ON eos (subject_key);
CREATE INDEX idx_eos_var ON eos (standard_var);

CREATE INDEX idx_co_subject ON co (subject_key);
CREATE INDEX idx_co_var ON co (standard_var);

CREATE INDEX idx_ex_subject ON ex (subject_key);
CREATE INDEX idx_ex_var ON ex (standard_var);

CREATE INDEX idx_ae_subject ON ae (subject_key);
CREATE INDEX idx_ae_var ON ae (standard_var);

CREATE INDEX idx_lb_subject ON lb (subject_key);
CREATE INDEX idx_lb_var ON lb (standard_var);

-- 4. Registry of which domains exist, for validation
CREATE TABLE domain_registry (
    standard_domain VARCHAR(20) PRIMARY KEY,
    table_name VARCHAR(30) NOT NULL,
    applies_to VARCHAR(30) NOT NULL -- e.g. 'T002,T005,T006' or 'T002 only'
);

INSERT INTO domain_registry VALUES
('DM', 'dm', 'T002,T005,T006'),
('DS', 'ds', 'T002,T005,T006'),
('SV', 'sv', 'T002,T005,T006'),
('MH', 'mh', 'T002,T005,T006'),
('PE', 'pe', 'T002,T005,T006'),
('VS', 'vs', 'T002,T005,T006'),
('BE', 'be', 'T002,T005,T006'),
('BS', 'bs', 'T002,T005,T006'),
('IE', 'ie', 'T002,T005,T006'),
('CM', 'cm', 'T002,T005,T006'),
('EOS', 'eos', 'T002,T005,T006'),
('CO', 'co', 'T002,T005,T006'),
('EX', 'ex', 'T002 only'),
('AE', 'ae', 'T002 only'),
('LB', 'lb', 'T002 only');
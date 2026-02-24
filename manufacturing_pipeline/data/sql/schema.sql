CREATE TABLE IF NOT EXISTS Parts (
    PartID INTEGER PRIMARY KEY AUTOINCREMENT,
    PartNumber TEXT NOT NULL,
    Revision TEXT,
    Material TEXT,
    PartType TEXT,
    GeneralTolerance TEXT,
    ConfidenceScore REAL,
    ManualReviewRequired INTEGER DEFAULT 0,
    AnalysisDate TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Holes (
    HoleID INTEGER PRIMARY KEY AUTOINCREMENT,
    PartID INTEGER,
    HoleType TEXT,
    DiameterNominal REAL,
    DiameterUpperDev REAL,
    DiameterLowerDev REAL,
    FitClass TEXT,
    PositionX REAL,
    PositionY REAL,
    PositionZ REAL,
    Depth REAL,
    DataSource TEXT,
    FOREIGN KEY(PartID) REFERENCES Parts(PartID)
);

CREATE TABLE IF NOT EXISTS PostProcessing (
    ProcessID INTEGER PRIMARY KEY AUTOINCREMENT,
    PartID INTEGER,
    Operation TEXT,
    Specification TEXT,
    Sequence INTEGER,
    FOREIGN KEY(PartID) REFERENCES Parts(PartID)
);

-- API job history (persistent log of all files analyzed via the REST API)
CREATE TABLE IF NOT EXISTS api_jobs (
    job_id TEXT PRIMARY KEY,
    file_name TEXT NOT NULL,
    file_hash TEXT,
    file_size_bytes INTEGER,
    status TEXT NOT NULL DEFAULT 'queued',
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    result_json TEXT,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_api_jobs_status ON api_jobs(status);
CREATE INDEX IF NOT EXISTS idx_api_jobs_created_at ON api_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_api_jobs_file_hash ON api_jobs(file_hash);

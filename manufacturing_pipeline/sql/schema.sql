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

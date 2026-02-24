-- OPPORTUNITIES
CREATE TABLE IF NOT EXISTS opportunities (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    company           TEXT NOT NULL,
    role_title        TEXT NOT NULL,
    job_family        TEXT CHECK(job_family IN ('A','B','C','D','E')),
    tier              INTEGER CHECK(tier IN (1,2,3)),
    stage             TEXT NOT NULL DEFAULT 'Prospect'
                      CHECK(stage IN (
                        'Prospect','Warm Lead','Applied',
                        'Recruiter Screen','HM Interview',
                        'Loop','Offer Pending','Closed'
                      )),
    source            TEXT CHECK(source IN (
                        'LinkedIn','Referral','Job Board',
                        'Outbound','Other'
                      )),
    date_added        DATE NOT NULL DEFAULT (date('now')),
    date_applied      DATE,
    date_closed       DATE,
    close_reason      TEXT CHECK(close_reason IN (
                        'Accepted','Declined','Rejected',
                        'Ghosted','Withdrew',NULL
                      )),
    fit_score         INTEGER CHECK(fit_score BETWEEN 1 AND 10),
    salary_range      TEXT,
    jd_url            TEXT,
    jd_raw            TEXT,
    jd_keywords       TEXT,
    resume_version    TEXT,
    next_action       TEXT,
    next_action_date  DATE,
    notes             TEXT,
    ai_fit_summary    TEXT,
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- CONTACTS
CREATE TABLE IF NOT EXISTS contacts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id    INTEGER REFERENCES opportunities(id),
    full_name         TEXT NOT NULL,
    title             TEXT,
    company           TEXT,
    linkedin_url      TEXT,
    email             TEXT,
    contact_type      TEXT CHECK(contact_type IN (
                        'Hiring Manager','Peer','Recruiter',
                        'Alumni','Referral Source','Other'
                      )),
    outreach_day0     DATE,
    outreach_day3     DATE,
    outreach_day7     DATE,
    response_status   TEXT DEFAULT 'Pending'
                      CHECK(response_status IN (
                        'Pending','Responded','No Response','Meeting Scheduled'
                      )),
    call_completed    BOOLEAN DEFAULT 0,
    referral_asked    BOOLEAN DEFAULT 0,
    referral_given    BOOLEAN DEFAULT 0,
    notes             TEXT,
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ACTIVITY LOG (immutable append-only)
CREATE TABLE IF NOT EXISTS activity_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id    INTEGER REFERENCES opportunities(id),
    contact_id        INTEGER REFERENCES contacts(id),
    activity_type     TEXT NOT NULL CHECK(activity_type IN (
                        'Stage Change','Outreach Sent','Follow-Up Sent',
                        'Response Received','Call Completed','Application Submitted',
                        'Interview Scheduled','Interview Completed',
                        'Offer Received','AI Action','Note Added'
                      )),
    description       TEXT,
    metadata          TEXT,
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- TRIGGERS: auto-update updated_at
CREATE TRIGGER IF NOT EXISTS opp_updated
AFTER UPDATE ON opportunities
BEGIN
  UPDATE opportunities SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS contact_updated
AFTER UPDATE ON contacts
BEGIN
  UPDATE contacts SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- VIEWS
CREATE VIEW IF NOT EXISTS today_queue AS
SELECT o.id, o.company, o.role_title, o.stage, o.next_action, o.next_action_date,
       c.full_name as contact_name, c.response_status
FROM opportunities o
LEFT JOIN contacts c ON c.opportunity_id = o.id
WHERE o.stage != 'Closed'
  AND (o.next_action_date <= date('now') OR c.outreach_day0 = date('now','- 3 days') OR c.outreach_day0 = date('now','- 7 days'))
ORDER BY o.tier ASC, o.next_action_date ASC;

CREATE VIEW IF NOT EXISTS warm_leads AS
SELECT o.*, c.full_name, c.response_status
FROM opportunities o
LEFT JOIN contacts c ON c.opportunity_id = o.id
WHERE o.stage IN ('Warm Lead','Applied');

CREATE VIEW IF NOT EXISTS waiting_on AS
SELECT o.company, o.role_title, o.stage, c.full_name, c.outreach_day0, c.response_status
FROM opportunities o
JOIN contacts c ON c.opportunity_id = o.id
WHERE c.response_status = 'Pending'
  AND c.outreach_day0 <= date('now','-2 days');

CREATE VIEW IF NOT EXISTS pipeline_summary AS
SELECT stage, COUNT(*) as count,
       AVG(fit_score) as avg_fit,
       MIN(date_added) as oldest
FROM opportunities
WHERE stage != 'Closed'
GROUP BY stage;

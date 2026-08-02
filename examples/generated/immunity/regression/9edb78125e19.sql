CREATE TABLE historical_negative_billing (
    record_id TEXT PRIMARY KEY,
    billing_amount_cents INTEGER NOT NULL,
    region TEXT NOT NULL
);
INSERT INTO historical_negative_billing VALUES ('patient-001', -5000, 'north');
INSERT INTO historical_negative_billing VALUES ('patient-002', 12000, 'south');
INSERT INTO historical_negative_billing VALUES ('patient-003', 8000, 'west');

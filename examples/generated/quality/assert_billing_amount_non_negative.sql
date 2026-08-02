-- LineageGuard incident 9edb78125e19
-- Returns violating rows; an empty result means the assertion passes.
SELECT *
FROM "raw_patients"
WHERE "billing_amount" < 0

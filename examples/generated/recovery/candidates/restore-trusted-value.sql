SELECT current.record_id,
       CASE WHEN current.billing_amount_cents < 0
            THEN trusted.billing_amount_cents
            ELSE current.billing_amount_cents END AS billing_amount_cents,
       current.region
FROM current_data AS current
LEFT JOIN trusted_snapshot AS trusted USING (record_id)
ORDER BY current.record_id

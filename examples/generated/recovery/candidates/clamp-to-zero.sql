SELECT record_id,
       CASE WHEN billing_amount_cents < 0 THEN 0 ELSE billing_amount_cents END
           AS billing_amount_cents,
       region
FROM current_data
ORDER BY record_id

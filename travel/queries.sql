-- 2) Amount spent on booking by registered vs non-registered users
SELECT
  u.is_registered,
  SUM(b.amount_total) AS total_amount_spent,
  COUNT(DISTINCT b.booking_id) AS distinct_bookings
FROM bookings b
JOIN users u
  ON u.user_id = b.user_id
WHERE b.is_current = TRUE
GROUP BY u.is_registered
ORDER BY u.is_registered DESC;




-- 3) Top 10 searched attribute values for each year
-- Notes:
-- - Returns top searched values (not top search_type or combined search signatures)
-- - Times are bucketed to hour-of-day to avoid near-unique raw timestamps
WITH base_searches AS (
  SELECT
    s.search_id,
    d.year
  FROM searches s
  JOIN "date" d
    ON d.date_id = s.date_id
),
search_value_events AS (
  -- FLIGHT attributes
  SELECT
    b.year AS year,
    'FLIGHT' AS business_line,
    'departure_airport' AS attribute_name,
    fs.departure_airport AS attribute_value
  FROM base_searches b
  JOIN flight_search fs
    ON fs.search_id = b.search_id

  UNION ALL

  SELECT
    b.year AS year,
    'FLIGHT' AS business_line,
    'arrival_airport' AS attribute_name,
    fs.arrival_airport AS attribute_value
  FROM base_searches b
  JOIN flight_search fs
    ON fs.search_id = b.search_id

  UNION ALL

  SELECT
    b.year AS year,
    'FLIGHT' AS business_line,
    'departure_hour' AS attribute_name,
    LPAD(TO_VARCHAR(DATE_PART('HOUR', fs.departure_time)), 2, '0') AS attribute_value
  FROM base_searches b
  JOIN flight_search fs
    ON fs.search_id = b.search_id

  UNION ALL

  SELECT
    b.year AS year,
    'FLIGHT' AS business_line,
    'arrival_hour' AS attribute_name,
    LPAD(TO_VARCHAR(DATE_PART('HOUR', fs.arrival_time)), 2, '0') AS attribute_value
  FROM base_searches b
  JOIN flight_search fs
    ON fs.search_id = b.search_id

  UNION ALL

  SELECT
    b.year AS year,
    'FLIGHT' AS business_line,
    'passenger_capacity' AS attribute_name,
    TO_VARCHAR(fs.passenger_capacity) AS attribute_value
  FROM base_searches b
  JOIN flight_search fs
    ON fs.search_id = b.search_id

  -- HOTEL attributes
  UNION ALL

  SELECT
    b.year AS year,
    'HOTEL' AS business_line,
    'location' AS attribute_name,
    hs.location AS attribute_value
  FROM base_searches b
  JOIN hotel_search hs
    ON hs.search_id = b.search_id

  UNION ALL

  SELECT
    b.year AS year,
    'HOTEL' AS business_line,
    'rooms_requested' AS attribute_name,
    TO_VARCHAR(hs.rooms_requested) AS attribute_value
  FROM base_searches b
  JOIN hotel_search hs
    ON hs.search_id = b.search_id

  -- CAR attributes
  UNION ALL

  SELECT
    b.year AS year,
    'CAR' AS business_line,
    'model' AS attribute_name,
    cs.model AS attribute_value
  FROM base_searches b
  JOIN car_search cs
    ON cs.search_id = b.search_id

  UNION ALL

  SELECT
    b.year AS year,
    'CAR' AS business_line,
    'passenger_capacity' AS attribute_name,
    TO_VARCHAR(cs.passenger_capacity) AS attribute_value
  FROM base_searches b
  JOIN car_search cs
    ON cs.search_id = b.search_id
),
cleaned_events AS (
  SELECT
    year,
    business_line,
    attribute_name,
    attribute_value
  FROM search_value_events
  WHERE attribute_value IS NOT NULL
    AND TRIM(attribute_value) <> ''
),
yearly_value_counts AS (
  SELECT
    year,
    business_line,
    attribute_name,
    attribute_value,
    COUNT(*) AS search_count
  FROM cleaned_events
  GROUP BY year, business_line, attribute_name, attribute_value
),
ranked_values AS (
  SELECT
    year,
    business_line,
    attribute_name,
    attribute_value,
    search_count,
    ROW_NUMBER() OVER (
      PARTITION BY year
      ORDER BY search_count DESC, business_line, attribute_name, attribute_value
    ) AS rn
  FROM yearly_value_counts
)
SELECT
  year,
  rn AS rank_in_year,
  business_line,
  attribute_name,
  attribute_value,
  search_count
FROM ranked_values
WHERE rn <= 10
ORDER BY year, rank_in_year;




-- 3A) Top 10 combined searches for each year
-- Purpose:
-- - Treat an entire search payload as one "search signature"
-- - Rank most frequent combined signatures per year
-- Notes:
-- - Flight times are bucketed to hour for better grouping
WITH base_searches AS (
  SELECT
    s.search_id,
    d.year
  FROM searches s
  JOIN "date" d
    ON d.date_id = s.date_id
),
combined_searches AS (
  -- FLIGHT combined search signature
  SELECT
    b.year,
    'FLIGHT' AS business_line,
    CONCAT(
      'dep=', COALESCE(fs.departure_airport, 'NA'),
      '|arr=', COALESCE(fs.arrival_airport, 'NA'),
      '|dep_hour=', COALESCE(LPAD(TO_VARCHAR(DATE_PART('HOUR', fs.departure_time)), 2, '0'), 'NA'),
      '|arr_hour=', COALESCE(LPAD(TO_VARCHAR(DATE_PART('HOUR', fs.arrival_time)), 2, '0'), 'NA'),
      '|pax_cap=', COALESCE(TO_VARCHAR(fs.passenger_capacity), 'NA')
    ) AS search_signature
  FROM base_searches b
  JOIN flight_search fs
    ON fs.search_id = b.search_id

  UNION ALL

  -- HOTEL combined search signature
  SELECT
    b.year,
    'HOTEL' AS business_line,
    CONCAT(
      'location=', COALESCE(hs.location, 'NA'),
      '|rooms_requested=', COALESCE(TO_VARCHAR(hs.rooms_requested), 'NA')
    ) AS search_signature
  FROM base_searches b
  JOIN hotel_search hs
    ON hs.search_id = b.search_id

  UNION ALL

  -- CAR combined search signature
  SELECT
    b.year,
    'CAR' AS business_line,
    CONCAT(
      'model=', COALESCE(cs.model, 'NA'),
      '|pax_cap=', COALESCE(TO_VARCHAR(cs.passenger_capacity), 'NA')
    ) AS search_signature
  FROM base_searches b
  JOIN car_search cs
    ON cs.search_id = b.search_id
),
yearly_signature_counts AS (
  SELECT
    year,
    business_line,
    search_signature,
    COUNT(*) AS search_count
  FROM combined_searches
  GROUP BY year, business_line, search_signature
),
ranked_signatures AS (
  SELECT
    year,
    business_line,
    search_signature,
    search_count,
    ROW_NUMBER() OVER (
      PARTITION BY year
      ORDER BY search_count DESC, business_line, search_signature
    ) AS rn
  FROM yearly_signature_counts
)
SELECT
  year,
  rn AS rank_in_year,
  business_line,
  search_signature,
  search_count
FROM ranked_signatures
WHERE rn <= 10
ORDER BY year, rank_in_year;



-- 4) Percentage growth in booking amount by year and business lines (FLIGHT, HOTEL, CAR)
-- Logic:
-- 1) Use current booking version only (is_current = TRUE)
-- 2) Join booking_items to get business_line from booking_type
-- 3) Aggregate yearly booking totals
-- 4) Use LAG to compare to prior year within each business line
-- 5) Compute YoY % growth
WITH yearly_booking_amount AS (
  SELECT
    d.year,
    bi.booking_type AS business_line,
    SUM(b.amount_total) AS total_amount
  FROM bookings b
  JOIN booking_items bi
    ON bi.booking_sk = b.booking_sk
  JOIN "date" d
    ON d.date_id = b.date_id
  WHERE b.is_current = TRUE
    AND bi.booking_type IN ('FLIGHT', 'HOTEL', 'CAR')
  GROUP BY d.year, bi.booking_type
),
with_previous AS (
  SELECT
    year,
    business_line,
    total_amount,
    LAG(total_amount) OVER (
      PARTITION BY business_line
      ORDER BY year
    ) AS prev_year_amount
  FROM yearly_booking_amount
)
SELECT
  year,
  business_line,
  total_amount,
  prev_year_amount,
  CASE
    WHEN prev_year_amount IS NULL OR prev_year_amount = 0 THEN NULL
    ELSE ROUND(
      ((total_amount - prev_year_amount) / prev_year_amount::FLOAT) * 100,
      2
    )
  END AS yoy_pct_growth
FROM with_previous
ORDER BY business_line, year;
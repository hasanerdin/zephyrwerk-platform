WITH nan_to_null AS(
    SELECT
        timestamp::TIMESTAMP WITH TIME ZONE,
        signal AS signal_name,
        NULLIF(value, 'NaN')::numeric AS value,
        unit
    FROM
        {{ source('raw', 'smard_generation') }}
)
-- Non-pumped-storage generation signals
SELECT
    *
FROM nan_to_null
WHERE signal_name NOT IN ('NUCLEAR', 'PUMPED_STORAGE')
AND value IS NOT NULL
AND value >= 0

UNION ALL

-- Nuclear — retired April 2023
SELECT
    *
FROM nan_to_null
WHERE signal_name = 'NUCLEAR'
AND timestamp <= '{{ var("nuclear_retirement_date") }}'::TIMESTAMP WITH TIME ZONE
AND value IS NOT NULL
AND value >= 0

UNION ALL

-- Pumped storage — can be negative (consumption mode)
SELECT
    *
FROM nan_to_null
WHERE signal_name = 'PUMPED_STORAGE'
AND value IS NOT NULL
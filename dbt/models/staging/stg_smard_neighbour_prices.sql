WITH nan_to_null AS(
    SELECT
        timestamp :: TIMESTAMP WITH TIME ZONE,
        signal AS signal_name,
        NULLIF(value, 'NaN') AS value,
        unit
    FROM
        {{ source('raw', 'smard_neighbour_prices') }}
)
SELECT 
    *
FROM 
    nan_to_null
WHERE 
    value IS NOT NULL
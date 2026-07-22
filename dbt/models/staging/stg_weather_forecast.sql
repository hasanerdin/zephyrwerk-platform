SELECT
    timestamp :: TIMESTAMP WITH TIME ZONE,
    region,
    signal_type AS signal_name,
    NULLIF(value, 'NaN') AS value,
    unit,
    fetched_at :: TIMESTAMP WITH TIME ZONE
FROM
    {{ source('raw', 'weather_forecast') }}

WITH latest_forecast AS (
    SELECT DISTINCT ON (timestamp, region, signal_name)
        timestamp,
        region,
        signal_name,
        value
    FROM {{ ref('stg_weather_forecast') }}
    ORDER BY timestamp, region, signal_name, fetched_at DESC
),

weather_pivot AS (
    SELECT
        timestamp,
        MAX(value) FILTER (WHERE region = 'wind_region_brandenburg' AND signal_name = 'wind_speed_100m')    AS wind_speed_100m_brandenburg,
        MAX(value) FILTER (WHERE region = 'wind_region_brandenburg' AND signal_name = 'wind_direction_100m') AS wind_direction_100m_brandenburg,
        MAX(value) FILTER (WHERE region = 'wind_region_brandenburg' AND signal_name = 'shortwave_radiation') AS shortwave_radiation_brandenburg,
        MAX(value) FILTER (WHERE region = 'wind_region_brandenburg' AND signal_name = 'cloud_cover')         AS cloud_cover_brandenburg,
        MAX(value) FILTER (WHERE region = 'wind_region_brandenburg' AND signal_name = 'temperature_2m')      AS temperature_2m_brandenburg,

        MAX(value) FILTER (WHERE region = 'wind_region_schleswig' AND signal_name = 'wind_speed_100m')    AS wind_speed_100m_schleswig,
        MAX(value) FILTER (WHERE region = 'wind_region_schleswig' AND signal_name = 'wind_direction_100m') AS wind_direction_100m_schleswig,
        MAX(value) FILTER (WHERE region = 'wind_region_schleswig' AND signal_name = 'shortwave_radiation') AS shortwave_radiation_schleswig,
        MAX(value) FILTER (WHERE region = 'wind_region_schleswig' AND signal_name = 'cloud_cover')         AS cloud_cover_schleswig,
        MAX(value) FILTER (WHERE region = 'wind_region_schleswig' AND signal_name = 'temperature_2m')      AS temperature_2m_schleswig,

        MAX(value) FILTER (WHERE region = 'solar_region_bavaria' AND signal_name = 'wind_speed_100m')    AS wind_speed_100m_bavaria,
        MAX(value) FILTER (WHERE region = 'solar_region_bavaria' AND signal_name = 'wind_direction_100m') AS wind_direction_100m_bavaria,
        MAX(value) FILTER (WHERE region = 'solar_region_bavaria' AND signal_name = 'shortwave_radiation') AS shortwave_radiation_bavaria,
        MAX(value) FILTER (WHERE region = 'solar_region_bavaria' AND signal_name = 'cloud_cover')         AS cloud_cover_bavaria,
        MAX(value) FILTER (WHERE region = 'solar_region_bavaria' AND signal_name = 'temperature_2m')      AS temperature_2m_bavaria,

        MAX(value) FILTER (WHERE region = 'solar_region_bawue' AND signal_name = 'wind_speed_100m')    AS wind_speed_100m_bawue,
        MAX(value) FILTER (WHERE region = 'solar_region_bawue' AND signal_name = 'wind_direction_100m') AS wind_direction_100m_bawue,
        MAX(value) FILTER (WHERE region = 'solar_region_bawue' AND signal_name = 'shortwave_radiation') AS shortwave_radiation_bawue,
        MAX(value) FILTER (WHERE region = 'solar_region_bawue' AND signal_name = 'cloud_cover')         AS cloud_cover_bawue,
        MAX(value) FILTER (WHERE region = 'solar_region_bawue' AND signal_name = 'temperature_2m')      AS temperature_2m_bawue

    FROM latest_forecast
    GROUP BY timestamp
)

SELECT
    w.timestamp,
    w.wind_speed_100m_brandenburg,
    w.wind_direction_100m_brandenburg,
    w.shortwave_radiation_brandenburg,
    w.cloud_cover_brandenburg,
    w.temperature_2m_brandenburg,
    w.wind_speed_100m_schleswig,
    w.wind_direction_100m_schleswig,
    w.shortwave_radiation_schleswig,
    w.cloud_cover_schleswig,
    w.temperature_2m_schleswig,
    w.wind_speed_100m_bavaria,
    w.wind_direction_100m_bavaria,
    w.shortwave_radiation_bavaria,
    w.cloud_cover_bavaria,
    w.temperature_2m_bavaria,
    w.wind_speed_100m_bawue,
    w.wind_direction_100m_bawue,
    w.shortwave_radiation_bawue,
    w.cloud_cover_bawue,
    w.temperature_2m_bawue,
    d.date_day,
    d.year,
    d.quarter,
    d.month,
    d.week_of_year,
    d.day_of_week,
    d.is_weekend,
    d.season,
    d.is_german_public_holiday,
    d.holiday_name,
    d.is_workday

FROM
    weather_pivot AS w
        LEFT JOIN
    {{ ref('dim_date') }} AS d
        ON w.timestamp :: date = d.date_day
ORDER BY w.timestamp

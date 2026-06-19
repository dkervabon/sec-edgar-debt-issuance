with source as (
    select * from {{ source('raw', 'fred_rate_observations') }}
),

deduplicated as (
    select
        *,
        row_number() over (
            partition by series_id, observation_date
            order by ingested_at desc
        ) as _row_num
    from source
    where series_id is not null
      and observation_date is not null
      and value is not null
),

final as (
    select
        series_id,
        observation_date,
        value as rate_value,
        ingested_at
    from deduplicated
    where _row_num = 1
)

select * from final

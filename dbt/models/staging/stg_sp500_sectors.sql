with source as (
    select * from {{ ref('sp500_sectors') }}
),

final as (
    select
        ticker,
        company_name,
        gics_sector,
        gics_sub_industry
    from source
    where ticker is not null
)

select * from final

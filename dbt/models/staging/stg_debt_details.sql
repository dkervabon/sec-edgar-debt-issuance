with source as (
    select * from {{ source('raw', 'edgar_debt_details') }}
),

deduplicated as (
    select
        *,
        row_number() over (
            partition by accession_no
            order by parsed_at desc
        ) as _row_num
    from source
    where accession_no is not null
),

final as (
    select
        accession_no,
        cik,
        entity_name,
        file_date,
        instrument_type,
        principal_amount_usd,
        principal_raw,
        interest_rate_type,
        interest_rate_raw,
        maturity_raw,
        item_203_text,
        parse_success,
        parsed_at
    from deduplicated
    where _row_num = 1
)

select * from final

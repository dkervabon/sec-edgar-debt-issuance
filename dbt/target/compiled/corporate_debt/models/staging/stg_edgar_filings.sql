with source as (
    select * from `sec-edgar-debt`.`raw`.`edgar_8k_filings`
),

deduplicated as (
    select
        *,
        row_number() over (
            partition by accession_no
            order by ingested_at desc
        ) as _row_num
    from source
    where accession_no is not null
),

final as (
    select
        accession_no,
        cik,
        entity_name,
        form_type,
        file_date,
        period_of_report,
        items,
        file_url,
        primary_doc,
        ingested_at
    from deduplicated
    where _row_num = 1
)

select * from final
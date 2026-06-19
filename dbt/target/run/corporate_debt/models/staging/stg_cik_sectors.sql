

  create or replace view `sec-edgar-debt`.`staging`.`stg_cik_sectors`
  OPTIONS()
  as with source as (
    select * from `sec-edgar-debt`.`raw`.`cik_sectors`
),

final as (
    select
        cik,
        entity_name,
        ticker,
        sic_code,
        sic_description,
        coalesce(gics_sector, 'Other') as gics_sector,
        fetched_at
    from source
    where cik is not null
)

select * from final;


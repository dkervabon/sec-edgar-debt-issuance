with filings as (
    select * from `sec-edgar-debt`.`staging`.`stg_edgar_filings`
),

details as (
    select * from `sec-edgar-debt`.`staging`.`stg_debt_details`
),

sectors as (
    select * from `sec-edgar-debt`.`staging`.`stg_cik_sectors`
),

enriched as (
    select
        f.accession_no,
        f.cik,
        f.entity_name,
        f.file_date,
        date_trunc(f.file_date, quarter)        as issuance_quarter,
        extract(year from f.file_date)          as issuance_year,
        extract(quarter from f.file_date)       as issuance_quarter_num,
        d.instrument_type,
        d.principal_amount_usd,
        d.interest_rate_type,
        d.interest_rate_raw,
        d.maturity_raw,
        d.parse_success,
        coalesce(s.gics_sector, 'Other')        as gics_sector,
        s.sic_code,
        s.sic_description,
        s.ticker                                as matched_ticker
    from filings f
    inner join details d
        on f.accession_no = d.accession_no
    left join sectors s
        on f.cik = s.cik
)

select * from enriched
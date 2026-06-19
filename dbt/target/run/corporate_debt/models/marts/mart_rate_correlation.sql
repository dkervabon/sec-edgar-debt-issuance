
  
    

    create or replace table `sec-edgar-debt`.`marts`.`mart_rate_correlation`
      
    
    

    
    OPTIONS()
    as (
      with issuance_by_quarter as (
    select
        issuance_quarter,
        gics_sector,
        instrument_type,
        count(*)                                                              as deal_count,
        countif(parse_success)                                                as parsed_deal_count,
        sum(case when parse_success then principal_amount_usd end)            as total_principal_usd,
        avg(case when parse_success then principal_amount_usd end)            as avg_principal_usd,
        countif(interest_rate_type = 'fixed')                                 as fixed_rate_deals,
        countif(interest_rate_type = 'floating')                              as floating_rate_deals,
        safe_divide(
            countif(interest_rate_type = 'floating'),
            nullif(countif(interest_rate_type is not null), 0)
        )                                                                      as pct_floating
    from `sec-edgar-debt`.`marts`.`mart_debt_issuance`
    group by 1, 2, 3
),

rates_quarterly as (
    select
        date_trunc(observation_date, quarter)                                  as rate_quarter,
        avg(case when series_id = 'DFF'        then rate_value end)            as avg_fed_funds_rate,
        avg(case when series_id = 'DGS2'       then rate_value end)            as avg_2yr_treasury,
        avg(case when series_id = 'DGS5'       then rate_value end)            as avg_5yr_treasury,
        avg(case when series_id = 'DGS10'      then rate_value end)            as avg_10yr_treasury,
        avg(case when series_id = 'BAMLC0A0CM' then rate_value end)            as avg_corp_oas_bps
    from `sec-edgar-debt`.`staging`.`stg_fred_rates`
    group by 1
),

final as (
    select
        i.issuance_quarter,
        i.gics_sector,
        i.instrument_type,
        i.deal_count,
        i.parsed_deal_count,
        i.total_principal_usd,
        i.avg_principal_usd,
        i.fixed_rate_deals,
        i.floating_rate_deals,
        i.pct_floating,
        r.avg_fed_funds_rate,
        r.avg_2yr_treasury,
        r.avg_5yr_treasury,
        r.avg_10yr_treasury,
        r.avg_corp_oas_bps
    from issuance_by_quarter i
    left join rates_quarterly r
        on i.issuance_quarter = r.rate_quarter
)

select * from final
    );
  
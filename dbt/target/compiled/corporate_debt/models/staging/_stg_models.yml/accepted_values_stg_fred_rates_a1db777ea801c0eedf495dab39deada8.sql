
    
    

with all_values as (

    select
        series_id as value_field,
        count(*) as n_records

    from `sec-edgar-debt`.`staging`.`stg_fred_rates`
    group by series_id

)

select *
from all_values
where value_field not in (
    'DFF','DGS2','DGS5','DGS10','BAMLC0A0CM'
)



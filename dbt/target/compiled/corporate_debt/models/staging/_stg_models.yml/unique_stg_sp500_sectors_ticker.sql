
    
    

with dbt_test__target as (

  select ticker as unique_field
  from `sec-edgar-debt`.`staging`.`stg_sp500_sectors`
  where ticker is not null

)

select
    unique_field,
    count(*) as n_records

from dbt_test__target
group by unique_field
having count(*) > 1



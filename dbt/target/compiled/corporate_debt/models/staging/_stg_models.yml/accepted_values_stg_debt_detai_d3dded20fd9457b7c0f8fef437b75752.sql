
    
    

with all_values as (

    select
        interest_rate_type as value_field,
        count(*) as n_records

    from (select * from `sec-edgar-debt`.`staging`.`stg_debt_details` where interest_rate_type is not null) dbt_subquery
    group by interest_rate_type

)

select *
from all_values
where value_field not in (
    'fixed','floating'
)



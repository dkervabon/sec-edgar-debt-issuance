
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select rate_value
from `sec-edgar-debt`.`staging`.`stg_fred_rates`
where rate_value is null



  
  
      
    ) dbt_internal_test
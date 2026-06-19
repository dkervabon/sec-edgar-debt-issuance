
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select series_id
from `sec-edgar-debt`.`staging`.`stg_fred_rates`
where series_id is null



  
  
      
    ) dbt_internal_test
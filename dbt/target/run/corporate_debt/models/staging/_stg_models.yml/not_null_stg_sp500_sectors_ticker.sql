
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select ticker
from `sec-edgar-debt`.`staging`.`stg_sp500_sectors`
where ticker is null



  
  
      
    ) dbt_internal_test

    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select gics_sector
from `sec-edgar-debt`.`staging`.`stg_sp500_sectors`
where gics_sector is null



  
  
      
    ) dbt_internal_test
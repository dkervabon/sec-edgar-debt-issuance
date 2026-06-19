
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select parse_success
from `sec-edgar-debt`.`staging`.`stg_debt_details`
where parse_success is null



  
  
      
    ) dbt_internal_test
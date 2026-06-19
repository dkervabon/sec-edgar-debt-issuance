
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select issuance_quarter
from `sec-edgar-debt`.`marts`.`mart_rate_correlation`
where issuance_quarter is null



  
  
      
    ) dbt_internal_test
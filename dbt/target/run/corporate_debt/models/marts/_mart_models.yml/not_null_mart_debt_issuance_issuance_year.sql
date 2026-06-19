
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select issuance_year
from `sec-edgar-debt`.`marts`.`mart_debt_issuance`
where issuance_year is null



  
  
      
    ) dbt_internal_test

    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select cik
from `sec-edgar-debt`.`staging`.`stg_edgar_filings`
where cik is null



  
  
      
    ) dbt_internal_test
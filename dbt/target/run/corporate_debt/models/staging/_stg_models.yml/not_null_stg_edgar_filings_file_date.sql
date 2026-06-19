
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select file_date
from `sec-edgar-debt`.`staging`.`stg_edgar_filings`
where file_date is null



  
  
      
    ) dbt_internal_test
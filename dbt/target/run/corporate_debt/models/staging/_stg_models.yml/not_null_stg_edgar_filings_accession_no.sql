
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select accession_no
from `sec-edgar-debt`.`staging`.`stg_edgar_filings`
where accession_no is null



  
  
      
    ) dbt_internal_test
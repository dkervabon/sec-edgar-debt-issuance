
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select accession_no
from `sec-edgar-debt`.`marts`.`mart_debt_issuance`
where accession_no is null



  
  
      
    ) dbt_internal_test

    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select deal_count
from `sec-edgar-debt`.`marts`.`mart_rate_correlation`
where deal_count is null



  
  
      
    ) dbt_internal_test
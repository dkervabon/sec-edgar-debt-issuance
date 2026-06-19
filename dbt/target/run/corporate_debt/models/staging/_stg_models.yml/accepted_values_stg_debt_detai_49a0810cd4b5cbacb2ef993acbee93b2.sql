
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    

with all_values as (

    select
        instrument_type as value_field,
        count(*) as n_records

    from (select * from `sec-edgar-debt`.`staging`.`stg_debt_details` where instrument_type is not null) dbt_subquery
    group by instrument_type

)

select *
from all_values
where value_field not in (
    'term_loan','revolving_credit_facility','senior_secured_notes','senior_unsecured_notes','senior_notes','convertible_notes','subordinated_notes','secured_promissory_note','promissory_note','commercial_paper','mortgage','receivables_facility','securitization_facility','financing_agreement','credit_agreement','credit_facility','bridge_facility','debentures','senior_debentures','junior_subordinated','guaranteed_notes','other'
)



  
  
      
    ) dbt_internal_test
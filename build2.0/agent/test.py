from pyathena import connect 
import pandas as pd 


conn= connect(
    s3_staging_dir='s3://ml.dev/athena_query_op/',
    region_name='us-east-1'
)


query ="""
 select segment, base_category, base_subcategory , base_sub_subcategory , base_brand ,base_sku, comp_sku, comp_source_store ,  base_title, comp_title
 
 from (
select segment, base_category, base_subcategory , base_sub_subcategory , base_brand ,base_sku, comp_sku, comp_source_store ,  base_title, comp_title, 
row_number() over (partition by  segment, base_category, base_subcategory , base_sub_subcategory , base_brand,comp_source_store  order by length(base_title) desc ) rn 

-- select count(distinct lower(base_brand ) )
from match_library.match_library_snapshot 
where load_date ='2025-05-14'
and base_source_store like  '%bjs'
and active = true 
and deleted_Date is null 
and coalesce(trim(lower(base_brand)),'x')  in 
('berkley jensen', 'bjs', 'wellsley farms', 'wf', 'w f', 'w farms', 'bj', 
            'wfarms', 'wellsley farms', 'berkley  jensen')

)
where rn <=2
order by 1,2,3,4,5"""
 

pd.read_sql(query, conn).to_csv('s3://ml-seam/sample_bjs_nb_ob/ob_brands.csv', index=False)

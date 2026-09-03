select *
from {{ ref('fct_purchases') }}
where order_date < '2023-01-01'
   or order_date >= '2024-01-01'
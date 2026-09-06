select
    log_item_id,
    item_key,
    product_base_price
from {{ ref('stg_item_logs') }}
where product_base_price is null
   or product_base_price <= 0

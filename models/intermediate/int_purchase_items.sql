with purchases as (

    select *
    from {{ ref('stg_purchase_logs') }}

),

flattened as (

    select
        purchases.purchase_key,
        purchases.customer_key,
        purchases.time_order_received_utc,
        basket.index::number(10, 0) as basket_position,
        basket.value:item_key::varchar as item_key,
        basket.value:item_count::number(10, 0) as item_count
    from purchases,
        lateral flatten(
            input => purchases.item_basket_json
        ) as basket

),

aggregated as (

    select
        purchase_key,
        customer_key,
        time_order_received_utc,
        item_key,
        min(basket_position) as basket_position,
        sum(item_count) as item_count
    from flattened
    group by
        purchase_key,
        customer_key,
        time_order_received_utc,
        item_key

)

select
    md5(purchase_key || '|' || item_key) as purchase_item_key,
    purchase_key,
    customer_key,
    time_order_received_utc,
    basket_position,
    item_key,
    item_count
from aggregated
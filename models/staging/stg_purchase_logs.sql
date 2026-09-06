with source as (

    select
        time_order_received_utc,
        purchase_key,
        customer_key,
        delivery_distance_line_meters,
        wolt_service_fee,
        courier_base_fee,
        total_basket_value,
        item_basket_description,
        try_parse_json(item_basket_description) as item_basket_json
    from {{ source('wolt_raw', 'purchase_logs') }}

),

deduplicated as (

    select *
    from source
    qualify row_number() over (
        partition by purchase_key
        order by
            time_order_received_utc desc,
            item_basket_description desc
    ) = 1

)

select
    purchase_key::varchar as purchase_key,
    customer_key::varchar as customer_key,
    time_order_received_utc::timestamp_ntz
        as time_order_received_utc,
    delivery_distance_line_meters::number(12, 2)
        as delivery_distance_line_meters,
    wolt_service_fee::number(12, 2)
        as wolt_service_fee,
    courier_base_fee::number(12, 2)
        as courier_base_fee,
    total_basket_value::number(12, 4)
        as total_basket_value,
    item_basket_description::varchar
        as item_basket_description_raw,
    item_basket_json
from deduplicated

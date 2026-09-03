with purchases as (

    select
        *,
        md5(to_json(item_basket_json)) as basket_signature_key

    from {{ ref('stg_purchase_logs') }}

),

ordered_purchases as (

    select
        *,

        lag(purchase_key) over (
            partition by
                customer_key,
                total_basket_value,
                wolt_service_fee,
                courier_base_fee,
                delivery_distance_line_meters,
                basket_signature_key
            order by
                time_order_received_utc,
                purchase_key
        ) as previous_matching_purchase_key,

        lag(time_order_received_utc) over (
            partition by
                customer_key,
                total_basket_value,
                wolt_service_fee,
                courier_base_fee,
                delivery_distance_line_meters,
                basket_signature_key
            order by
                time_order_received_utc,
                purchase_key
        ) as previous_matching_purchase_time_utc

    from purchases

),

with_gaps as (

    select
        *,

        datediff(
            'second',
            previous_matching_purchase_time_utc,
            time_order_received_utc
        ) as seconds_since_matching_purchase

    from ordered_purchases

),

with_groups as (

    select
        *,

        sum(
            case
                when previous_matching_purchase_time_utc is null
                    or seconds_since_matching_purchase > 300
                    then 1
                else 0
            end
        ) over (
            partition by
                customer_key,
                total_basket_value,
                wolt_service_fee,
                courier_base_fee,
                delivery_distance_line_meters,
                basket_signature_key
            order by
                time_order_received_utc,
                purchase_key
            rows between unbounded preceding and current row
        ) as rapid_repeat_group_number

    from with_gaps

),

sequenced as (

    select
        *,

        row_number() over (
            partition by
                customer_key,
                total_basket_value,
                wolt_service_fee,
                courier_base_fee,
                delivery_distance_line_meters,
                basket_signature_key,
                rapid_repeat_group_number
            order by
                time_order_received_utc,
                purchase_key
        ) as rapid_repeat_sequence_number,

        count(*) over (
            partition by
                customer_key,
                total_basket_value,
                wolt_service_fee,
                courier_base_fee,
                delivery_distance_line_meters,
                basket_signature_key,
                rapid_repeat_group_number
        ) as rapid_repeat_group_size

    from with_groups

)

select
    purchase_key,
    customer_key,
    time_order_received_utc,
    delivery_distance_line_meters,
    wolt_service_fee,
    courier_base_fee,
    total_basket_value,
    item_basket_description_raw,
    item_basket_json,

    previous_matching_purchase_key,
    previous_matching_purchase_time_utc,
    seconds_since_matching_purchase,

    rapid_repeat_sequence_number,
    rapid_repeat_group_size,

    rapid_repeat_group_size > 1
        as is_in_rapid_repeat_group,

    rapid_repeat_sequence_number > 1
        and seconds_since_matching_purchase <= 300
        as is_rapid_repeat_candidate

from sequenced
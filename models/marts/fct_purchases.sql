with purchases as (

    select *
    from {{ ref('int_purchases_classified') }}

),

final as (

    select
        purchase_key,
        customer_key,

        time_order_received_utc,
        cast(time_order_received_utc as date) as order_date,
        date_trunc('month', time_order_received_utc)::date as order_month,

        customer_purchase_number_in_period,
        previous_customer_purchase_time_utc,
        is_first_observed_purchase_in_period,
        is_repeat_purchase_in_period,
        days_since_previous_purchase,

        delivery_distance_line_meters,
        delivery_distance_line_meters / 1000.0
            as delivery_distance_line_km,

        total_basket_value
            as merchandise_revenue,

        wolt_service_fee
            as service_fee_revenue,

        total_basket_value + wolt_service_fee
            as gross_order_revenue,

        courier_base_fee
            as courier_cost,

        total_basket_value
            + wolt_service_fee
            - courier_base_fee
            as revenue_less_courier_cost,

        round(
            wolt_service_fee
            / nullif(total_basket_value, 0),
            4
        ) as service_fee_to_basket_ratio,

        round(
            courier_base_fee
            / nullif(total_basket_value, 0),
            4
        ) as courier_cost_to_basket_ratio,

        -- Rapid-repeat diagnostics.
        -- These fields flag suspicious patterns but do not remove purchases.
        is_in_rapid_repeat_group,
        is_rapid_repeat_candidate,
        seconds_since_matching_purchase,
        rapid_repeat_sequence_number,
        rapid_repeat_group_size

    from purchases

)

select *
from final
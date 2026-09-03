with purchase_items as (

    select *
    from {{ ref('int_purchase_items_enriched') }}

),

purchase_classification as (

    select
        purchase_key,

        customer_purchase_number_in_period,
        previous_customer_purchase_time_utc,
        is_first_observed_purchase_in_period,
        is_repeat_purchase_in_period,
        days_since_previous_purchase,

        is_in_rapid_repeat_group,
        is_rapid_repeat_candidate,
        seconds_since_matching_purchase,
        rapid_repeat_sequence_number,
        rapid_repeat_group_size

    from {{ ref('int_purchases_classified') }}

),

final as (

    select
        pi.purchase_item_key,
        pi.purchase_key,
        pi.customer_key,

        pi.time_order_received_utc,
        cast(pi.time_order_received_utc as date) as order_date,
        date_trunc('month', pi.time_order_received_utc)::date as order_month,

        pc.customer_purchase_number_in_period,
        pc.previous_customer_purchase_time_utc,
        pc.is_first_observed_purchase_in_period,
        pc.is_repeat_purchase_in_period,
        pc.days_since_previous_purchase,

        pi.basket_position,

        pi.item_key,
        pi.item_version_key,
        pi.item_name,
        pi.brand_name,
        pi.item_category,

        pi.item_count,
        pi.number_of_units,
        pi.weight_in_grams,

        pi.unit_base_price,
        pi.currency,
        pi.vat_rate_percentage,

        pi.is_on_promotion,
        pi.promo_type,
        pi.discount_percentage,

        pi.line_value_before_discount,
        pi.calculated_line_value_after_discount,

        pi.unit_base_price is not null as has_price,

        -- Purchase-level rapid-repeat diagnostics.
        pc.is_in_rapid_repeat_group,
        pc.is_rapid_repeat_candidate,
        pc.seconds_since_matching_purchase,
        pc.rapid_repeat_sequence_number,
        pc.rapid_repeat_group_size

    from purchase_items pi

    inner join purchase_classification pc
    on pi.purchase_key = pc.purchase_key

)

select *
from final
with purchase_items as (

    select *
    from {{ ref('int_purchase_items') }}

),

item_versions as (

    select *
    from {{ ref('int_item_versions') }}

),

promos as (

    select *
    from {{ ref('stg_promos') }}

)

select
    purchase_items.purchase_item_key,
    purchase_items.purchase_key,
    purchase_items.customer_key,
    purchase_items.time_order_received_utc,
    purchase_items.basket_position,
    purchase_items.item_key,
    purchase_items.item_count,

    item_versions.item_version_key,
    item_versions.item_name,
    item_versions.brand_name,
    item_versions.item_category,
    item_versions.number_of_units,
    item_versions.weight_in_grams,
    item_versions.product_base_price as unit_base_price,
    item_versions.currency,
    item_versions.vat_rate_percentage,

    promos.item_key is not null as is_on_promotion,
    promos.promo_type,
    promos.discount_percentage,

    round(
        item_versions.product_base_price
        * purchase_items.item_count,
        2
    ) as line_value_before_discount,

    round(
        item_versions.product_base_price
        * purchase_items.item_count
        * (
            1
            - coalesce(promos.discount_percentage, 0) / 100
        ),
        2
    ) as calculated_line_value_after_discount

from purchase_items

left join item_versions
    on purchase_items.item_key = item_versions.item_key
    and purchase_items.time_order_received_utc
        >= item_versions.valid_from_utc
    and (
        purchase_items.time_order_received_utc
            < item_versions.valid_to_utc
        or item_versions.valid_to_utc is null
    )

left join promos
    on purchase_items.item_key = promos.item_key
    and purchase_items.time_order_received_utc::date
        >= promos.promo_start_date
    and purchase_items.time_order_received_utc::date
        < promos.promo_end_date
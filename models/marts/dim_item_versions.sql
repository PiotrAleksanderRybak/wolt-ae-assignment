with item_versions as (

    select *
    from {{ ref('int_item_versions') }}

),

final as (

    select
        item_version_key,
        item_key,
        item_version_number,

        valid_from_utc,
        valid_to_utc,
        is_current,

        item_name,
        brand_name,
        item_category,

        number_of_units,
        weight_in_grams,

        product_base_price,
        currency,
        vat_rate_percentage

    from item_versions

)

select *
from final
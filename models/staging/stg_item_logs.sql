with source as (

    select
        log_item_id,
        item_key,
        time_log_created_utc,
        payload,
        try_parse_json(payload) as payload_json
    from {{ source('wolt_raw', 'item_logs') }}

),

deduplicated as (

    select *
    from source
    qualify row_number() over (
        partition by log_item_id
        order by time_log_created_utc desc, payload desc
    ) = 1

),

item_names as (

    select
        items.log_item_id,
        max(
            case
                when names.value:lang::varchar = 'en'
                    then names.value:value::varchar
            end
        ) as item_name_en,
        max(
            case
                when names.value:lang::varchar = 'de'
                    then names.value:value::varchar
            end
        ) as item_name_de
    from deduplicated as items,
        lateral flatten(
            input => items.payload_json:name,
            outer => true
        ) as names
    group by items.log_item_id

),

price_attributes as (

    select
        items.log_item_id,
        trim(max(prices.value:currency::varchar)) as currency,
        max(
            prices.value:product_base_price::number(10, 2)
        ) as product_base_price,
        max(
            prices.value:vat_rate_in_percent::number(5, 2)
        ) as vat_rate_percentage
    from deduplicated as items,
        lateral flatten(
            input => items.payload_json:price_attributes,
            outer => true
        ) as prices
    group by items.log_item_id

)

select
    items.log_item_id::varchar as log_item_id,
    coalesce(
        items.payload_json:item_key::varchar,
        items.item_key::varchar
    ) as item_key,
    items.time_log_created_utc::timestamp_ntz
        as time_log_created_utc,
    items.payload_json:time_item_created_in_source_utc::timestamp_ntz
        as time_item_created_in_source_utc,
    coalesce(
        item_names.item_name_en,
        item_names.item_name_de
    ) as item_name,
    item_names.item_name_en,
    item_names.item_name_de,
    items.payload_json:brand_name::varchar as brand_name,
    items.payload_json:item_category::varchar as item_category,
    items.payload_json:number_of_units::number(10, 0)
        as number_of_units,
    items.payload_json:weight_in_grams::number(10, 2)
        as weight_in_grams,
    price_attributes.product_base_price,
    price_attributes.currency,
    price_attributes.vat_rate_percentage,
    items.payload::varchar as payload_raw,
    items.payload_json
from deduplicated as items
left join item_names
    on items.log_item_id = item_names.log_item_id
left join price_attributes
    on items.log_item_id = price_attributes.log_item_id
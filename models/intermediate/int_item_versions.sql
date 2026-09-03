with item_logs as (

    select *
    from {{ ref('stg_item_logs') }}

),

sequenced as (

    select
        *,
        row_number() over (
            partition by item_key
            order by time_log_created_utc, log_item_id
        ) as item_version_number,
        lead(time_log_created_utc) over (
            partition by item_key
            order by time_log_created_utc, log_item_id
        ) as valid_to_utc
    from item_logs

)

select
    md5(
        item_key || '|' ||
        time_log_created_utc::varchar || '|' ||
        log_item_id
    ) as item_version_key,
    log_item_id,
    item_key,
    item_version_number,

case
    when item_version_number = 1
        then '1900-01-01 00:00:00'::timestamp_ntz
    else time_log_created_utc
end as valid_from_utc,

    valid_to_utc,
    valid_to_utc is null as is_current,

    item_name,
    item_name_en,
    item_name_de,
    brand_name,
    item_category,
    number_of_units,
    weight_in_grams,
    product_base_price,
    currency,
    vat_rate_percentage
from sequenced
with source as (

    select *
    from {{ source('wolt_raw', 'promos') }}

),

renamed as (

    select
        item_key::varchar as item_key,
        promo_start_date::date as promo_start_date,
        promo_end_date::date as promo_end_date,
        trim(promo_type)::varchar as promo_type,
        discount_in_percentage::number(5, 2) as discount_percentage
    from source

)

select *
from renamed
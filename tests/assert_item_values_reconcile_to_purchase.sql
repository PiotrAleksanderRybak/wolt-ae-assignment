with item_totals as (

    select
        purchase_key,
        sum(calculated_line_value_after_discount) as calculated_basket_value
    from {{ ref('fct_purchase_items') }}
    group by purchase_key

)

select
    p.purchase_key,
    p.merchandise_revenue,
    i.calculated_basket_value,
    p.merchandise_revenue - i.calculated_basket_value as difference
from {{ ref('fct_purchases') }} as p
inner join item_totals as i
    on p.purchase_key = i.purchase_key
where abs(
    p.merchandise_revenue - i.calculated_basket_value
) > 0.0001

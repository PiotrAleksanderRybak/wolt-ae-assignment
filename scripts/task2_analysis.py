import json
import os
from pathlib import Path

import pandas as pd
import snowflake.connector


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

OUTPUT_DIR = Path("analysis_outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

JSON_OUTPUT = OUTPUT_DIR / "task2_analysis_results.json"
MANIFEST_OUTPUT = OUTPUT_DIR / "task2_analysis_manifest.txt"

DATABASE = "WOLT_TASK"
SCHEMA = "DBT_DEV"

PURCHASES = f"{DATABASE}.{SCHEMA}.FCT_PURCHASES"
PURCHASE_ITEMS = f"{DATABASE}.{SCHEMA}.FCT_PURCHASE_ITEMS"
ITEM_DIM = f"{DATABASE}.{SCHEMA}.DIM_ITEM_VERSIONS"


# ---------------------------------------------------------------------
# Queries
#
# Structure intentionally follows the Wolt Task 2 questions:
#
# 00 = overall context
# 10 = categories / star products / growth
# 20 = products bought together
# 30 = consumption by period
# 40 = first observed customers and promotions
# 50 = rapid-repeat sensitivity
# 60 = data-quality / price coverage
# ---------------------------------------------------------------------

QUERIES = {

    # =================================================================
    # 00. BUSINESS CONTEXT
    # =================================================================

    "00_purchase_overview": f"""
        select
            count(*) as purchases,
            count(distinct customer_key) as customers,
            round(sum(merchandise_revenue), 2) as merchandise_revenue,
            round(sum(service_fee_revenue), 2) as service_fee_revenue,
            round(sum(gross_order_revenue), 2) as gross_order_revenue,
            round(sum(courier_cost), 2) as courier_cost,
            round(avg(merchandise_revenue), 2) as avg_basket_value,
            round(avg(delivery_distance_line_km), 2) as avg_delivery_distance_km,
            count_if(is_first_observed_purchase_in_period) as first_observed_purchases,
            count_if(is_repeat_purchase_in_period) as repeat_purchases,
            count_if(is_rapid_repeat_candidate) as rapid_repeat_candidates,
            round(
                100.0 * count_if(is_rapid_repeat_candidate)
                / nullif(count(*), 0),
                2
            ) as rapid_repeat_candidate_share_pct
        from {PURCHASES}
    """,

    "01_item_overview": f"""
        select
            count(*) as purchase_item_rows,
            sum(item_count) as units,
            count(distinct item_key) as distinct_items,
            count(distinct item_category) as distinct_categories,
            count(distinct purchase_key) as purchases,
            sum(iff(is_on_promotion, item_count, 0)) as promo_units,
            round(
                100.0 * sum(iff(is_on_promotion, item_count, 0))
                / nullif(sum(item_count), 0),
                2
            ) as promo_unit_share_pct,
            count_if(has_price) as rows_with_price,
            round(
                100.0 * count_if(has_price)
                / nullif(count(*), 0),
                2
            ) as price_row_coverage_pct
        from {PURCHASE_ITEMS}
    """,

    "02_monthly_business_overview": f"""
        select
            order_month,
            count(*) as purchases,
            count(distinct customer_key) as active_customers,
            count_if(is_first_observed_purchase_in_period)
                as first_observed_purchases,
            round(sum(merchandise_revenue), 2)
                as merchandise_revenue,
            round(sum(service_fee_revenue), 2)
                as service_fee_revenue,
            round(sum(courier_cost), 2)
                as courier_cost,
            round(avg(merchandise_revenue), 2)
                as avg_basket_value,
            round(avg(delivery_distance_line_km), 2)
                as avg_delivery_distance_km,
            count_if(is_rapid_repeat_candidate)
                as rapid_repeat_candidates,
            round(
                100.0 * count_if(is_rapid_repeat_candidate)
                / nullif(count(*), 0),
                2
            ) as rapid_repeat_candidate_share_pct
        from {PURCHASES}
        group by order_month
        order by order_month
    """,


    # =================================================================
    # Q1 + Q2
    # Which categories perform better?
    # Star products?
    # Which categories are not improving and why?
    # =================================================================

    "10_category_annual_summary": f"""
        select
            coalesce(item_category, 'Unknown') as item_category,

            sum(item_count) as units,

            count(distinct purchase_key) as purchases,

            count(distinct customer_key) as customers,

            round(
                sum(item_count)
                / nullif(count(distinct purchase_key), 0),
                2
            ) as units_per_purchase,

            sum(
                iff(is_on_promotion, item_count, 0)
            ) as promo_units,

            round(
                100.0
                * sum(iff(is_on_promotion, item_count, 0))
                / nullif(sum(item_count), 0),
                2
            ) as promo_unit_share_pct,

            round(
                100.0 * count_if(has_price)
                / nullif(count(*), 0),
                2
            ) as price_row_coverage_pct

        from {PURCHASE_ITEMS}

        group by 1

        order by units desc
    """,

    "11_category_q1_vs_q4": f"""
        with category_quarters as (

            select
                coalesce(item_category, 'Unknown') as item_category,
                quarter(order_date) as quarter_number,

                sum(item_count) as units,
                count(distinct purchase_key) as purchases,
                count(distinct customer_key) as customers,

                sum(
                    iff(is_on_promotion, item_count, 0)
                ) as promo_units

            from {PURCHASE_ITEMS}

            where quarter(order_date) in (1, 4)

            group by 1, 2
        ),

        pivoted as (

            select
                item_category,

                max(
                    iff(quarter_number = 1, units, null)
                ) as q1_units,

                max(
                    iff(quarter_number = 4, units, null)
                ) as q4_units,

                max(
                    iff(quarter_number = 1, purchases, null)
                ) as q1_purchases,

                max(
                    iff(quarter_number = 4, purchases, null)
                ) as q4_purchases,

                max(
                    iff(quarter_number = 1, customers, null)
                ) as q1_customers,

                max(
                    iff(quarter_number = 4, customers, null)
                ) as q4_customers,

                max(
                    iff(quarter_number = 1, promo_units, null)
                ) as q1_promo_units,

                max(
                    iff(quarter_number = 4, promo_units, null)
                ) as q4_promo_units

            from category_quarters

            group by item_category
        )

        select
            *,

            q4_units - q1_units
                as units_absolute_change,

            round(
                100.0 * (q4_units - q1_units)
                / nullif(q1_units, 0),
                2
            ) as units_change_pct,

            q4_purchases - q1_purchases
                as purchases_absolute_change,

            round(
                100.0 * (q4_purchases - q1_purchases)
                / nullif(q1_purchases, 0),
                2
            ) as purchases_change_pct,

            q4_customers - q1_customers
                as customers_absolute_change,

            round(
                100.0 * (q4_customers - q1_customers)
                / nullif(q1_customers, 0),
                2
            ) as customers_change_pct,

            round(
                1.0 * q1_units
                / nullif(q1_purchases, 0),
                2
            ) as q1_units_per_purchase,

            round(
                1.0 * q4_units
                / nullif(q4_purchases, 0),
                2
            ) as q4_units_per_purchase,

            round(
                100.0 * q1_promo_units
                / nullif(q1_units, 0),
                2
            ) as q1_promo_unit_share_pct,

            round(
                100.0 * q4_promo_units
                / nullif(q4_units, 0),
                2
            ) as q4_promo_unit_share_pct

        from pivoted

        order by units_change_pct desc nulls last
    """,

    "12_star_products": f"""
        with current_items as (

            select
                item_key,
                item_name,
                item_category
            from {ITEM_DIM}
            where is_current

        )

        select
            i.item_key,

            max(d.item_name) as current_item_name,
            max(d.item_category) as current_item_category,

            sum(i.item_count) as units,
            count(distinct i.purchase_key) as purchases,
            count(distinct i.customer_key) as customers,

            round(
                sum(i.item_count)
                / nullif(count(distinct i.purchase_key), 0),
                2
            ) as units_per_purchase,

            sum(
                iff(i.is_on_promotion, i.item_count, 0)
            ) as promo_units,

            round(
                100.0
                * sum(iff(i.is_on_promotion, i.item_count, 0))
                / nullif(sum(i.item_count), 0),
                2
            ) as promo_unit_share_pct,

            round(
                100.0 * count_if(i.has_price)
                / nullif(count(*), 0),
                2
            ) as price_row_coverage_pct

        from {PURCHASE_ITEMS} i

        left join current_items d
            on i.item_key = d.item_key

        group by i.item_key

        order by units desc
    """,

    "13_product_q1_vs_q4_drivers": f"""
        with product_quarters as (

            select
                coalesce(item_category, 'Unknown')
                    as historical_item_category,

                item_key,

                max(item_name) as item_name,

                quarter(order_date) as quarter_number,

                sum(item_count) as units,

                count(distinct purchase_key) as purchases,

                count(distinct customer_key) as customers

            from {PURCHASE_ITEMS}

            where quarter(order_date) in (1, 4)

            group by 1, 2, 4
        ),

        pivoted as (

            select
                historical_item_category,
                item_key,
                max(item_name) as item_name,

                max(
                    iff(quarter_number = 1, units, null)
                ) as q1_units,

                max(
                    iff(quarter_number = 4, units, null)
                ) as q4_units,

                max(
                    iff(quarter_number = 1, purchases, null)
                ) as q1_purchases,

                max(
                    iff(quarter_number = 4, purchases, null)
                ) as q4_purchases,

                max(
                    iff(quarter_number = 1, customers, null)
                ) as q1_customers,

                max(
                    iff(quarter_number = 4, customers, null)
                ) as q4_customers

            from product_quarters

            group by 1, 2
        )

        select
            *,

            coalesce(q4_units, 0)
                - coalesce(q1_units, 0)
                as units_absolute_change,

            round(
                100.0
                * (
                    coalesce(q4_units, 0)
                    - coalesce(q1_units, 0)
                )
                / nullif(q1_units, 0),
                2
            ) as units_change_pct

        from pivoted

        order by abs(units_absolute_change) desc

        limit 200
    """,


    # =================================================================
    # Q3
    # Which products are bought together?
    # =================================================================

    "20_product_pairs": f"""
        with basket_items as (

            select distinct
                purchase_key,
                item_key

            from {PURCHASE_ITEMS}
        ),

        item_orders as (

            select
                item_key,
                count(*) as item_purchases

            from basket_items

            group by item_key
        ),

        pairs as (

            select
                a.item_key as item_a_key,
                b.item_key as item_b_key,
                count(*) as pair_purchases

            from basket_items a

            join basket_items b
                on a.purchase_key = b.purchase_key
               and a.item_key < b.item_key

            group by 1, 2
        ),

        total as (

            select count(*) as total_purchases
            from {PURCHASES}
        ),

        current_items as (

            select
                item_key,
                item_name,
                item_category

            from {ITEM_DIM}

            where is_current
        )

        select
            p.item_a_key,
            a.item_name as item_a_name,
            a.item_category as item_a_category,

            p.item_b_key,
            b.item_name as item_b_name,
            b.item_category as item_b_category,

            p.pair_purchases,

            ia.item_purchases as item_a_purchases,
            ib.item_purchases as item_b_purchases,

            round(
                100.0 * p.pair_purchases
                / nullif(t.total_purchases, 0),
                3
            ) as support_pct,

            round(
                100.0 * p.pair_purchases
                / nullif(ia.item_purchases, 0),
                2
            ) as confidence_a_to_b_pct,

            round(
                100.0 * p.pair_purchases
                / nullif(ib.item_purchases, 0),
                2
            ) as confidence_b_to_a_pct,

            round(
                1.0 * p.pair_purchases * t.total_purchases
                / nullif(
                    ia.item_purchases * ib.item_purchases,
                    0
                ),
                3
            ) as lift

        from pairs p

        join item_orders ia
            on p.item_a_key = ia.item_key

        join item_orders ib
            on p.item_b_key = ib.item_key

        cross join total t

        left join current_items a
            on p.item_a_key = a.item_key

        left join current_items b
            on p.item_b_key = b.item_key

        where p.pair_purchases >= 20

        order by p.pair_purchases desc, lift desc

        limit 100
    """,

    "21_product_pairs_without_rapid_repeats": f"""
        with basket_items as (

            select distinct
                purchase_key,
                item_key

            from {PURCHASE_ITEMS}

            where not is_rapid_repeat_candidate
        ),

        item_orders as (

            select
                item_key,
                count(*) as item_purchases

            from basket_items

            group by item_key
        ),

        pairs as (

            select
                a.item_key as item_a_key,
                b.item_key as item_b_key,
                count(*) as pair_purchases

            from basket_items a

            join basket_items b
                on a.purchase_key = b.purchase_key
               and a.item_key < b.item_key

            group by 1, 2
        ),

        total as (

            select count(*) as total_purchases

            from {PURCHASES}

            where not is_rapid_repeat_candidate
        ),

        current_items as (

            select
                item_key,
                item_name,
                item_category

            from {ITEM_DIM}

            where is_current
        )

        select
            p.item_a_key,
            a.item_name as item_a_name,

            p.item_b_key,
            b.item_name as item_b_name,

            p.pair_purchases,

            round(
                100.0 * p.pair_purchases
                / nullif(t.total_purchases, 0),
                3
            ) as support_pct,

            round(
                1.0 * p.pair_purchases * t.total_purchases
                / nullif(
                    ia.item_purchases * ib.item_purchases,
                    0
                ),
                3
            ) as lift

        from pairs p

        join item_orders ia
            on p.item_a_key = ia.item_key

        join item_orders ib
            on p.item_b_key = ib.item_key

        cross join total t

        left join current_items a
            on p.item_a_key = a.item_key

        left join current_items b
            on p.item_b_key = b.item_key

        where p.pair_purchases >= 20

        order by p.pair_purchases desc, lift desc

        limit 100
    """,


    # =================================================================
    # Q4
    # How does category consumption behave over different periods?
    # =================================================================

    "30_category_monthly": f"""
        select
            order_month,
            coalesce(item_category, 'Unknown') as item_category,

            sum(item_count) as units,

            count(distinct purchase_key) as purchases,

            count(distinct customer_key) as customers,

            sum(
                iff(is_on_promotion, item_count, 0)
            ) as promo_units,

            round(
                100.0
                * sum(iff(is_on_promotion, item_count, 0))
                / nullif(sum(item_count), 0),
                2
            ) as promo_unit_share_pct

        from {PURCHASE_ITEMS}

        group by 1, 2

        order by 1, 3 desc
    """,

    "31_category_by_weekday": f"""
        select
            dayofweekiso(order_date) as weekday_number,
            dayname(order_date) as weekday_name,

            coalesce(item_category, 'Unknown')
                as item_category,

            sum(item_count) as units,

            count(distinct purchase_key) as purchases,

            count(distinct customer_key) as customers

        from {PURCHASE_ITEMS}

        group by 1, 2, 3

        order by 1, units desc
    """,

    "32_category_by_hour": f"""
        select
            date_part(
                'hour',
                time_order_received_utc
            ) as order_hour,

            coalesce(item_category, 'Unknown')
                as item_category,

            sum(item_count) as units,

            count(distinct purchase_key) as purchases,

            count(distinct customer_key) as customers

        from {PURCHASE_ITEMS}

        group by 1, 2

        order by 1, units desc
    """,


    # =================================================================
    # Q5
    # Are first observed customers coming through promotions?
    #
    # IMPORTANT:
    # This is deliberately called "first observed", not "new customer".
    # =================================================================

    "40_first_purchase_promo_summary": f"""
        with first_purchases as (

            select
                customer_key,
                purchase_key as first_purchase_key,
                order_date as first_purchase_date

            from {PURCHASES}

            where is_first_observed_purchase_in_period
        ),

        first_baskets as (

            select
                purchase_key,

                max(
                    iff(is_on_promotion, 1, 0)
                ) as first_purchase_has_promo,

                sum(item_count) as first_purchase_units,

                sum(
                    iff(is_on_promotion, item_count, 0)
                ) as first_purchase_promo_units

            from {PURCHASE_ITEMS}

            where is_first_observed_purchase_in_period

            group by purchase_key
        ),

        lifecycle as (

            select
                customer_key,

                max(
                    iff(
                        customer_purchase_number_in_period = 2,
                        order_date,
                        null
                    )
                ) as second_purchase_date,

                count(*) as total_purchases_in_2023

            from {PURCHASES}

            group by customer_key
        ),

        customer_level as (

            select
                f.customer_key,
                f.first_purchase_key,
                f.first_purchase_date,

                b.first_purchase_has_promo,
                b.first_purchase_units,
                b.first_purchase_promo_units,

                l.second_purchase_date,
                l.total_purchases_in_2023,

                iff(
                    f.first_purchase_date <= '2023-12-01',
                    true,
                    false
                ) as eligible_for_30d_followup,

                iff(
                    f.first_purchase_date <= '2023-12-01'
                    and l.second_purchase_date
                        <= dateadd(
                            day,
                            30,
                            f.first_purchase_date
                        ),
                    true,
                    false
                ) as returned_within_30d

            from first_purchases f

            join first_baskets b
                on f.first_purchase_key = b.purchase_key

            join lifecycle l
                on f.customer_key = l.customer_key
        )

        select
            iff(
                first_purchase_has_promo = 1,
                'promo_on_first_purchase',
                'no_promo_on_first_purchase'
            ) as first_purchase_segment,

            count(*) as customers,

            count_if(eligible_for_30d_followup)
                as eligible_30d_customers,

            count_if(
                eligible_for_30d_followup
                and returned_within_30d
            ) as returned_within_30d_customers,

            round(
                100.0
                * count_if(
                    eligible_for_30d_followup
                    and returned_within_30d
                )
                / nullif(
                    count_if(eligible_for_30d_followup),
                    0
                ),
                2
            ) as return_30d_rate_pct,

            count_if(second_purchase_date is not null)
                as returned_by_year_end_customers,

            round(
                100.0
                * count_if(second_purchase_date is not null)
                / nullif(count(*), 0),
                2
            ) as returned_by_year_end_pct,

            round(
                avg(total_purchases_in_2023),
                2
            ) as avg_total_purchases_in_2023,

            round(
                avg(
                    iff(
                        second_purchase_date is not null,
                        datediff(
                            day,
                            first_purchase_date,
                            second_purchase_date
                        ),
                        null
                    )
                ),
                2
            ) as avg_days_to_second_purchase

        from customer_level

        group by 1

        order by 1
    """,

    "41_first_purchase_promo_monthly": f"""
        with first_purchases as (

            select
                customer_key,
                purchase_key as first_purchase_key,
                order_date as first_purchase_date,
                order_month as first_purchase_month

            from {PURCHASES}

            where is_first_observed_purchase_in_period
        ),

        first_baskets as (

            select
                purchase_key,

                max(
                    iff(is_on_promotion, 1, 0)
                ) as first_purchase_has_promo

            from {PURCHASE_ITEMS}

            where is_first_observed_purchase_in_period

            group by purchase_key
        ),

        lifecycle as (

            select
                customer_key,

                max(
                    iff(
                        customer_purchase_number_in_period = 2,
                        order_date,
                        null
                    )
                ) as second_purchase_date

            from {PURCHASES}

            group by customer_key
        )

        select
            f.first_purchase_month,

            count(*) as first_observed_customers,

            count_if(
                b.first_purchase_has_promo = 1
            ) as first_observed_with_promo,

            round(
                100.0
                * count_if(
                    b.first_purchase_has_promo = 1
                )
                / nullif(count(*), 0),
                2
            ) as first_purchase_promo_share_pct,

            count_if(
                f.first_purchase_date <= '2023-12-01'
            ) as eligible_30d_customers,

            count_if(
                f.first_purchase_date <= '2023-12-01'
                and l.second_purchase_date
                    <= dateadd(
                        day,
                        30,
                        f.first_purchase_date
                    )
            ) as returned_within_30d,

            round(
                100.0
                * count_if(
                    f.first_purchase_date <= '2023-12-01'
                    and l.second_purchase_date
                        <= dateadd(
                            day,
                            30,
                            f.first_purchase_date
                        )
                )
                / nullif(
                    count_if(
                        f.first_purchase_date
                            <= '2023-12-01'
                    ),
                    0
                ),
                2
            ) as return_30d_rate_pct

        from first_purchases f

        join first_baskets b
            on f.first_purchase_key = b.purchase_key

        join lifecycle l
            on f.customer_key = l.customer_key

        group by f.first_purchase_month

        order by f.first_purchase_month
    """,

    "42_promo_products_on_first_purchase": f"""
        with lifecycle as (

            select
                customer_key,

                max(
                    iff(
                        customer_purchase_number_in_period = 2,
                        order_date,
                        null
                    )
                ) as second_purchase_date

            from {PURCHASES}

            group by customer_key
        ),

        current_items as (

            select
                item_key,
                item_name,
                item_category

            from {ITEM_DIM}

            where is_current
        )

        select
            i.item_key,
            max(d.item_name) as current_item_name,
            max(d.item_category) as current_item_category,

            count(distinct i.customer_key)
                as first_observed_customers_buying_promo_item,

            sum(i.item_count) as promo_units_on_first_purchases,

            count(
                distinct case
                    when i.order_date <= '2023-12-01'
                    then i.customer_key
                end
            ) as eligible_30d_customers,

            count(
                distinct case
                    when i.order_date <= '2023-12-01'
                     and l.second_purchase_date
                        <= dateadd(
                            day,
                            30,
                            i.order_date
                        )
                    then i.customer_key
                end
            ) as returned_within_30d_customers,

            round(
                100.0
                * count(
                    distinct case
                        when i.order_date <= '2023-12-01'
                         and l.second_purchase_date
                            <= dateadd(
                                day,
                                30,
                                i.order_date
                            )
                        then i.customer_key
                    end
                )
                / nullif(
                    count(
                        distinct case
                            when i.order_date
                                <= '2023-12-01'
                            then i.customer_key
                        end
                    ),
                    0
                ),
                2
            ) as return_30d_rate_pct

        from {PURCHASE_ITEMS} i

        join lifecycle l
            on i.customer_key = l.customer_key

        left join current_items d
            on i.item_key = d.item_key

        where i.is_first_observed_purchase_in_period
          and i.is_on_promotion

        group by i.item_key

        having count(distinct i.customer_key) >= 5

        order by first_observed_customers_buying_promo_item desc
    """,

    "43_promo_types_on_first_purchase": f"""
        with lifecycle as (

            select
                customer_key,

                max(
                    iff(
                        customer_purchase_number_in_period = 2,
                        order_date,
                        null
                    )
                ) as second_purchase_date

            from {PURCHASES}

            group by customer_key
        )

        select
            coalesce(i.promo_type, 'Unknown')
                as promo_type,

            count(distinct i.customer_key)
                as first_observed_customers,

            sum(i.item_count)
                as promo_units_on_first_purchases,

            count(
                distinct case
                    when i.order_date <= '2023-12-01'
                    then i.customer_key
                end
            ) as eligible_30d_customers,

            count(
                distinct case
                    when i.order_date <= '2023-12-01'
                     and l.second_purchase_date
                        <= dateadd(
                            day,
                            30,
                            i.order_date
                        )
                    then i.customer_key
                end
            ) as returned_within_30d_customers

        from {PURCHASE_ITEMS} i

        join lifecycle l
            on i.customer_key = l.customer_key

        where i.is_first_observed_purchase_in_period
          and i.is_on_promotion

        group by 1

        order by first_observed_customers desc
    """,


    # =================================================================
    # SENSITIVITY
    # Are conclusions robust to rapid-repeat candidates?
    # =================================================================

    "50_overall_rapid_repeat_sensitivity": f"""
        with purchase_metrics as (

            select
                'all_purchases' as scenario,

                count(*) as purchases,
                count(distinct customer_key) as customers,

                round(
                    sum(merchandise_revenue),
                    2
                ) as merchandise_revenue,

                round(
                    avg(merchandise_revenue),
                    2
                ) as avg_basket_value

            from {PURCHASES}

            union all

            select
                'exclude_rapid_repeat_candidates'
                    as scenario,

                count(*) as purchases,
                count(distinct customer_key) as customers,

                round(
                    sum(merchandise_revenue),
                    2
                ) as merchandise_revenue,

                round(
                    avg(merchandise_revenue),
                    2
                ) as avg_basket_value

            from {PURCHASES}

            where not is_rapid_repeat_candidate
        ),

        item_metrics as (

            select
                'all_purchases' as scenario,
                sum(item_count) as units

            from {PURCHASE_ITEMS}

            union all

            select
                'exclude_rapid_repeat_candidates'
                    as scenario,
                sum(item_count) as units

            from {PURCHASE_ITEMS}

            where not is_rapid_repeat_candidate
        )

        select
            p.scenario,
            p.purchases,
            p.customers,
            p.merchandise_revenue,
            p.avg_basket_value,
            i.units

        from purchase_metrics p

        join item_metrics i
            on p.scenario = i.scenario

        order by p.scenario
    """,

    "51_category_rapid_repeat_sensitivity": f"""
        with all_metrics as (

            select
                coalesce(item_category, 'Unknown')
                    as item_category,

                sum(item_count) as all_units,

                count(distinct purchase_key)
                    as all_purchases

            from {PURCHASE_ITEMS}

            group by 1
        ),

        clean_metrics as (

            select
                coalesce(item_category, 'Unknown')
                    as item_category,

                sum(item_count) as clean_units,

                count(distinct purchase_key)
                    as clean_purchases

            from {PURCHASE_ITEMS}

            where not is_rapid_repeat_candidate

            group by 1
        )

        select
            a.item_category,

            a.all_units,
            c.clean_units,

            a.all_units - c.clean_units
                as candidate_units,

            round(
                100.0
                * (a.all_units - c.clean_units)
                / nullif(a.all_units, 0),
                2
            ) as candidate_unit_share_pct,

            a.all_purchases,
            c.clean_purchases,

            a.all_purchases - c.clean_purchases
                as candidate_purchases

        from all_metrics a

        join clean_metrics c
            on a.item_category = c.item_category

        order by a.all_units desc
    """,

    "52_product_rapid_repeat_sensitivity": f"""
        with all_metrics as (

            select
                item_key,
                max(item_name) as item_name,
                sum(item_count) as all_units

            from {PURCHASE_ITEMS}

            group by item_key
        ),

        clean_metrics as (

            select
                item_key,
                sum(item_count) as clean_units

            from {PURCHASE_ITEMS}

            where not is_rapid_repeat_candidate

            group by item_key
        )

        select
            a.item_key,
            a.item_name,

            a.all_units,
            c.clean_units,

            a.all_units - c.clean_units
                as candidate_units,

            round(
                100.0
                * (a.all_units - c.clean_units)
                / nullif(a.all_units, 0),
                2
            ) as candidate_unit_share_pct

        from all_metrics a

        join clean_metrics c
            on a.item_key = c.item_key

        order by a.all_units desc

        limit 100
    """,


    # =================================================================
    # DATA QUALITY / INTERPRETATION GUARDRAILS
    # =================================================================

    "60_price_coverage_by_category": f"""
        select
            coalesce(item_category, 'Unknown')
                as item_category,

            count(*) as purchase_item_rows,

            count_if(has_price)
                as rows_with_price,

            round(
                100.0 * count_if(has_price)
                / nullif(count(*), 0),
                2
            ) as price_row_coverage_pct,

            sum(item_count) as units,

            sum(
                iff(has_price, item_count, 0)
            ) as units_with_price,

            round(
                100.0
                * sum(iff(has_price, item_count, 0))
                / nullif(sum(item_count), 0),
                2
            ) as price_unit_coverage_pct

        from {PURCHASE_ITEMS}

        group by 1

        order by units desc
    """,

    "61_price_coverage_top_products": f"""
        select
            item_key,
            max(item_name) as item_name,

            sum(item_count) as units,

            count(*) as purchase_item_rows,

            count_if(has_price)
                as rows_with_price,

            round(
                100.0 * count_if(has_price)
                / nullif(count(*), 0),
                2
            ) as price_row_coverage_pct

        from {PURCHASE_ITEMS}

        group by item_key

        order by units desc

        limit 100
    """
}


# ---------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------

def run_query(conn, name, sql):
    """Run one Snowflake query and return a pandas DataFrame."""

    print(f"\nRunning {name}...")

    cursor = conn.cursor()

    try:
        cursor.execute(sql)
        df = cursor.fetch_pandas_all()

        print(f"  -> {len(df):,} rows")

        return df

    finally:
        cursor.close()


def dataframe_to_json_records(df):
    """
    Convert DataFrame to JSON-safe records.
    Handles timestamps and numpy types.
    """

    return json.loads(
        df.to_json(
            orient="records",
            date_format="iso"
        )
    )


# ---------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------

def main():

    print("=" * 70)
    print("WOLT TASK 2 ANALYSIS")
    print("=" * 70)

    conn = snowflake.connector.connect(
        account="TTIJSKQ-HQ63691",
        user="PIOTRRYB",
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse="COMPUTE_WH",
        database=DATABASE,
        schema=SCHEMA,
        role="ACCOUNTADMIN",
    )

    combined_results = {}
    manifest_lines = []

    failed_queries = []

    try:

        for name, sql in QUERIES.items():

            try:

                df = run_query(
                    conn,
                    name,
                    sql
                )

                csv_path = (
                    OUTPUT_DIR
                    / f"{name}.csv"
                )

                df.to_csv(
                    csv_path,
                    index=False
                )

                combined_results[name] = {
                    "row_count": len(df),
                    "columns": list(df.columns),
                    "records": dataframe_to_json_records(df),
                }

                manifest_lines.append(
                    f"{name}: {len(df):,} rows"
                )

            except Exception as exc:

                print(
                    f"  !! ERROR in {name}: {exc}"
                )

                failed_queries.append(
                    {
                        "query": name,
                        "error": str(exc),
                    }
                )

                combined_results[name] = {
                    "error": str(exc)
                }

    finally:

        conn.close()

    combined_results["_metadata"] = {
        "database": DATABASE,
        "schema": SCHEMA,
        "analysis_period": "2023",
        "failed_queries": failed_queries,
        "important_interpretation_notes": [
            (
                "First observed purchase in 2023 is not necessarily "
                "the customer's first-ever Wolt purchase."
            ),
            (
                "Rapid-repeat candidates are preserved in the analytical "
                "population and evaluated through sensitivity analysis."
            ),
            (
                "Product/category performance should primarily use units, "
                "purchases and customers because product price coverage "
                "is materially incomplete."
            ),
            (
                "Promotion comparisons are observational and should not "
                "be interpreted as causal acquisition effects."
            ),
        ],
    }

    with open(
        JSON_OUTPUT,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            combined_results,
            file,
            indent=2,
            ensure_ascii=False
        )

    with open(
        MANIFEST_OUTPUT,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            "Wolt Task 2 analysis outputs\n"
        )

        file.write(
            "=" * 40 + "\n\n"
        )

        for line in manifest_lines:
            file.write(line + "\n")

        if failed_queries:

            file.write(
                "\nFAILED QUERIES\n"
            )

            file.write(
                "-" * 40 + "\n"
            )

            for failure in failed_queries:

                file.write(
                    f"{failure['query']}: "
                    f"{failure['error']}\n"
                )

    print("\n" + "=" * 70)

    print(
        f"Combined results saved to:\n"
        f"  {JSON_OUTPUT}"
    )

    print(
        f"\nManifest saved to:\n"
        f"  {MANIFEST_OUTPUT}"
    )

    print(
        f"\nIndividual CSV files saved in:\n"
        f"  {OUTPUT_DIR}"
    )

    if failed_queries:

        print(
            f"\nWARNING: "
            f"{len(failed_queries)} query/queries failed."
        )

        for failure in failed_queries:

            print(
                f"  - {failure['query']}"
            )

    else:

        print(
            "\nSUCCESS: all queries completed."
        )

    print("=" * 70)


if __name__ == "__main__":
    main()
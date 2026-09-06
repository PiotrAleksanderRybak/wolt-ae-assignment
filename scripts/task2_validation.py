import json
import os
from pathlib import Path

import pandas as pd
import snowflake.connector


OUTPUT_DIR = Path("analysis_outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "task2_validation_results.json"

DATABASE = "WOLT_TASK"
SCHEMA = "DBT_DEV"

PURCHASES = f"{DATABASE}.{SCHEMA}.FCT_PURCHASES"
PURCHASE_ITEMS = f"{DATABASE}.{SCHEMA}.FCT_PURCHASE_ITEMS"
ITEM_DIM = f"{DATABASE}.{SCHEMA}.DIM_ITEM_VERSIONS"
STG_PURCHASES = f"{DATABASE}.{SCHEMA}.STG_PURCHASE_LOGS"


QUERIES = {

    "01_stable_category_q1_vs_q4": f"""
        with current_items as (

            select
                item_key,
                item_name,
                item_category as current_item_category

            from {ITEM_DIM}

            where is_current

        ),

        category_quarters as (

            select
                coalesce(
                    d.current_item_category,
                    'Unknown'
                ) as item_category,

                quarter(i.order_date) as quarter_number,

                sum(i.item_count) as units,

                count(distinct i.purchase_key) as purchases,

                count(distinct i.customer_key) as customers,

                sum(
                    iff(
                        i.is_on_promotion,
                        i.item_count,
                        0
                    )
                ) as promo_units

            from {PURCHASE_ITEMS} i

            left join current_items d
                on i.item_key = d.item_key

            where quarter(i.order_date) in (1, 4)

            group by 1, 2
        ),

        pivoted as (

            select
                item_category,

                max(
                    iff(
                        quarter_number = 1,
                        units,
                        null
                    )
                ) as q1_units,

                max(
                    iff(
                        quarter_number = 4,
                        units,
                        null
                    )
                ) as q4_units,

                max(
                    iff(
                        quarter_number = 1,
                        purchases,
                        null
                    )
                ) as q1_purchases,

                max(
                    iff(
                        quarter_number = 4,
                        purchases,
                        null
                    )
                ) as q4_purchases,

                max(
                    iff(
                        quarter_number = 1,
                        customers,
                        null
                    )
                ) as q1_customers,

                max(
                    iff(
                        quarter_number = 4,
                        customers,
                        null
                    )
                ) as q4_customers,

                max(
                    iff(
                        quarter_number = 1,
                        promo_units,
                        null
                    )
                ) as q1_promo_units,

                max(
                    iff(
                        quarter_number = 4,
                        promo_units,
                        null
                    )
                ) as q4_promo_units

            from category_quarters

            group by item_category
        )

        select
            *,

            q4_units - q1_units
                as units_absolute_change,

            round(
                100.0
                * (q4_units - q1_units)
                / nullif(q1_units, 0),
                2
            ) as units_change_pct,

            round(
                100.0
                * q1_promo_units
                / nullif(q1_units, 0),
                2
            ) as q1_promo_unit_share_pct,

            round(
                100.0
                * q4_promo_units
                / nullif(q4_units, 0),
                2
            ) as q4_promo_unit_share_pct

        from pivoted

        order by q4_units desc
    """,

    "02_stable_product_q1_vs_q4": f"""
        with current_items as (

            select
                item_key,
                item_name,
                item_category as current_item_category

            from {ITEM_DIM}

            where is_current

        ),

        product_quarters as (

            select
                i.item_key,
                d.item_name,
                d.current_item_category,

                quarter(i.order_date)
                    as quarter_number,

                sum(i.item_count)
                    as units,

                count(distinct i.purchase_key)
                    as purchases,

                count(distinct i.customer_key)
                    as customers

            from {PURCHASE_ITEMS} i

            left join current_items d
                on i.item_key = d.item_key

            where quarter(i.order_date) in (1, 4)

            group by 1, 2, 3, 4
        )

        select
            item_key,
            item_name,
            current_item_category,

            sum(
                iff(
                    quarter_number = 1,
                    units,
                    0
                )
            ) as q1_units,

            sum(
                iff(
                    quarter_number = 4,
                    units,
                    0
                )
            ) as q4_units,

            sum(
                iff(
                    quarter_number = 4,
                    units,
                    0
                )
            )
            -
            sum(
                iff(
                    quarter_number = 1,
                    units,
                    0
                )
            ) as units_absolute_change

        from product_quarters

        group by 1, 2, 3

        order by abs(units_absolute_change) desc
    """,

    "03_first_observed_vs_2022_history": f"""
        with first_2023 as (

            select
                customer_key,
                purchase_key as first_2023_purchase_key,
                order_date as first_2023_purchase_date

            from {PURCHASES}

            where is_first_observed_purchase_in_period

        ),

        first_purchase_promo as (

            select
                purchase_key,

                max(
                    iff(
                        is_on_promotion,
                        1,
                        0
                    )
                ) as has_promo

            from {PURCHASE_ITEMS}

            where is_first_observed_purchase_in_period

            group by purchase_key

        ),

        observed_2022 as (

            select distinct
                customer_key

            from {STG_PURCHASES}

            where time_order_received_utc
                    < '2023-01-01'
        )

        select
            iff(
                p.customer_key is not null,
                'observed_in_available_2022_history',
                'not_observed_in_available_2022_history'
            ) as prior_history_status,

            count(*) as customers,

            count_if(
                promo.has_promo = 1
            ) as customers_with_promo_first_2023_purchase,

            round(
                100.0
                * count_if(
                    promo.has_promo = 1
                )
                / nullif(count(*), 0),
                2
            ) as promo_share_pct

        from first_2023 f

        left join observed_2022 p
            on f.customer_key = p.customer_key

        left join first_purchase_promo promo
            on f.first_2023_purchase_key
                = promo.purchase_key

        group by 1

        order by 1
    """,

    "04_available_2022_history": f"""
        select
            count(*) as purchases,
            count(distinct customer_key)
                as customers,
            min(time_order_received_utc)
                as first_timestamp,
            max(time_order_received_utc)
                as last_timestamp

        from {STG_PURCHASES}

        where time_order_received_utc
                < '2023-01-01'
    """
}


def main():

    conn = snowflake.connector.connect(
        account="TTIJSKQ-HQ63691",
        user="PIOTRRYB",
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse="COMPUTE_WH",
        database=DATABASE,
        schema=SCHEMA,
        role="ACCOUNTADMIN",
    )

    results = {}

    try:

        for name, sql in QUERIES.items():

            print(f"Running {name}...")

            cursor = conn.cursor()

            try:
                cursor.execute(sql)
                df = cursor.fetch_pandas_all()

                results[name] = json.loads(
                    df.to_json(
                        orient="records",
                        date_format="iso"
                    )
                )

                print(f"  -> {len(df)} rows")

            finally:
                cursor.close()

    finally:
        conn.close()

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            results,
            file,
            indent=2,
            ensure_ascii=False
        )

    print()
    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
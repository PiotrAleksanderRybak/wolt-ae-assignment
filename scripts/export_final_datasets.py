import os
from pathlib import Path

import pandas as pd
import snowflake.connector


OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)


conn = snowflake.connector.connect(
    account="TTIJSKQ-HQ63691",
    user="PIOTRRYB",
    password=os.environ["SNOWFLAKE_PASSWORD"],
    warehouse="COMPUTE_WH",
    database="WOLT_TASK",
    schema="DBT_DEV",
    role="ACCOUNTADMIN",
)


datasets = [
    "FCT_PURCHASES",
    "FCT_PURCHASE_ITEMS",
    "DIM_ITEM_VERSIONS",
]


try:
    for dataset in datasets:
        print(f"Exporting {dataset}...")

        query = f"""
            select *
            from WOLT_TASK.DBT_DEV.{dataset}
        """

        cursor = conn.cursor()

        try:
            cursor.execute(query)

            df = cursor.fetch_pandas_all()

            output_path = OUTPUT_DIR / f"{dataset.lower()}.csv.gz"

            df.to_csv(
                output_path,
                index=False,
                compression="gzip",
            )

            print(
                f"Saved {len(df):,} rows to {output_path}"
            )

        finally:
            cursor.close()

finally:
    conn.close()


print("Export completed.")
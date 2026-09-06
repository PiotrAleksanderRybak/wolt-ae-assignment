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


# All three analytical marts are kept as compressed extracts in the repo.
repo_datasets = [
    "FCT_PURCHASES",
    "FCT_PURCHASE_ITEMS",
    "DIM_ITEM_VERSIONS",
]

# The recruiter asked for two CSV/Google Sheet result files.
# These two facts are exported additionally as normal CSV files for submission.
submission_datasets = {
    "FCT_PURCHASES",
    "FCT_PURCHASE_ITEMS",
}


try:
    for dataset in repo_datasets:
        print(f"Exporting {dataset}...")

        query = f"""
            select *
            from WOLT_TASK.DBT_DEV.{dataset}
        """

        cursor = conn.cursor()

        try:
            cursor.execute(query)
            df = cursor.fetch_pandas_all()

            compressed_path = (
                OUTPUT_DIR / f"{dataset.lower()}.csv.gz"
            )

            df.to_csv(
                compressed_path,
                index=False,
                compression="gzip",
            )

            print(
                f"Saved {len(df):,} rows to "
                f"{compressed_path}"
            )

            if dataset in submission_datasets:
                csv_path = (
                    OUTPUT_DIR / f"{dataset.lower()}.csv"
                )

                df.to_csv(
                    csv_path,
                    index=False,
                )

                print(
                    f"Saved submission CSV to {csv_path}"
                )

        finally:
            cursor.close()

finally:
    conn.close()


print("Export completed.")

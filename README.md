# Wolt Analytics Engineering Assignment

This repository contains my solution to the Wolt Analytics Engineering take-home assignment.

I used dbt on Snowflake to turn the three supplied sources (`purchase_logs`, `item_logs` and `promos`) into a small analytical model that can be used for both purchase-level and product-level analysis.

The main outputs are:

- `fct_purchases` - one row per purchase
- `fct_purchase_items` - one row per basket position
- `dim_item_versions` - historical product versions

The final analytical period is 2023, in line with the assignment description.

## Project layout

```text
sources
  |
  v
staging
  |
  v
intermediate
  |
  v
marts
```

### Staging

The staging models mainly clean names/types and unpack the semi-structured source fields without adding much business logic.

- `stg_purchase_logs` - purchase-level data and the original basket JSON
- `stg_item_logs` - item history, names, category, package attributes and price fields
- `stg_promos` - promotion periods and discounts

I kept the raw item payload in the staging layer because it was useful when checking missing prices and product-history changes.

### Intermediate

`int_purchase_items` explodes each basket into individual item positions.

`int_item_versions` turns the item log into validity intervals (`valid_from_utc` / `valid_to_utc`). This is important because names, categories and prices can change over time.

`int_purchase_items_enriched` joins each purchased item to the item version that was valid at the purchase timestamp, then adds the applicable promotion.

`int_purchases_classified` adds two pieces of logic that I wanted to keep separate from the final facts:

- customer purchase order within the observed 2023 period
- diagnostic flags for suspicious rapid-repeat purchases

## Final models

### `fct_purchases`

Grain: one completed purchase in 2023.

It contains 94,822 rows and includes:

- customer and purchase identifiers
- order date/month
- delivery distance
- basket value, Wolt service fee and courier cost
- derived revenue/cost metrics
- purchase number within the observed period
- first-observed / repeat-purchase flags
- rapid-repeat diagnostics

### `fct_purchase_items`

Grain: one basket position within a purchase.

It contains 120,795 rows and includes:

- purchase/customer identifiers
- quantity
- historically correct product attributes
- historical base price where available
- promotion status and discount
- calculated line values where price is available
- customer-lifecycle fields inherited from the purchase
- rapid-repeat diagnostics

### `dim_item_versions`

Grain: one historical version of an item.

The dimension contains 471 versions for 60 products. There is one current version per item.

## A few source-data issues I handled explicitly

### The purchase file is not actually limited to 2023

The assignment describes `purchase_logs` as 2023 purchases, but the supplied file also contains:

- 667 purchases from 2022
- 3,382 purchases from 2024

I left these rows in staging for traceability, but the final analytical marts only include purchases from 2023-01-01 (inclusive) to 2024-01-01 (exclusive).

There are also singular dbt tests that fail if an out-of-period record enters either final fact table.

### Item attributes change over time

One example I found while validating the model was Tony's Chocolonely Dark Milk Brownie. Its category changes from `Other Confectionary` to `Chocolate` during the year.

For transaction-level analysis I therefore use the item version that was valid when the purchase happened. I did not overwrite historical purchases with the latest category or latest price.

### Price coverage is incomplete

Price is genuinely missing in the source for some item versions. It is not a parsing issue.

At the 2023 purchase-item level, only 39.5% of rows have an available base price. The two highest-volume SKUs have no source base price at all.

Because of this I keep missing prices as `NULL` and expose `has_price` rather than imputing a value. For product/category performance analysis I rely mainly on units, purchases and customers instead of pretending that item-level revenue is complete.

### Rapid-repeat purchases

I found a non-trivial number of purchases with a different `purchase_key` but the same customer, basket, basket value, service fee, courier fee and delivery distance very close together in time.

Using a five-minute detection window, 8,399 purchases (8.86% of the 2023 population) are flagged as rapid-repeat candidates.

I did **not** remove them.

The source describes each row as a completed/delivered purchase and does not provide payment transaction IDs, checkout IDs, idempotency keys, delivery IDs or refund/cancellation status. Without that information I do not think a time threshold alone is enough to call a transaction a duplicate.

Instead, the facts keep the purchases and expose the flags so that important results can be checked both with and without the candidate population.

In a production setting I would investigate this with the upstream owner before defining a permanent deduplication rule.

### "First observed" is not necessarily "new customer"

The customer-lifecycle fields are calculated within the 2023 analytical period.

For that reason the model uses names such as:

- `is_first_observed_purchase_in_period`
- `customer_purchase_number_in_period`

rather than `is_new_customer`.

The available data is not sufficient to prove that the first purchase seen in 2023 is the customer's first-ever Wolt purchase.

## Validation

A few reconciliation checks I used while building the models:

- `fct_purchases`: 94,822 unique purchases, covering 2023-01-01 to 2023-12-31
- `fct_purchase_items`: 120,795 rows and 120,795 distinct `purchase_item_key` values
- `dim_item_versions`: 471 rows and 471 distinct `item_version_key` values
- 2,001 distinct customers and exactly 2,001 first-observed purchases in the period
- 2023 merchandise revenue in the mart reconciles to the 2023 source basket value: EUR 427,698.14

The complete project currently builds successfully with `dbt build`.

## Tests

The project uses dbt tests for, among other things:

- unique keys
- required fields
- relationships between facts/intermediate models
- accepted boolean values
- customer-lifecycle fields
- 2023 date boundaries
- purchase-item grain

## Running the project

Install the Python dependencies:

```bash
pip install -r requirements.txt
```

The Snowflake password is read from the `SNOWFLAKE_PASSWORD` environment variable and is not stored in this repository.

Check the connection:

```bash
dbt debug
```

Build all models and run the tests:

```bash
dbt build
```

Generate dbt documentation if needed:

```bash
dbt docs generate
```

## Exported outputs

The repository includes compressed extracts of the three final analytical datasets:

```text
outputs/
  fct_purchases.csv.gz
  fct_purchase_items.csv.gz
  dim_item_versions.csv.gz
```

The export script is in `scripts/export_final_datasets.py`.

## Why I structured it this way

The main goal was to keep the analytical layer easy to query without hiding uncertainty in the source data.

The choices I considered most important were:

1. keep purchase and purchase-item grains separate;
2. resolve product attributes point-in-time;
3. keep missing prices missing instead of inventing them;
4. keep suspicious transactions visible and auditable rather than deleting them with a heuristic;
5. be explicit about what the available customer history can and cannot tell us.

That gives the business-facing models fairly simple semantics while keeping the assumptions visible in the dbt project.

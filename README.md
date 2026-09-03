# Wolt Analytics Engineering Assignment

## Overview

This dbt project transforms raw Wolt snack purchase, item-log, and promotion data into analytics-ready dimensional models for business analysis.

The resulting datasets support questions such as:

* What products are customers purchasing?
* Which products and categories drive sales?
* What prices are products going for over time?
* How often are products purchased on promotion?
* Which customers use promotions?
* Are customers coming back?
* How do Wolt fees compare with basket value?
* How does revenue evolve over time?
* How do courier costs evolve over time?
* How robust are business conclusions to potential source-data anomalies?

The project is built with **dbt** and runs on **Snowflake**.

---

## Project Structure

The transformation follows three logical layers:

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

The final analytics layer contains two fact tables and one historical product dimension:

```text
fct_purchases
fct_purchase_items
dim_item_versions
```

---

## Staging Models

### `stg_purchase_logs`

Standardizes purchase-level source data, including:

* purchase and customer identifiers
* purchase timestamp
* basket value
* Wolt service fee
* courier base fee
* delivery distance
* nested basket contents

The staging layer preserves the supplied source population, including records outside the declared 2023 analysis period, for traceability and data-quality investigation.

### `stg_item_logs`

Parses and standardizes item-log payloads, including:

* item identifier
* multilingual product names
* brand
* category
* package size
* base price
* currency
* VAT

The raw JSON payload is retained for traceability.

### `stg_promos`

Standardizes promotion attributes, including:

* item identifier
* promotion start and end date
* promotion type
* discount percentage

---

## Intermediate Models

### `int_purchase_items`

Explodes the nested item basket from each purchase into a purchase-item grain.

**Grain:** one row per item position within a purchase.

This provides the bridge between purchase-level transactions and product-level analysis.

### `int_item_versions`

Creates historical versions of products from the item log.

Each product version receives:

* `item_version_key`
* `item_version_number`
* `valid_from_utc`
* `valid_to_utc`
* `is_current`

This allows downstream models to resolve product attributes as they were known at the time a purchase occurred rather than retrospectively applying the latest product attributes.

### `int_purchase_items_enriched`

Enriches purchase items with:

* historically correct product version
* item name
* brand
* category
* historical product price
* VAT and currency
* applicable promotion
* discount percentage
* calculated line value before discount
* calculated line value after discount

The temporal join uses the purchase timestamp to select the product version that was valid at the time of the transaction.

### `int_purchases_classified`

Defines the purchase population used by the final analytical marts and adds customer-lifecycle and data-quality diagnostics.

The analytical population is restricted to:

```text
2023-01-01 00:00:00 inclusive
to
2024-01-01 00:00:00 exclusive
```

The model also adds customer-purchase lifecycle fields:

* `customer_purchase_number_in_period`
* `previous_customer_purchase_time_utc`
* `is_first_observed_purchase_in_period`
* `is_repeat_purchase_in_period`
* `days_since_previous_purchase`

The wording **first observed purchase in period** is intentional.

Because the available analytical population is limited to 2023, the project does not assume that a customer's first observed purchase in this dataset is necessarily their first-ever purchase with Wolt.

The model also adds rapid-repeat diagnostic fields:

* `is_in_rapid_repeat_group`
* `is_rapid_repeat_candidate`
* `seconds_since_matching_purchase`
* `rapid_repeat_sequence_number`
* `rapid_repeat_group_size`

No purchases within the defined 2023 analytical population are removed based on the rapid-repeat heuristic.

---

# Analytics Marts

## `fct_purchases`

**Grain:** one row per completed purchase in the 2023 analysis period.

The model contains:

* purchase and customer identifiers
* order timestamp
* order date and month
* customer purchase number
* first-observed / repeat-purchase classification
* time since previous customer purchase
* delivery distance
* merchandise revenue
* service fee revenue
* gross order revenue
* courier cost
* revenue less courier cost
* service-fee-to-basket ratio
* courier-cost-to-basket ratio
* rapid-repeat diagnostics

Current row count:

```text
94,822 purchases
```

The model can directly support questions about:

* revenue
* courier costs
* Wolt fees
* delivery distance
* purchase frequency
* repeat behavior
* first observed purchases
* suspicious rapid-repeat activity

---

## `fct_purchase_items`

**Grain:** one row per item position within a completed purchase in the 2023 analysis period.

The model contains:

* purchase and customer identifiers
* order date and month
* customer lifecycle fields
* item identifier and basket position
* quantity
* historically correct product version
* item name
* brand
* category
* package information
* historical base price
* currency and VAT
* promotion attributes
* calculated line values
* price-availability flag
* rapid-repeat diagnostics inherited from the purchase

Current row count:

```text
120,795 purchase-item rows
```

This model supports product, category, price, promotion and customer-behavior analysis without requiring analysts to reconstruct historical joins themselves.

---

## `dim_item_versions`

**Grain:** one row per historical version of an item.

The dimension contains:

* `item_version_key`
* `item_key`
* version number
* validity interval
* current-version flag
* historical item name
* historical brand
* historical category
* package information
* product base price
* currency
* VAT

Current dimension size:

```text
Historical versions: 471
Distinct items:        60
Current versions:      60
Versions without price: 108
```

There is exactly one current version per item.

---

# Temporal Product Modeling

Product attributes can change over time.

A purchase should therefore not automatically inherit the latest known version of a product.

`int_item_versions` converts the supplied item log into historical validity intervals.

Purchase items are then matched to the product version valid at:

```text
time_order_received_utc
```

This preserves historical changes such as:

* item-name changes
* category changes
* price changes
* package changes
* other product-attribute changes

For example, the same product can legitimately appear under different historical categories in downstream analysis if its source category changed over time.

This approach avoids historical restatement caused by joining transactions only to the latest product record.

---

# Promotion Logic

Promotions are matched using:

* `item_key`
* purchase date
* promotion start date
* promotion end date

For percentage discounts, an expected discounted line value is calculated using the historically valid item base price and purchased quantity.

Where the source does not provide a product price, price-derived measures remain `NULL` rather than being imputed.

---

# Analysis-Period Contract

The assignment describes `purchase_logs` as containing completed and delivered purchases occurring during 2023.

However, inspection of the supplied source data identified purchases outside that period.

The source contains:

```text
2022:     667 purchases
2023:  94,822 purchases
2024:   3,382 purchases
----------------------
Total: 98,871 purchases
```

The out-of-period records represent:

```text
4,049 purchases
4.10% of the supplied purchase rows
```

Their basket value is:

```text
EUR 17,735.77
```

The 2023 population contains:

```text
EUR 427,698.14
```

of merchandise basket value.

## Modeling decision

The out-of-period records are preserved in the staging layer for traceability.

The final analytical purchase population is restricted to the period defined by the assignment:

```sql
time_order_received_utc >= '2023-01-01'
and time_order_received_utc < '2024-01-01'
```

This ensures that standard queries against the final marts return metrics corresponding to the requested 2023 analysis period.

Explicit dbt tests also verify that records outside 2023 cannot enter the final purchase marts.

---

# Customer Lifecycle Modeling

Customer purchase order is calculated within the 2023 analysis period.

Observed results are:

```text
Customers:                         2,001
First observed purchases:          2,001
Repeat purchases:                 92,821
Total purchases:                  94,822
Maximum purchases by one customer:   272
```

Each customer therefore has exactly one purchase classified as:

```text
is_first_observed_purchase_in_period = true
```

All subsequent purchases for that customer within the analytical period are classified as repeat purchases.

This enables simple analysis of:

* first observed vs repeat purchases
* customer purchase frequency
* time between purchases
* product mix of first observed vs repeat purchases
* customer retention patterns within the observed period

The model deliberately does not label these customers as definitively **new to Wolt**, because purchase history before the available analysis period is not sufficient to establish that.

---

# Data Quality Findings

## Missing Product Prices

Some item-log payloads explicitly contain:

```text
product_base_price = null
```

The missing values therefore originate in the supplied source data rather than from the transformation logic.

At historical item-version level:

```text
Total item versions:         471
Versions without price:      108
Versions with price:         363
Missing-price share:       22.93%
```

Missing source prices are preserved as `NULL`.

No price imputation is performed because there is no authoritative basis for estimating the missing values.

`fct_purchase_items.has_price` allows analysts to explicitly control for price availability when calculating price-based metrics.

This avoids silently turning missing source information into assumed business data.

---

# Rapid Repeat Purchases

## Observation

A material population of purchases has:

* a different `purchase_key`
* the same customer
* identical basket contents
* identical basket value
* identical service fee
* identical courier fee
* identical delivery distance
* a timestamp very close to another matching purchase

These patterns may represent duplicates, but the supplied data does not contain enough transaction-semantic information to prove that they are duplicates.

## Detection logic

Rapid-repeat matching uses:

* customer
* basket contents
* basket value
* Wolt service fee
* courier fee
* delivery distance

The basket is represented by a deterministic basket signature.

When another matching purchase follows within five minutes, the subsequent purchase is flagged as:

```text
is_rapid_repeat_candidate = true
```

The first purchase in the sequence is retained as the initial transaction.

The five-minute threshold is an **anomaly-detection threshold**, not a business definition of a duplicate transaction.

Within the final 2023 analysis population:

```text
Total purchases:             94,822
Rapid-repeat candidates:      8,399
Candidate share:               8.86%
```

The pattern is therefore material enough to warrant explicit visibility in the analytical model.

---

# Decision on Potential Duplicates

I intentionally **did not deduplicate rapid-repeat purchases in the analytical fact tables**.

This decision is based on the semantics of the supplied source data.

The purchase source describes the records as completed and delivered purchases with payment in advance, and each record has a distinct `purchase_key`.

The available fields do not provide sufficient evidence to determine whether a rapid repeat represents:

* an accidental technical retry
* a duplicate checkout request
* two separately created and paid orders
* legitimate repeated purchases
* a customer intentionally placing multiple identical orders
* promotion or quantity-limit behavior
* another upstream process

Automatically deleting records based only on similarity and temporal proximity would introduce an unsupported business assumption into the analytical model.

For example, defining:

```text
119 seconds = duplicate
121 seconds = legitimate purchase
```

would not have a defensible transaction-level basis.

The project therefore follows a **preserve + flag + quantify** approach:

1. Preserve every purchase in the defined analytical population.
2. Flag suspicious rapid-repeat patterns.
3. Expose the diagnostic fields in the analytical marts.
4. Allow downstream sensitivity analysis.
5. Avoid silently changing revenue or order counts without an authoritative transaction-level rule.

---

# Sensitivity Analysis

Rapid-repeat candidates are retained in the analytical source of truth.

Analysts can perform sensitivity analysis by comparing results from:

```sql
select *
from {{ ref('fct_purchases') }}
```

with results excluding candidates:

```sql
select *
from {{ ref('fct_purchases') }}
where not is_rapid_repeat_candidate
```

The same diagnostic fields are propagated to `fct_purchase_items`, allowing product-level conclusions to be tested using the same approach.

The final 2023 population contains 8,399 rapid-repeat candidates, representing 8.86% of purchases.

Revenue, units and product-level sensitivity should therefore be explicitly considered when drawing major business conclusions from the dataset.

---

# What I Would Do in a Production Environment

In a real Wolt data environment, I would not create a permanent deduplication rule from the available fields alone.

I would first investigate the upstream transaction lifecycle and request additional identifiers and statuses such as:

* payment transaction ID
* checkout or session ID
* request or idempotency key
* delivery ID
* order creation event ID
* payment status
* cancellation status
* refund status

These fields would allow rapid repeats to be classified using transaction semantics instead of behavioral heuristics.

For example:

* the same payment transaction associated with multiple purchase records could provide strong evidence of technical duplication
* separate successful payments and separate deliveries would indicate distinct economic transactions
* a second order followed by a refund would require different revenue treatment

Only after validating the behavior with the source-system owner would I introduce an official deduplication rule into the production analytical layer.

Until that information is available, preserving the records while exposing anomaly flags keeps the analytical model auditable and flexible.

---

# Validation and Reconciliation

## Purchase Fact

The final purchase fact contains:

```text
Total purchases:    94,822
Unique customers:    2,001
First date:     2023-01-01
Last date:      2023-12-31
```

Merchandise revenue reconciles to the 2023 source population:

```text
Source 2023 basket value:      EUR 427,698.14
Mart merchandise revenue:      EUR 427,698.14
Aggregate difference:          EUR       0.00
```

---

## Purchase-Item Grain

`fct_purchase_items` contains:

```text
Total rows:                     120,795
Distinct purchase_item_key:     120,795
Missing purchase classification:      0
First date:                  2023-01-01
Last date:                   2023-12-31
```

The equality between row count and distinct `purchase_item_key` confirms the intended one-row-per-basket-position grain.

---

## Customer Lifecycle Reconciliation

`fct_purchases` contains:

```text
First observed purchases:  2,001
Repeat purchases:         92,821
Total:                    94,822
```

The number of first observed purchases exactly equals the number of distinct customers.

At purchase-item level:

```text
Purchase-item rows:                   120,795
Rows from first observed purchases:     2,550
Rows from repeat purchases:            118,245
Missing purchase-number classification:      0
```

---

## Item-Version Dimension

`dim_item_versions` contains:

```text
Versions:               471
Unique version keys:    471
Distinct items:          60
Current versions:        60
Versions without price: 108
```

The number of current versions equals the number of distinct items.

---

# Data Tests

The project includes dbt tests covering:

* primary-key uniqueness
* required-field completeness
* model relationships
* accepted boolean values
* source-to-intermediate integrity
* intermediate-to-mart integrity
* purchase-item grain
* rapid-repeat classification fields
* customer-lifecycle fields
* 2023 analysis-period boundaries

Two explicit singular tests ensure that purchases outside the defined analysis period cannot enter the final marts:

```text
tests/assert_fct_purchases_2023.sql
tests/assert_fct_purchase_items_2023.sql
```

The complete project builds successfully using:

```bash
dbt build
```

---

# Final Analytical Datasets

The principal datasets intended for analytics consumption are:

### `fct_purchases`

Use for:

* orders
* customers
* revenue
* Wolt fees
* courier costs
* delivery distance
* repeat behavior
* customer purchase frequency

### `fct_purchase_items`

Use for:

* products
* categories
* units
* prices
* promotions
* product mix
* product/customer behavior

### `dim_item_versions`

Use for:

* historical product attributes
* historical product prices
* historical categories
* version-level product investigation

Together, these models provide the dimensional analytical layer requested in the assignment.

---

# Running the Project

## Environment

The project uses:

```text
dbt-snowflake==1.11.6
```

Install the Python dependency from the repository root:

```bash
pip install -r requirements.txt
```

## Validate the connection

```bash
dbt debug
```

## Build the full project

```bash
dbt build
```

## Run the final analytical datasets

```bash
dbt run --select fct_purchases fct_purchase_items dim_item_versions
```

## Run tests for the final analytical layer

```bash
dbt test --select fct_purchases fct_purchase_items dim_item_versions
```

## Generate dbt documentation

```bash
dbt docs generate
```

---

# Credentials

Snowflake credentials are not stored in the project repository.

The Snowflake password is provided through the environment variable:

```text
SNOWFLAKE_PASSWORD
```

The local dbt profile references the environment variable using:

```text
{{ env_var('SNOWFLAKE_PASSWORD') }}
```

This keeps credentials outside version control.

---

# Key Modeling Decisions

The principal design decisions in this project are:

1. Separate purchase-level and purchase-item-level fact tables with explicit grains.

2. Expose historical item versions as a reusable dimension.

3. Resolve product attributes point-in-time rather than retrospectively applying the latest state.

4. Match promotions to the date of purchase.

5. Preserve missing source prices rather than imputing unsupported values.

6. Keep the staging layer traceable to the supplied source data.

7. Restrict the final analytical population to the 2023 period defined by the assignment.

8. Explicitly distinguish first observed purchase in the analysis period from a customer's first-ever purchase.

9. Preserve suspected rapid-repeat purchases rather than applying an unsupported deduplication heuristic.

10. Expose rapid-repeat diagnostic fields for downstream sensitivity analysis.

11. Reconcile final financial metrics to the corresponding source population.

12. Keep material data-quality findings, assumptions and business limitations explicit and auditable.

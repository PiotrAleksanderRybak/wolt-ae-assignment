# Wolt Analytics Engineering Assignment

## Overview

This dbt project transforms raw Wolt snack purchase, item-log, and promotion data into analytics-ready models that support common business questions such as:

* What products are customers purchasing?
* Which products and categories drive sales?
* What prices are products going for?
* How often are products purchased on promotion?
* What does purchase-level revenue and courier cost look like?
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

### Staging

#### `stg_purchase_logs`

Standardizes purchase-level source data, including:

* purchase and customer identifiers
* purchase timestamp
* basket value
* Wolt service fee
* courier base fee
* delivery distance
* nested basket contents

#### `stg_item_logs`

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

#### `stg_promos`

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

### `int_item_versions`

Creates historical versions of products from the item log.

Each product version receives:

* `valid_from_utc`
* `valid_to_utc`
* `item_version_number`
* `is_current`

This allows downstream models to resolve product attributes as they were known at the time a purchase occurred rather than applying the latest item attributes retrospectively.

### `int_purchase_items_enriched`

Enriches purchase items with:

* historically correct product version
* product attributes
* price
* applicable promotion
* discount percentage
* calculated line value before discount
* calculated line value after discount

### `int_purchases_classified`

Preserves every purchase from the source while adding diagnostic information for suspicious rapid-repeat purchase patterns.

No purchases are removed in this model.

The classification includes:

* `is_in_rapid_repeat_group`
* `is_rapid_repeat_candidate`
* `seconds_since_matching_purchase`
* `rapid_repeat_sequence_number`
* `rapid_repeat_group_size`

Rapid repeats are identified when purchases share the same:

* customer
* basket contents
* basket value
* service fee
* courier fee
* delivery distance

and another matching purchase occurs shortly afterwards.

The first purchase in a sequence is preserved as the initial event. Subsequent purchases occurring within five minutes of a matching purchase are marked as `is_rapid_repeat_candidate = true`.

The five-minute window is used as an **anomaly-detection threshold**, not as a business definition of a duplicate transaction.

---

## Analytics Marts

### `fct_purchases`

**Grain:** one row per purchase.

The model contains all source purchases and exposes purchase-level analytical metrics including:

* merchandise revenue
* service fee revenue
* gross order revenue
* courier cost
* revenue less courier cost
* delivery distance
* service-fee-to-basket ratio
* courier-cost-to-basket ratio
* rapid-repeat diagnostic fields

Importantly, suspected rapid repeats are **not removed** from the fact table.

### `fct_purchase_items`

**Grain:** one row per item position within a purchase.

The model contains:

* purchase and customer identifiers
* historically correct product attributes
* quantity
* base price
* promotion attributes
* calculated line values
* price-availability flag
* rapid-repeat diagnostic fields inherited from the purchase

This allows product, category, price, and promotion analyses to be run both on the complete source population and as sensitivity analyses excluding rapid-repeat candidates.

---

## Temporal Product Modeling

Product attributes change over time.

A purchase should therefore not automatically inherit the latest known product attributes.

`int_item_versions` creates validity intervals from the item-log history, and purchase items are matched to the version valid at `time_order_received_utc`.

This preserves historical changes such as:

* category changes
* price changes
* other item-attribute changes

For example, the same product can legitimately appear under different historical categories in downstream analysis if the source category changed over time.

---

## Promotion Logic

Promotions are matched using:

* `item_key`
* the purchase date
* the promotion validity period

For percentage discounts, the expected discounted line value is calculated using the item base price and purchased quantity.

Where the source does not provide a product price, price-derived measures remain `NULL` rather than being imputed.

---

## Data Quality Findings

### Missing Product Prices

Some item-log payloads explicitly contain:

```text
product_base_price = null
```

The missing values therefore originate in the supplied source data rather than in the transformation logic.

Observed coverage:

* 471 historical item-version records
* 108 item versions without a price
* 22.93% of item versions without a price

At purchase-item level:

* 126,022 purchase-item rows
* 76,049 purchase-item rows without a price
* 60.35% of purchase-item rows without a price

The effect is highly concentrated in a small number of frequently purchased SKUs.

Two products alone account for approximately 84% of purchase-item records with missing prices.

For this reason:

* missing prices are preserved as `NULL`
* no price imputation is performed
* `fct_purchase_items.has_price` allows analysts to explicitly control for price availability

---

## Rapid Repeat Purchases

### Observation

A material population of purchases has:

* a different `purchase_key`
* the same customer
* identical basket contents
* identical basket value
* identical service fee
* identical courier fee
* identical delivery distance
* a timestamp very close to another matching purchase

Using the strict matching criteria above, the data contains:

* 5,762 subsequent matching purchases within 1 minute
* 7,498 within 2 minutes
* 8,811 within 5 minutes

The five-minute rapid-repeat candidates represent approximately **8.91% of all purchase records**.

Repeated sequences are not limited to pairs. Some matching sequences contain multiple purchases, with the diagnostic model identifying sequences of up to 21 records under the chained five-minute grouping logic.

---

## Decision on Potential Duplicates

I intentionally **did not deduplicate these purchases in the analytical fact tables**.

This decision is based on the semantics of the supplied source data.

The purchase source describes these records as completed and delivered purchases, and each record has a distinct `purchase_key`.

The available data therefore does not provide sufficient evidence to determine whether a rapid repeat represents:

* an accidental technical retry
* a duplicate checkout request
* two separately created and paid orders
* legitimate repeated purchases
* a customer intentionally placing multiple identical orders
* promotion or quantity-limit behavior
* another upstream process

Automatically removing records based only on similarity and temporal proximity would introduce an unverified business assumption into the analytical model.

For example, defining:

```text
119 seconds = duplicate
121 seconds = legitimate purchase
```

would not have a defensible business basis.

The project therefore follows a **preserve + flag + quantify** approach:

1. Preserve every source purchase.
2. Flag suspicious rapid-repeat patterns.
3. Expose the diagnostic fields in the analytical marts.
4. Quantify their potential impact through sensitivity analysis.
5. Avoid silently modifying reported revenue or order counts without an authoritative transaction-level rule.

---

## Rapid Repeat Sensitivity Analysis

The impact of rapid-repeat candidates was quantified without removing them from the source-of-truth marts.

### Orders

```text
All purchases:                    98,871
Without rapid-repeat candidates: 90,060
Rapid-repeat candidates:          8,811
Share:                             8.91%
```

### Merchandise Revenue

```text
All purchase revenue:             EUR 445,433.91
Without rapid-repeat candidates:  EUR 410,076.54
Candidate revenue:                 EUR 35,357.37
Candidate share:                         7.94%
```

### Units Purchased

```text
All units:                        161,980
Without rapid-repeat candidates: 149,166
Candidate units:                   12,814
Candidate share:                     7.91%
```

The similar shares across orders, revenue, and units suggest that rapid-repeat candidates are material but do not disproportionately dominate the overall dataset.

Nevertheless, the approximately EUR 35k revenue associated with these purchases is large enough that major business conclusions should be checked for sensitivity to this population.

---

## What I Would Do in a Production Environment

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
* a second order followed by a refund would require different revenue treatment again

Only after validating the behavior with the source-system owner would I introduce an official deduplication rule into the production analytical layer.

Until that information is available, preserving the records while exposing anomaly flags keeps the analytical model both auditable and flexible.

---

## Validation and Reconciliation

### Purchase-item grain

`fct_purchase_items` contains:

```text
Total rows:                  126,022
Distinct purchase_item_key: 126,022
Null purchase_item_key:           0
Duplicate purchase_item_key:      0
```

Record reconciliation between `int_purchase_items_enriched` and `fct_purchase_items`:

```text
Intermediate rows: 126,022
Mart rows:         126,022
Difference:              0
```

### Purchase revenue reconciliation

Purchase-level merchandise revenue fully reconciles to the source basket value:

```text
Purchases:                  98,871
Source basket value:       EUR 445,433.91
Mart merchandise revenue:  EUR 445,433.91
Mismatched purchases:                   0
Aggregate difference:      EUR       0.00
```

Rapid-repeat classification does not remove or modify source purchases, so this reconciliation remains intact.

---

## Data Tests

The project includes dbt tests covering:

* primary-key uniqueness
* required-field completeness
* model relationships
* accepted values
* source-to-intermediate integrity
* intermediate-to-mart integrity
* rapid-repeat classification fields

The complete project builds successfully with no warnings or errors.

Run:

```bash
dbt build
```

to build the full DAG and execute all tests.

---

## Running the Project

Install dependencies:

```bash
dbt deps
```

Validate the Snowflake connection:

```bash
dbt debug
```

Build the project:

```bash
dbt build
```

Run the marts:

```bash
dbt run --select fct_purchases fct_purchase_items
```

Run mart tests:

```bash
dbt test --select fct_purchases fct_purchase_items
```

---

## Credentials

Snowflake credentials are not stored in the project repository.

The Snowflake password is provided using the environment variable:

```text
SNOWFLAKE_PASSWORD
```

The dbt profile references the variable using:

```text
{{ env_var('SNOWFLAKE_PASSWORD') }}
```

---

## Key Modeling Decisions

The main design decisions in this project are:

1. Separate purchase-level and purchase-item-level facts with explicit grains.
2. Resolve product attributes historically rather than applying the latest state retrospectively.
3. Match promotions to the date of purchase.
4. Preserve missing source prices rather than imputing them.
5. Preserve all completed source purchases rather than applying an unsupported deduplication heuristic.
6. Explicitly flag suspicious rapid-repeat purchase patterns.
7. Support sensitivity analysis without redefining the source of truth.
8. Reconcile final financial metrics back to the supplied source.
9. Keep business assumptions visible and auditable in the data model.

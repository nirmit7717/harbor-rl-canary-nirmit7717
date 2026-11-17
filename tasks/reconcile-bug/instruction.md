# Transaction Reconciliation

## Objective

Build a command-line Python application that processes a CSV file containing transaction records and produces a JSON reconciliation summary.

The application must correctly handle transaction statuses, duplicate transaction IDs, and timestamps that include timezone information.

## Input

The application accepts one command-line argument: the path to an input CSV file.

The CSV file contains the following columns:

| Column | Description |
|---|---|
| tx_id | Unique identifier associated with a transaction |
| timestamp | ISO 8601 timestamp representing when the transaction was recorded |
| amount | Monetary value associated with the transaction |
| status | Current transaction status |

The input file may contain multiple records with the same transaction ID.

## Processing Rules

### 1. Transaction Deduplication

Each transaction ID must appear only once in the final reconciliation.

If multiple records share the same tx_id, retain the record with the most recent timestamp.

Timestamps must be interpreted as actual points in time, taking their timezone information into account. Two timestamps with different UTC offsets must still be compared chronologically.

If two records for the same transaction have exactly the same timestamp, retain the first record encountered in the input file.

### 2. Transaction Status

Transaction statuses are case-insensitive and may contain leading or trailing whitespace.

The application must recognise the following statuses:

- VALID: The transaction is eligible to contribute to the valid transaction summary.
- FAILED: The transaction is counted as a failed transaction.
- PENDING: The transaction is not included in either the valid or failed transaction totals.

Only transactions whose final deduplicated status is VALID may contribute to the valid transaction amount and count.

### 3. Amount Calculation

Calculate the total amount using only the final deduplicated transactions with a VALID status.

Monetary values must be handled with decimal precision rather than relying on floating-point arithmetic.

The final total must be rounded to two decimal places using the standard financial rounding rule (round half up).

### 4. Input Validation

The application must reject invalid input rather than silently producing an incorrect reconciliation.

In particular:

- Timestamps must be valid ISO 8601 timestamps containing timezone information.
- Amounts must be valid numeric monetary values.
- Transaction statuses must belong to the supported status set.
- The input CSV must contain the required columns.

If the input cannot be processed, the application should terminate with a non-zero exit status and provide a meaningful error message.

## Output

On successful execution, print a JSON object to standard output containing exactly these fields:

    {
      "total_valid_amount": 1250.75,
      "valid_count": 3,
      "failed_count": 1
    }

Field descriptions:

| Field | Description |
|---|---|
| total_valid_amount | Sum of amounts from final deduplicated VALID transactions, rounded to two decimal places |
| valid_count | Number of final deduplicated transactions with status VALID |
| failed_count | Number of final deduplicated transactions with status FAILED |

Transactions with a final status of PENDING must not contribute to either count or to the total valid amount.

## Execution

The application must be executable using:

    python reconcile.py <input_csv_path>

For example:

    python reconcile.py input.csv

The application should print the resulting JSON to standard output when processing succeeds.

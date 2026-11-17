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

The file is UTF-8 encoded and may begin with a UTF-8 byte order mark (BOM), which must be accepted.

## Processing Rules

The application must first validate all input rows and resolve duplicate transaction IDs. Only after deduplication should the retained records be classified by status and included in the appropriate output counts and totals.

### 1. Transaction Deduplication

Each transaction ID must appear only once in the final reconciliation.

If multiple records share the same tx_id, retain the record with the most recent timestamp.

Timestamps must be interpreted as actual points in time, taking their timezone information into account. Two timestamps with different UTC offsets must still be compared chronologically.

If two records for the same transaction represent the same point in time, even when written with different UTC offsets, retain the first record encountered in the input file.

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

The final total must be rounded to two decimal places using round half up, with halves rounded away from zero (for example, 2.345 becomes 2.35 and -2.345 becomes -2.35).

The total must keep full decimal precision and must not be converted to a binary floating-point value at any stage, including JSON output.

A total that rounds to zero must be reported as 0, never as negative zero.

### 4. Input Validation

The application must reject invalid input rather than silently producing an incorrect reconciliation.

In particular:

- Timestamps must be valid ISO 8601 timestamps containing timezone information.
- Amounts must be valid numeric monetary values.
- Transaction statuses must belong to the supported status set. Empty or whitespace-only statuses are invalid.
- The input CSV must contain the required columns.
- Transaction IDs must not be empty or contain only whitespace.
- Monetary amounts must be finite numeric values. Values such as NaN and Infinity are invalid.
- Each data row must contain exactly the fields defined by the header; rows with missing or extra fields must be rejected.
- Validation applies to every data row, including PENDING rows and rows superseded by a later record for the same transaction ID.

If the input cannot be processed, the application should terminate with a non-zero exit status, print a meaningful error message to standard error, and must not print a summary or an uncaught exception traceback.

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

`total_valid_amount` must be a JSON number (not a string); `valid_count` and `failed_count` must be JSON integers.

Transactions with a final status of PENDING must not contribute to either count or to the total valid amount.

## Execution

The application is located at `/app/reconcile.py` and must be executable using:

    python reconcile.py <input_csv_path>

For example:

    python reconcile.py input.csv

The application should print the resulting JSON to standard output when processing succeeds.

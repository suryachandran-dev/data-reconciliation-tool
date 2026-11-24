# Data Reconciliation Tool

A command-line tool that compares two CSV files by key and reports every difference: changed values, rows missing from the target, and rows missing from the source.

It is built for the check that follows a data migration or a batch run: did every record arrive, and did it arrive unchanged?

## What it reports

- **Value mismatches**: the same record has a different value in a column, shown with both values
- **Missing in target**: a record in the source file that is not in the target file
- **Missing in source**: a record in the target file that is not in the source file
- **Duplicate keys**: the same key appearing more than once in a file

Numbers are compared by value, so `1200` and `1200.00` count as equal. Spaces around a value are ignored.

## Requirements

Python 3.8 or later. No extra packages are needed.

## Usage

```
python reconcile.py SOURCE TARGET --key COLUMN [COLUMN ...]
```

| Option | Purpose |
| --- | --- |
| `--key` | Column or columns that identify a row (required) |
| `--ignore` | Columns to leave out of the comparison |
| `--ignore-case` | Treat `active` and `ACTIVE` as equal |
| `--report FILE` | Write the differences to a CSV file |

The exit code is `0` when the files match, `1` when differences are found, and `2` when a file cannot be read. That makes the tool usable as a pass/fail step in a batch job.

## Example

The `sample_data` folder holds two versions of an insurance policy extract.

```
python reconcile.py sample_data/policies_source.csv sample_data/policies_target.csv --key policy_id --report sample_data/sample_report.csv
```

Output:

```
Source rows:        8
Target rows:        8
Matched:            5
Value mismatches:   2
Missing in target:  1
Missing in source:  1

Differences:
  POL-1003: status is 'Lapsed' in source, 'Active' in target
  POL-1005: premium is '1100.00' in source, '1150.00' in target
  POL-1007: missing in target
  POL-1009: missing in source

Report written to sample_data/sample_report.csv
```

POL-1001 has a premium of `1200.00` in the source and `1200` in the target. The tool treats these as equal, so it is not reported.

The report file has one row per difference:

| policy_id | issue | column | source_value | target_value |
| --- | --- | --- | --- | --- |
| POL-1003 | value_mismatch | status | Lapsed | Active |
| POL-1005 | value_mismatch | premium | 1100.00 | 1150.00 |
| POL-1007 | missing_in_target | | | |
| POL-1009 | missing_in_source | | | |

## Running the tests

```
python -m unittest discover -s tests
```

## Project structure

```
reconcile.py              the tool
sample_data/              example source and target files, and the report they produce
tests/test_reconcile.py   unit tests
```

## Limitations

- Both files are loaded into memory, so very large files need a machine with enough RAM.
- Columns are matched by header name. A column that exists in only one file is listed but not compared.
- The sample data is made up for the example and does not describe real people or policies.

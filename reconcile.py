"""Compare two CSV files by key and report every difference.

Typical use: check that records moved from one system to another
arrived complete and unchanged.

    python reconcile.py source.csv target.csv --key policy_id
"""

import argparse
import csv
import sys
from decimal import Decimal, InvalidOperation

MISSING_IN_TARGET = "missing_in_target"
MISSING_IN_SOURCE = "missing_in_source"
VALUE_MISMATCH = "value_mismatch"


def load_rows(path, key_columns):
    """Read a CSV file into a dict of rows indexed by key.

    Returns (column names, rows by key, list of duplicated keys).
    Values are stripped of surrounding spaces. When a key appears more
    than once, the first row is kept and the key is reported as a duplicate.
    """
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames
        if not columns:
            raise ValueError(f"{path} has no header row")

        absent = [column for column in key_columns if column not in columns]
        if absent:
            raise ValueError(f"{path} has no key column: {', '.join(absent)}")

        rows = {}
        duplicates = []
        for raw in reader:
            row = {name: (value or "").strip() for name, value in raw.items() if name is not None}
            key = tuple(row[column] for column in key_columns)
            if key in rows:
                duplicates.append(key)
                continue
            rows[key] = row
    return columns, rows, duplicates


def values_match(source_value, target_value, ignore_case=False):
    """Return True when two cell values should count as equal.

    Numbers are compared by value, so 1200 and 1200.00 match.
    """
    if source_value == target_value:
        return True
    if ignore_case and source_value.casefold() == target_value.casefold():
        return True
    try:
        return Decimal(source_value) == Decimal(target_value)
    except InvalidOperation:
        return False


def reconcile(source_rows, target_rows, compare_columns, ignore_case=False):
    """Compare two sets of rows and return a list of differences.

    Each difference is a dict with: key, issue, column, source_value, target_value.
    """
    differences = []

    for key in sorted(source_rows):
        source = source_rows[key]
        target = target_rows.get(key)
        if target is None:
            differences.append(_difference(key, MISSING_IN_TARGET))
            continue
        for column in compare_columns:
            if not values_match(source[column], target[column], ignore_case):
                differences.append(
                    _difference(key, VALUE_MISMATCH, column, source[column], target[column])
                )

    for key in sorted(target_rows):
        if key not in source_rows:
            differences.append(_difference(key, MISSING_IN_SOURCE))

    return differences


def _difference(key, issue, column="", source_value="", target_value=""):
    return {
        "key": key,
        "issue": issue,
        "column": column,
        "source_value": source_value,
        "target_value": target_value,
    }


def write_report(path, key_columns, differences):
    """Write the differences to a CSV file, one row per difference."""
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(list(key_columns) + ["issue", "column", "source_value", "target_value"])
        for item in differences:
            writer.writerow(
                list(item["key"])
                + [item["issue"], item["column"], item["source_value"], item["target_value"]]
            )


def summarize(source_rows, target_rows, differences):
    """Count the outcome of a reconciliation."""
    mismatched_keys = {item["key"] for item in differences if item["issue"] == VALUE_MISMATCH}
    missing_in_target = sum(1 for item in differences if item["issue"] == MISSING_IN_TARGET)
    missing_in_source = sum(1 for item in differences if item["issue"] == MISSING_IN_SOURCE)
    in_both = len(source_rows) - missing_in_target
    return {
        "source_rows": len(source_rows),
        "target_rows": len(target_rows),
        "matched": in_both - len(mismatched_keys),
        "mismatched": len(mismatched_keys),
        "missing_in_target": missing_in_target,
        "missing_in_source": missing_in_source,
    }


def format_key(key):
    return "/".join(key)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compare two CSV files by key and report the differences."
    )
    parser.add_argument("source", help="CSV file treated as the source of truth")
    parser.add_argument("target", help="CSV file to check against the source")
    parser.add_argument(
        "--key", nargs="+", required=True, metavar="COLUMN",
        help="column or columns that identify a row",
    )
    parser.add_argument(
        "--ignore", nargs="+", default=[], metavar="COLUMN",
        help="columns to leave out of the comparison",
    )
    parser.add_argument(
        "--ignore-case", action="store_true",
        help="treat values that differ only by letter case as equal",
    )
    parser.add_argument("--report", metavar="FILE", help="write the differences to this CSV file")
    args = parser.parse_args(argv)

    try:
        source_columns, source_rows, source_duplicates = load_rows(args.source, args.key)
        target_columns, target_rows, target_duplicates = load_rows(args.target, args.key)
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    skipped = set(args.key) | set(args.ignore)
    compare_columns = [c for c in source_columns if c in target_columns and c not in skipped]
    only_in_source = [c for c in source_columns if c not in target_columns]
    only_in_target = [c for c in target_columns if c not in source_columns]

    differences = reconcile(source_rows, target_rows, compare_columns, args.ignore_case)
    summary = summarize(source_rows, target_rows, differences)

    print(f"Source rows:        {summary['source_rows']}")
    print(f"Target rows:        {summary['target_rows']}")
    print(f"Matched:            {summary['matched']}")
    print(f"Value mismatches:   {summary['mismatched']}")
    print(f"Missing in target:  {summary['missing_in_target']}")
    print(f"Missing in source:  {summary['missing_in_source']}")

    if only_in_source:
        print(f"Columns only in source (not compared): {', '.join(only_in_source)}")
    if only_in_target:
        print(f"Columns only in target (not compared): {', '.join(only_in_target)}")
    for label, duplicates in (("source", source_duplicates), ("target", target_duplicates)):
        if duplicates:
            keys = ", ".join(format_key(key) for key in duplicates)
            print(f"Duplicate keys in {label} (first row kept): {keys}")

    if differences:
        print()
        print("Differences:")
        for item in differences:
            if item["issue"] == VALUE_MISMATCH:
                print(
                    f"  {format_key(item['key'])}: {item['column']} is "
                    f"'{item['source_value']}' in source, '{item['target_value']}' in target"
                )
            else:
                print(f"  {format_key(item['key'])}: {item['issue'].replace('_', ' ')}")

    if args.report:
        write_report(args.report, args.key, differences)
        print()
        print(f"Report written to {args.report}")

    has_problems = bool(differences or source_duplicates or target_duplicates)
    return 1 if has_problems else 0


if __name__ == "__main__":
    sys.exit(main())

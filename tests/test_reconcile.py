import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import reconcile as rec


def write_csv(folder, name, lines):
    path = os.path.join(folder, name)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return path


class ValuesMatchTests(unittest.TestCase):
    def test_identical_text_matches(self):
        self.assertTrue(rec.values_match("Active", "Active"))

    def test_different_text_does_not_match(self):
        self.assertFalse(rec.values_match("Active", "Lapsed"))

    def test_numbers_compare_by_value(self):
        self.assertTrue(rec.values_match("1200", "1200.00"))

    def test_different_numbers_do_not_match(self):
        self.assertFalse(rec.values_match("1100.00", "1150.00"))

    def test_case_differs_by_default(self):
        self.assertFalse(rec.values_match("active", "ACTIVE"))

    def test_case_ignored_when_asked(self):
        self.assertTrue(rec.values_match("active", "ACTIVE", ignore_case=True))


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def load(self, name, lines, key=("id",)):
        path = write_csv(self.folder.name, name, lines)
        return rec.load_rows(path, list(key))

    def test_identical_files_have_no_differences(self):
        lines = ["id,name,amount", "1,Asha,10", "2,David,20"]
        _, source, _ = self.load("a.csv", lines)
        _, target, _ = self.load("b.csv", lines)
        self.assertEqual(rec.reconcile(source, target, ["name", "amount"]), [])

    def test_value_mismatch_is_reported_with_both_values(self):
        _, source, _ = self.load("a.csv", ["id,name,amount", "1,Asha,10"])
        _, target, _ = self.load("b.csv", ["id,name,amount", "1,Asha,15"])
        differences = rec.reconcile(source, target, ["name", "amount"])
        self.assertEqual(len(differences), 1)
        self.assertEqual(differences[0]["issue"], rec.VALUE_MISMATCH)
        self.assertEqual(differences[0]["column"], "amount")
        self.assertEqual(differences[0]["source_value"], "10")
        self.assertEqual(differences[0]["target_value"], "15")

    def test_row_missing_in_target(self):
        _, source, _ = self.load("a.csv", ["id,name", "1,Asha", "2,David"])
        _, target, _ = self.load("b.csv", ["id,name", "1,Asha"])
        differences = rec.reconcile(source, target, ["name"])
        self.assertEqual([(d["key"], d["issue"]) for d in differences],
                         [(("2",), rec.MISSING_IN_TARGET)])

    def test_row_missing_in_source(self):
        _, source, _ = self.load("a.csv", ["id,name", "1,Asha"])
        _, target, _ = self.load("b.csv", ["id,name", "1,Asha", "3,Meera"])
        differences = rec.reconcile(source, target, ["name"])
        self.assertEqual([(d["key"], d["issue"]) for d in differences],
                         [(("3",), rec.MISSING_IN_SOURCE)])

    def test_surrounding_spaces_are_ignored(self):
        _, source, _ = self.load("a.csv", ["id,name", "1,Asha"])
        _, target, _ = self.load("b.csv", ["id,name", "1,  Asha  "])
        self.assertEqual(rec.reconcile(source, target, ["name"]), [])

    def test_duplicate_keys_are_reported_and_first_row_kept(self):
        _, rows, duplicates = self.load("a.csv", ["id,name", "1,Asha", "1,Other"])
        self.assertEqual(duplicates, [("1",)])
        self.assertEqual(rows[("1",)]["name"], "Asha")

    def test_composite_key(self):
        lines = ["region,id,amount", "UK,1,10", "IN,1,20"]
        _, source, _ = self.load("a.csv", lines, key=("region", "id"))
        _, target, _ = self.load("b.csv", ["region,id,amount", "UK,1,10", "IN,1,25"],
                                 key=("region", "id"))
        differences = rec.reconcile(source, target, ["amount"])
        self.assertEqual(len(differences), 1)
        self.assertEqual(differences[0]["key"], ("IN", "1"))

    def test_missing_key_column_raises(self):
        path = write_csv(self.folder.name, "a.csv", ["name,amount", "Asha,10"])
        with self.assertRaises(ValueError):
            rec.load_rows(path, ["id"])

    def test_summary_counts(self):
        _, source, _ = self.load("a.csv", ["id,amount", "1,10", "2,20", "3,30"])
        _, target, _ = self.load("b.csv", ["id,amount", "1,10", "2,25", "4,40"])
        differences = rec.reconcile(source, target, ["amount"])
        summary = rec.summarize(source, target, differences)
        self.assertEqual(summary, {
            "source_rows": 3,
            "target_rows": 3,
            "matched": 1,
            "mismatched": 1,
            "missing_in_target": 1,
            "missing_in_source": 1,
        })


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def test_exit_code_zero_when_files_match(self):
        lines = ["id,amount", "1,10"]
        a = write_csv(self.folder.name, "a.csv", lines)
        b = write_csv(self.folder.name, "b.csv", lines)
        self.assertEqual(rec.main([a, b, "--key", "id"]), 0)

    def test_exit_code_one_and_report_written_when_files_differ(self):
        a = write_csv(self.folder.name, "a.csv", ["id,amount", "1,10"])
        b = write_csv(self.folder.name, "b.csv", ["id,amount", "1,99"])
        report = os.path.join(self.folder.name, "report.csv")
        self.assertEqual(rec.main([a, b, "--key", "id", "--report", report]), 1)
        with open(report, newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[0], ["id", "issue", "column", "source_value", "target_value"])
        self.assertEqual(rows[1], ["1", "value_mismatch", "amount", "10", "99"])

    def test_ignored_column_is_not_compared(self):
        a = write_csv(self.folder.name, "a.csv", ["id,amount,note", "1,10,old"])
        b = write_csv(self.folder.name, "b.csv", ["id,amount,note", "1,10,new"])
        self.assertEqual(rec.main([a, b, "--key", "id", "--ignore", "note"]), 0)

    def test_exit_code_two_when_file_is_missing(self):
        a = write_csv(self.folder.name, "a.csv", ["id,amount", "1,10"])
        missing = os.path.join(self.folder.name, "nope.csv")
        self.assertEqual(rec.main([a, missing, "--key", "id"]), 2)


if __name__ == "__main__":
    unittest.main()

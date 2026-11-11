"""End-to-end tests for the csv2json command-line tool."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "csv2json", *args],
        cwd=ROOT,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )


class ConversionTests(unittest.TestCase):
    def test_stdin_to_array(self) -> None:
        result = run_cli(stdin="name,age\nAlice,30\nBob,41\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            [{"name": "Alice", "age": "30"}, {"name": "Bob", "age": "41"}],
        )

    def test_empty_input_yields_empty_array(self) -> None:
        result = run_cli(stdin="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "[]")

    def test_types_are_inferred_on_request(self) -> None:
        result = run_cli(
            "--types",
            stdin="id,score,active,note\n007,3.5,true,\n42,1e3,False,hello\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            [
                {"id": "007", "score": 3.5, "active": True, "note": None},
                {"id": 42, "score": 1000.0, "active": False, "note": "hello"},
            ],
        )

    def test_shorts_rows_are_padded_and_long_rows_rejected(self) -> None:
        padded = run_cli(stdin="a,b\n1\n")
        self.assertEqual(padded.returncode, 0, padded.stderr)
        self.assertEqual(json.loads(padded.stdout), [{"a": "1", "b": ""}])

        rejected = run_cli(stdin="a,b\n1,2,3\n")
        self.assertEqual(rejected.returncode, 1)
        self.assertIn("row 2 has 3 fields", rejected.stderr)

    def test_duplicate_headers_are_rejected(self) -> None:
        result = run_cli(stdin="id,id\n1,2\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("duplicate header", result.stderr)

    def test_no_header_uses_positional_keys(self) -> None:
        result = run_cli("--no-header", stdin="1,2\n3,4\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            [
                {"column_1": "1", "column_2": "2"},
                {"column_1": "3", "column_2": "4"},
            ],
        )

    def test_ndjson(self) -> None:
        result = run_cli("--ndjson", stdin="a\n1\n2\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual([json.loads(line) for line in lines], [{"a": "1"}, {"a": "2"}])

    def test_indent_pretty_prints(self) -> None:
        result = run_cli("--indent", "2", stdin="a\n1\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith('[\n  {\n    "a": "1"\n  }\n]'))
        self.assertEqual(json.loads(result.stdout), [{"a": "1"}])

    def test_tab_delimiter(self) -> None:
        result = run_cli("-d", "\\t", stdin="a\tb\n1\t2\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [{"a": "1", "b": "2"}])

    def test_blank_lines_are_skipped(self) -> None:
        result = run_cli(stdin="a\n1\n\n2\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [{"a": "1"}, {"a": "2"}])


class FileTests(unittest.TestCase):
    def test_file_input_and_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "input.csv"
            dst = Path(tmp) / "output.json"
            src.write_text("a,b\n1,2\n", encoding="utf-8")
            result = run_cli(str(src), "-o", str(dst))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(json.loads(dst.read_text(encoding="utf-8")), [{"a": "1", "b": "2"}])

    def test_bom_is_stripped_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "bom.csv"
            src.write_text("id\n1\n", encoding="utf-8-sig")
            result = run_cli(str(src))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), [{"id": "1"}])

    def test_missing_file_reports_error(self) -> None:
        result = run_cli("definitely-not-here.csv")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot open", result.stderr)

    def test_version(self) -> None:
        result = run_cli("--version")
        self.assertEqual(result.returncode, 0)
        self.assertIn("csv2json", result.stdout)


if __name__ == "__main__":
    unittest.main()

"""Command-line interface for csv2json.

Converts CSV input (file or stdin) to JSON output (file or stdout) using only
the Python standard library. Records are streamed one at a time, so memory use
stays flat regardless of input size.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence, TextIO

from . import __version__

__all__ = ["ConversionError", "build_parser", "iter_records", "main", "write_records"]

# Type inference patterns. Deliberately explicit: ``int()`` / ``float()`` are
# too permissive (they accept "1_000", "nan", "inf", ...), which would corrupt
# data or emit JSON that strict parsers reject.
_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")
_LEADING_ZERO_RE = re.compile(r"^[+-]?0\d")


class ConversionError(Exception):
    """Raised when the input cannot be converted."""


def _non_negative_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid integer: {value!r}") from None
    if number < 0:
        raise argparse.ArgumentTypeError("indent must be zero or greater")
    return number


def _delimiter(value: str) -> str:
    escapes = {"\\t": "\t", "\\n": "\n", "\\r": "\r"}
    delimiter = escapes.get(value, value)
    if len(delimiter) != 1:
        raise argparse.ArgumentTypeError(
            f"delimiter must be a single character, got {value!r}"
        )
    return delimiter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="csv2json",
        description="Convert CSV to JSON.",
        epilog=(
            "examples:\n"
            "  csv2json data.csv\n"
            "  csv2json data.csv -o data.json --types\n"
            "  cat data.csv | csv2json --ndjson"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input",
        nargs="?",
        metavar="INPUT",
        help="CSV file to read (default: stdin)",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="write JSON to FILE instead of stdout",
    )
    parser.add_argument(
        "-d",
        "--delimiter",
        type=_delimiter,
        default=",",
        metavar="CHAR",
        help="field delimiter (default: ','); use '\\t' for tab",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8-sig",
        metavar="ENC",
        help="input encoding (default: utf-8-sig, which also strips a BOM)",
    )
    parser.add_argument(
        "--no-header",
        action="store_true",
        help="the CSV has no header row; keys are column_1, column_2, ...",
    )
    parser.add_argument(
        "--types",
        action="store_true",
        help="infer integers, floats, booleans and nulls instead of emitting strings",
    )
    parser.add_argument(
        "--ndjson",
        action="store_true",
        help="emit one JSON object per line (JSON Lines) instead of an array",
    )
    parser.add_argument(
        "--indent",
        type=_non_negative_int,
        default=None,
        metavar="N",
        help="pretty-print the array with N spaces of indentation",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def _infer_type(value: str) -> Any:
    """Convert a CSV string to a JSON scalar, best effort.

    Leading zeros are preserved (``007`` stays a string) because IDs, zip codes
    and phone numbers would otherwise lose meaning. ``nan``/``inf`` stay strings
    since they are not valid JSON numbers.
    """
    text = value.strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if _LEADING_ZERO_RE.match(text):
        return value
    if _INT_RE.match(text):
        return int(text)
    if _FLOAT_RE.match(text):
        return float(text)
    return value


def _check_headers(headers: list[str]) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for header in headers:
        if header in seen and header not in duplicates:
            duplicates.append(header)
        seen.add(header)
    if duplicates:
        shown = ", ".join(repr(name) for name in duplicates)
        raise ConversionError(f"duplicate header name(s): {shown}")


def _make_record(
    row: list[str],
    headers: list[str],
    row_number: int,
    infer_types: bool,
) -> dict[str, Any]:
    width = len(headers)
    if len(row) > width:
        raise ConversionError(
            f"row {row_number} has {len(row)} fields but the header has {width}"
        )
    row = row + [""] * (width - len(row))
    if infer_types:
        values = [_infer_type(value) for value in row]
    else:
        values = row
    return dict(zip(headers, values))


def iter_records(
    stream: TextIO,
    *,
    delimiter: str = ",",
    has_header: bool = True,
    infer_types: bool = False,
) -> Iterator[dict[str, Any]]:
    """Yield one dict per data row, streaming the CSV as it is read."""
    reader = csv.reader(stream, delimiter=delimiter)
    try:
        first: list[str] | None = None
        for candidate in reader:
            if candidate:  # skip blank lines, as csv.DictReader does
                first = candidate
                break
        if first is None:
            return

        if has_header:
            headers = list(first)
            if headers and headers[0].startswith("﻿"):
                headers[0] = headers[0].lstrip("﻿")
            headers = [name.strip() for name in headers]
            _check_headers(headers)
            row_number = 2
        else:
            headers = [f"column_{index}" for index in range(1, len(first) + 1)]
            row_number = 1
            yield _make_record(first, headers, row_number, infer_types)
            row_number += 1

        for row in reader:
            if not row:
                continue
            yield _make_record(row, headers, row_number, infer_types)
            row_number += 1
    except csv.Error as exc:
        raise ConversionError(f"malformed CSV: {exc}") from exc


def _dump_record(record: dict[str, Any], indent: int | None) -> str:
    if indent is None:
        return json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    block = json.dumps(record, ensure_ascii=False, indent=indent)
    if indent == 0:
        return block
    pad = " " * indent
    return "\n".join(pad + line for line in block.splitlines())


def write_records(
    records: Iterable[dict[str, Any]],
    out: TextIO,
    *,
    indent: int | None = None,
    ndjson: bool = False,
) -> None:
    """Write records as a JSON array, or as JSON Lines when ``ndjson`` is set."""
    if ndjson:
        for record in records:
            out.write(_dump_record(record, None))
            out.write("\n")
        return

    out.write("[")
    empty = True
    for record in records:
        if empty:
            empty = False
        else:
            out.write(",")
        if indent is not None:
            out.write("\n")
        out.write(_dump_record(record, indent))
    if indent is not None and not empty:
        out.write("\n")
    out.write("]\n")


def _prepare_stdin(encoding: str) -> TextIO:
    """Read stdin as ``encoding``, including BOM handling, when possible."""
    reconfigure = getattr(sys.stdin, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding=encoding, newline="")
        except LookupError:
            raise ConversionError(f"unknown encoding {encoding!r}") from None
        except (OSError, ValueError):
            pass  # detached or replaced stream: fall back to its own encoding
    return sys.stdin


def _open_input(stack: contextlib.ExitStack, path: str | None, encoding: str) -> TextIO:
    if path is None or path == "-":
        return _prepare_stdin(encoding)
    try:
        return stack.enter_context(
            open(path, "r", encoding=encoding, newline="")
        )
    except (OSError, LookupError) as exc:
        detail = getattr(exc, "strerror", None) or str(exc)
        raise ConversionError(f"cannot open {path!r}: {detail}") from exc


def _open_output(stack: contextlib.ExitStack, path: str | None) -> TextIO:
    if path is None or path == "-":
        return sys.stdout
    try:
        return stack.enter_context(
            open(path, "w", encoding="utf-8", newline="")
        )
    except OSError as exc:
        detail = exc.strerror or str(exc)
        raise ConversionError(f"cannot open {path!r}: {detail}") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.ndjson and args.indent is not None:
        parser.error("--indent cannot be combined with --ndjson")

    try:
        with contextlib.ExitStack() as stack:
            stream = _open_input(stack, args.input, args.encoding)
            out = _open_output(stack, args.output)
            records = iter_records(
                stream,
                delimiter=args.delimiter,
                has_header=not args.no_header,
                infer_types=args.types,
            )
            write_records(
                records,
                out,
                indent=args.indent,
                ndjson=args.ndjson,
            )
            out.flush()
    except ConversionError as exc:
        print(f"csv2json: error: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())

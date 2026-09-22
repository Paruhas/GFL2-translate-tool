#!/usr/bin/env python3
"""Export a GFL2 LangPackage table to one UTF-8 JSON file for translation.

Python 3.10+; standard library only. Translate the text values, preserving IDs.
Keep the original .bytes file for
langpackage_import.py. Neither script needs to be installed.

Double-click this script with LangPackageTableCnData.bytes beside it to create
translations.json. Double-click langpackage_import.py after translating it.
Command-line arguments remain optional for choosing other paths.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import struct
import sys
from typing import Iterator


ORIGINAL_NAME = "LangPackageTableCnData.bytes"
TRANSLATIONS_FILE = "output/translations.json"


class TableError(ValueError):
    """Invalid or unsupported input, reported without a traceback by the CLI."""


@dataclass(slots=True)
class Field:
    number: int
    wire: int
    start: int
    payload: int
    end: int
    value: int = 0


def read_varint(data: bytes, pos: int, end: int) -> tuple[int, int]:
    value = 0
    for shift in range(0, 70, 7):
        if pos >= end:
            raise TableError(f"Truncated protobuf varint at byte {pos}.")
        byte = data[pos]
        pos += 1
        if shift == 63 and byte > 1:
            raise TableError(f"Protobuf varint exceeds 64 bits at byte {pos - 1}.")
        value |= (byte & 127) << shift
        if byte < 128:
            return value, pos
    raise TableError("Overlong protobuf varint.")


def varint(value: int) -> bytes:
    if not 0 <= value < 1 << 64:
        raise TableError("Protobuf integer is outside the unsigned 64-bit range.")
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def fields(data: bytes, start: int = 0, end: int | None = None) -> Iterator[Field]:
    end = len(data) if end is None else end
    if not 0 <= start <= end <= len(data):
        raise TableError("Protobuf message bounds are outside the file.")
    pos = start
    while pos < end:
        begin = pos
        tag, pos = read_varint(data, pos, end)
        number, wire = tag >> 3, tag & 7
        if not 1 <= number < 1 << 29:
            raise TableError(f"Invalid protobuf field number at byte {begin}.")
        payload, value = pos, 0
        if wire == 0:
            value, pos = read_varint(data, pos, end)
        elif wire == 2:
            length, pos = read_varint(data, pos, end)
            payload = pos
            pos += length
        elif wire in (1, 5):
            pos += 8 if wire == 1 else 4
        else:
            raise TableError(f"Unsupported protobuf wire type {wire} at byte {begin}.")
        if pos > end:
            raise TableError(f"Protobuf field at byte {begin} extends beyond its message.")
        yield Field(number, wire, begin, payload, pos, value)


def single(items: list[Field], number: int, wire: int, *, optional: bool = False) -> Field | None:
    matches = [f for f in items if f.number == number]
    if not matches and optional:
        return None
    if len(matches) != 1 or matches[0].wire != wire:
        raise TableError(f"Expected one field #{number} with wire type {wire}.")
    return matches[0]


@dataclass(slots=True)
class Row:
    id: int
    text: str
    field: Field


@dataclass(slots=True)
class Index:
    field: Field
    value_field: Field
    offset: int
    length: int


@dataclass(slots=True)
class Table:
    data: bytes
    body_start: int
    metadata: list[Field]
    indexes: list[Index]
    rows: list[Row]

def load_table(path: Path) -> Table:
    data = path.read_bytes()
    if len(data) < 4:
        raise TableError("The table is shorter than its four-byte header.")
    body_start = 4 + struct.unpack_from("<I", data)[0]
    if body_start > len(data):
        raise TableError("The table header points beyond the end of the file.")
    metadata = list(fields(data, 4, body_start))
    rows, ids, boundaries = [], set(), {0}
    for outer in fields(data, body_start):
        if (outer.number, outer.wire) != (1, 2):
            raise TableError("The row section contains an unsupported non-row field.")
        inner = list(fields(data, outer.payload, outer.end))
        identity = single(inner, 1, 0)
        text = single(inner, 2, 2, optional=True)
        assert identity is not None
        if identity.value in ids:
            raise TableError(f"Duplicate text ID {identity.value} in the source table.")
        ids.add(identity.value)
        try:
            value = data[text.payload:text.end].decode("utf-8") if text else ""
        except UnicodeDecodeError as exc:
            raise TableError(f"Text ID {identity.value} is not valid UTF-8.") from exc
        rows.append(Row(identity.value, value, outer))
        boundaries.add(outer.end - body_start)

    indexes = []
    for outer in metadata:
        if outer.number == 1 and outer.wire == 2:
            raise TableError("The header includes rows instead of only table metadata.")
        if outer.number != 3:
            continue
        if outer.wire != 2:
            raise TableError("Unsupported table index encoding.")
        inner = list(fields(data, outer.payload, outer.end))
        single(inner, 1, 0, optional=True)  # Index key: preserve, including omitted zero.
        value = single(inner, 2, 2)
        assert value is not None
        parts = list(fields(data, value.payload, value.end))
        offset = single(parts, 1, 0, optional=True)
        length = single(parts, 2, 0)
        assert length is not None
        start, size = offset.value if offset else 0, length.value
        if size == 0 or start not in boundaries or start + size not in boundaries:
            raise TableError("An index range does not align with complete rows.")
        indexes.append(Index(outer, value, start, size))
    # Require complete, non-overlapping coverage; do not guess at an unknown index layout.
    cursor = 0
    for index in sorted(indexes, key=lambda item: item.offset):
        if index.offset != cursor:
            raise TableError("The table index has a gap or overlapping ranges.")
        cursor += index.length
    if cursor != len(data) - body_start:
        raise TableError("The index does not cover the complete row section.")
    return Table(data, body_start, metadata, indexes, rows)


def export_table(source: Path, destination: Path, chunk_size: int | None = None) -> tuple[int, int]:
    if chunk_size is not None and chunk_size < 1:
        raise TableError("Chunk size must be at least 1.")
    if destination.exists():
        raise FileExistsError(f"The export destination already exists: {destination}")
    table = load_table(source)
    rows = sorted(table.rows, key=lambda row: row.id)
    size = chunk_size if chunk_size is not None else max(1, len(rows))
    count = max(1, (len(rows) + size - 1) // size)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if chunk_size is not None:
        destination.mkdir()
    for part in range(count):
        batch = rows[part * size:(part + 1) * size]
        texts = {str(row.id): row.text for row in batch}
        document = {"texts": texts}
        path = destination if chunk_size is None else destination / f"{part + 1:04d}.json"
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    return len(rows), count


def nearby_original(directory: Path) -> Path:
    source = directory / ORIGINAL_NAME
    if not source.is_file():
        raise TableError(
            f"Place the untouched {ORIGINAL_NAME} file beside both scripts, then run this script again.\n"
            f"Folder: {directory}"
        )
    return source


def wait_to_close() -> None:
    # Explorer launches a temporary console for .py files. Keep results and errors visible.
    try:
        input("\nPress Enter to close...")
    except (EOFError, KeyboardInterrupt):
        pass


def double_click_setup() -> int:
    directory = Path(__file__).resolve().parent
    print("Set up text for translation\n", flush=True)
    try:
        source = nearby_original(directory)
        destination = directory / TRANSLATIONS_FILE
        if destination.exists():
            print("translations.json already exists. Your existing work has been kept.")
            print(f"File: {destination}")
            print("Continue translating that file, then double-click langpackage_import.py.")
            print("For a fresh export, move or rename translations.json and run this script again.")
            return 0
        print(f"Reading {source.name} and exporting the text...", flush=True)
        entries, _ = export_table(source, destination)
        print(f"\nReady: all {entries:,} entries in one JSON file.")
        print(f"Translate this file: {destination}")
        print("Translate only the string values under texts. Preserve the IDs.")
        print("Save the translated file as translations.json beside the scripts.")
        print("When ready, double-click langpackage_import.py to create the output file.")
        print(f"Keep {ORIGINAL_NAME} beside the scripts, untouched.")
        return 0
    except (OSError, ValueError) as exc:
        print(f"\nSetup could not finish: {exc}")
        return 1
    finally:
        wait_to_close()


def main() -> int:
    if len(sys.argv) == 1:
        return double_click_setup()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="Original LangPackageTableCnData.bytes (or another locale).")
    parser.add_argument("output", type=Path, help="New JSON output file; must not exist.")
    parser.add_argument("--chunk-size", type=int, help="Optional split export; output is then a new directory. Default: one JSON file.")
    args = parser.parse_args()
    try:
        entries, batches = export_table(args.source, args.output, args.chunk_size)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Exported {entries:,} entries to {batches:,} UTF-8 JSON file(s): {args.output.resolve()}")
    print("Translate only the string values under texts. Preserve the IDs.")
    print("Keep the original .bytes file; the importer requires it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

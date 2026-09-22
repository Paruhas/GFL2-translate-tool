#!/usr/bin/env python3
"""Rebuild a GFL2 LangPackage table from translated JSON.

Python 3.10+; standard library only. Keep langpackage_export.py alongside this
script. Supply a base .bytes file and the translated JSON. Translations match by
text ID. Rows without a translation keep their existing text; translation IDs
absent from the base table are skipped and counted.

Double-click this script after running langpackage_export.py and translating
translations.json beside the scripts. It reads the untouched original
beside the scripts and writes output/LangPackageTableCnData.bytes. Running it
again refreshes that output. Optional command-line use requires a new output file.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import struct
import sys
import tempfile

from langpackage_export import (
    ORIGINAL_NAME, TRANSLATIONS_FILE, Table, TableError, fields,
    load_table, nearby_original, varint, wait_to_close,
)


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise TableError(f"Duplicate JSON key {key!r}.")
        result[key] = value
    return result


def read_translations(path: Path) -> dict[int, str]:
    files = sorted(path.glob("*.json")) if path.is_dir() else [path]
    if not files:
        raise TableError("The translation directory contains no .json batches.")
    translations = {}
    for file in files:
        try:
            document = json.loads(file.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object)
            if not isinstance(document, dict):
                raise TableError("Expected a JSON object containing texts.")
            texts = document.get("texts")
            if not isinstance(texts, dict):
                raise TableError("The texts property must be an object mapping IDs to strings.")
            for key, text in texts.items():
                if not re.fullmatch(r"0|[1-9][0-9]{0,19}", key):
                    raise TableError(f"Malformed text ID {key!r}.")
                identity = int(key)
                if identity in translations:
                    raise TableError(f"Text ID {key} occurs in more than one batch.")
                if not isinstance(text, str):
                    raise TableError(f"Text ID {key} must contain a string (empty strings are allowed).")
                try:
                    text.encode("utf-8")
                except UnicodeEncodeError as exc:
                    raise TableError(f"Text ID {key} contains an invalid Unicode surrogate.") from exc
                translations[identity] = text
        except (ValueError, UnicodeError) as exc:
            raise TableError(f"{file.name}: {exc}") from exc
    return translations


def length_field(number: int, payload: bytes) -> bytes:
    return varint((number << 3) | 2) + varint(len(payload)) + payload


def replace_numbers(data: bytes, start: int, end: int, replacements: dict[int, int]) -> bytes:
    result, seen = [], set()
    for field in fields(data, start, end):
        if field.number in replacements:
            value = replacements[field.number]
            seen.add(field.number)
            # Preserve the original bytes when the value did not change.
            result.append(data[field.start:field.end] if value == field.value else varint(field.number << 3) + varint(value))
        else:
            result.append(data[field.start:field.end])
    for number, value in replacements.items():
        if number not in seen and value:
            result.append(varint(number << 3) + varint(value))
    return b"".join(result)


def rebuild(table: Table, translations: dict[int, str]) -> tuple[bytes, int]:
    data = table.data
    segments, offsets = [], {0: 0}
    position, changed = 0, 0
    for row in table.rows:
        outer = row.field
        text = translations.get(row.id, row.text)
        if text == row.text:
            segment = data[outer.start:outer.end]
        else:
            encoded = text.encode("utf-8")
            inner, replaced = [], False
            for field in fields(data, outer.payload, outer.end):
                if field.number == 2:
                    inner.append(length_field(2, encoded))
                    replaced = True
                else:
                    inner.append(data[field.start:field.end])
            if not replaced:
                inner.append(length_field(2, encoded))
            segment = length_field(1, b"".join(inner))
            changed += 1
        segments.append(segment)
        position += len(segment)
        offsets[outer.end - table.body_start] = position

    index_replacements = {}
    for index in table.indexes:
        start = offsets[index.offset]
        end = offsets[index.offset + index.length]
        if start == index.offset and end - start == index.length:
            continue
        value = index.value_field
        rewritten = replace_numbers(data, value.payload, value.end, {1: start, 2: end - start})
        inner = []
        for field in fields(data, index.field.payload, index.field.end):
            inner.append(length_field(2, rewritten) if field.start == value.start else data[field.start:field.end])
        index_replacements[index.field.start] = length_field(3, b"".join(inner))
    metadata = b"".join(index_replacements.get(f.start, data[f.start:f.end]) for f in table.metadata)
    if len(metadata) >= 1 << 32:
        raise TableError("Rebuilt index is too large for the four-byte header.")
    return struct.pack("<I", len(metadata)) + metadata + b"".join(segments), changed


def import_table(
    source: Path, translations: Path, output: Path,
    *, refresh_output: bool = False,
) -> tuple[int, int, int]:
    if source.resolve() == output.resolve() or (output.exists() and not refresh_output):
        raise TableError("Output must be a new file; the original and existing outputs are never overwritten.")
    table = load_table(source)
    edits = read_translations(translations)
    matched = sum(row.id in edits for row in table.rows)
    result, changed = rebuild(table, edits)
    output.parent.mkdir(parents=True, exist_ok=True)
    if refresh_output:
        # Finish writing before refreshing the generated output, retaining it if a write fails.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", dir=output.parent, prefix=".langpackage-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(result)
            os.replace(temporary, output)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    else:
        # Exclusive creation protects explicit CLI output paths from concurrent writes.
        with output.open("xb") as stream:
            stream.write(result)
    skipped = len(edits) - matched
    if skipped:
        print(f"Skipped {skipped:,} translation IDs absent from this table.")
    return len(table.rows), matched, changed


def double_click_import() -> int:
    directory = Path(__file__).resolve().parent
    print("Create the translated table\n", flush=True)
    try:
        source = nearby_original(directory)
        translations = directory / TRANSLATIONS_FILE
        if not translations.is_file():
            raise TableError("Run langpackage_export.py first, then translate translations.json beside the scripts.")
        output = directory / "output" / ORIGINAL_NAME
        print("Reading translations and rebuilding the table...", flush=True)
        total, supplied, changed = import_table(source, translations, output, refresh_output=True)
        print(f"\nReady: {output}")
        print(f"{changed:,} of {total:,} entries changed.")
        print("Your original file beside the scripts is untouched.")
        print("After more translation edits, run this script again to refresh the file in output.")
        return 0
    except (OSError, ValueError) as exc:
        print(f"\nNo output was created or refreshed: {exc}")
        return 1
    finally:
        wait_to_close()


def main() -> int:
    if len(sys.argv) == 1:
        return double_click_import()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="Base .bytes file; translations are matched by text ID.")
    parser.add_argument("translations", type=Path, help="One translated JSON batch, or a directory of batches.")
    parser.add_argument("output", type=Path, help="New .bytes output file; existing files are never overwritten.")
    args = parser.parse_args()
    try:
        total, supplied, changed = import_table(args.source, args.translations, args.output)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {args.output.resolve()}")
    print(f"{total:,} entries; {supplied:,} supplied; {changed:,} changed; {total - supplied:,} retained from unsupplied batches.")
    print("Rebuilt row lengths, index offsets, index lengths, and the table header.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

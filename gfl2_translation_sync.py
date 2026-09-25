#!/usr/bin/env python3
"""GFL2 Translation Memory & Sync Tool.

Maintains a persistent Chinese -> English translation memory database (SQLite).
When the game updates and table IDs shift:
1. Matches Chinese text directly to existing English translations (skipping re-translation).
2. Produces the updated `translations_eng.json` with the new IDs preserved.
3. Automatically detects any new or untranslated Chinese strings from the update.
4. Auto-translates new strings (or allows manual export/import) and permanently
   saves them to the database for future updates.

Works seamlessly with langpackage_export.py and langpackage_import.py.
Requires Python 3.10+; uses only the standard library (no pip install required).
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Regular expression to test if a string contains CJK characters
CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")

DEFAULT_DB_NAME = "translation_memory.db"
DEFAULT_CN_FILE = "translations.json"
DEFAULT_EN_FILE = "translations_eng.json"
DEFAULT_UNTRANSLATED_FILE = "untranslated.json"
FORMAT_NAME = "gfl2-langpackage-by-text-1"


def fingerprint(text: str) -> str:
    """Translation key for a text: first 16 hex chars (64 bits) of its UTF-8 SHA-256."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class TranslationMemory:
    """Manages the SQLite database for Chinese -> English translations."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS translations (
                    source_cn TEXT PRIMARY KEY,
                    target_en TEXT NOT NULL,
                    frequency INTEGER DEFAULT 1,
                    source_type TEXT DEFAULT 'matched',
                    updated_at TEXT,
                    is_verified INTEGER DEFAULT 1,
                    created_at TEXT,
                    fingerprint TEXT
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_source_cn ON translations (source_cn);")
            cols = [c[1] for c in conn.execute("PRAGMA table_info(translations);").fetchall()]
            if "is_verified" not in cols:
                conn.execute("ALTER TABLE translations ADD COLUMN is_verified INTEGER DEFAULT 1;")
            if "created_at" not in cols:
                conn.execute("ALTER TABLE translations ADD COLUMN created_at TEXT;")
                conn.execute("UPDATE translations SET created_at = COALESCE(updated_at, datetime('now')) WHERE created_at IS NULL;")
            if "fingerprint" not in cols:
                conn.execute("ALTER TABLE translations ADD COLUMN fingerprint TEXT;")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_is_verified ON translations (is_verified);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_translations_created_at ON translations (created_at);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_translations_fingerprint ON translations (fingerprint);")
            conn.commit()

    def count(self) -> int:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM translations;")
            row = cur.fetchone()
            return row[0] if row else 0

    def get_translation(self, text_cn: str) -> str | None:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT target_en FROM translations WHERE source_cn = ?;", (text_cn,))
            row = cur.fetchone()
            return row[0] if row else None

    def get_translation_by_fingerprint(self, fp: str) -> str | None:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT target_en FROM translations WHERE fingerprint = ?;", (fp,))
            row = cur.fetchone()
            return row[0] if row else None

    def get_all_dict(self) -> dict[str, str]:
        """Loads all translation pairs into memory for ultra-fast lookup (keyed by Chinese text)."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT source_cn, target_en FROM translations;")
            return dict(cur.fetchall())

    def get_all_by_fingerprint(self) -> dict[str, str]:
        """Loads all translation pairs into memory indexed by SHA-256 fingerprint."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT fingerprint, target_en FROM translations WHERE fingerprint IS NOT NULL;")
            return dict(cur.fetchall())

    def upsert_bulk(self, entries: list[tuple]) -> int:
        """Batch insert or update translations.

        entries format: list of (source_cn, target_en, frequency, source_type[, is_verified[, created_at]])
        """
        if not entries:
            return 0
        now_str = datetime.now().isoformat()
        formatted = []
        for item in entries:
            if len(item) >= 6:
                cn, en, freq, stype, verified, created = item[0], item[1], item[2], item[3], item[4], item[5]
            elif len(item) == 5:
                cn, en, freq, stype, verified = item[0], item[1], item[2], item[3], item[4]
                created = now_str
            elif len(item) == 4:
                cn, en, freq, stype = item
                verified = 1
                created = now_str
            else:
                cn, en = item[0], item[1]
                freq = item[2] if len(item) > 2 else 1
                stype = item[3] if len(item) > 3 else "matched"
                verified = 1
                created = now_str
            fp = fingerprint(cn)
            formatted.append((cn, en, freq, stype, now_str, verified, created, fp))

        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.executemany("""
                INSERT INTO translations (source_cn, target_en, frequency, source_type, updated_at, is_verified, created_at, fingerprint)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_cn) DO UPDATE SET
                    target_en = excluded.target_en,
                    frequency = translations.frequency + excluded.frequency,
                    source_type = excluded.source_type,
                    updated_at = excluded.updated_at,
                    is_verified = excluded.is_verified,
                    fingerprint = excluded.fingerprint
                WHERE excluded.source_type != 'auto' OR translations.source_type = 'auto';
            """, formatted)
            conn.commit()
            return len(entries)


# ==============================================================================
# Built-in Translation Service (Standard Library Google Translate)
# ==============================================================================

def translate_single_text(text: str, retries: int = 3, delay: float = 0.5) -> str:
    """Translates a single string from Simplified Chinese to English using Google Translate API."""
    if not text or not CJK_PATTERN.search(text):
        return text

    url = (
        "https://translate.googleapis.com/translate_a/single?client=gtx"
        "&sl=zh-CN&tl=en&dt=t&q=" + urllib.parse.quote(text)
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as response:
                raw_json = response.read().decode("utf-8")
                data = json.loads(raw_json)
                translated_parts = [part[0] for part in data[0] if part and part[0]]
                return "".join(translated_parts)
        except Exception as err:
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
            else:
                return text
    return text


def batch_auto_translate(
    texts: list[str], max_workers: int = 4, delay_between: float = 0.2, db: TranslationMemory | None = None
) -> dict[str, str]:
    """Translates a list of Chinese texts with multithreading and progress reporting."""
    results: dict[str, str] = {}
    total = len(texts)
    if total == 0:
        return results

    print(f"\nStarting auto-translation for {total:,} unique strings (workers={max_workers})...")
    completed = 0
    t_start = time.time()
    pending_db_entries: list[tuple[str, str, int, str]] = []

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_cn = {executor.submit(translate_single_text, cn): cn for cn in texts}
            for future in as_completed(future_to_cn):
                cn = future_to_cn[future]
                try:
                    en = future.result()
                    results[cn] = en
                    if en and en != cn:
                        pending_db_entries.append((cn, en, 1, "auto"))
                except Exception:
                    results[cn] = cn
                completed += 1

                # Periodically commit to database so progress is never lost
                if db and len(pending_db_entries) >= 25:
                    db.upsert_bulk(pending_db_entries)
                    pending_db_entries.clear()

                if completed % 10 == 0 or completed == total:
                    elapsed = time.time() - t_start
                    rate = completed / elapsed if elapsed > 0 else 0
                    print(f"  Progress: {completed:,}/{total:,} ({completed*100/total:.1f}%) - {rate:.1f} strings/sec", end="\r", flush=True)
    finally:
        # Save any remaining translations on completion or interrupt
        if db and pending_db_entries:
            db.upsert_bulk(pending_db_entries)
            pending_db_entries.clear()

    print(f"\nCompleted translation of {total:,} strings in {time.time() - t_start:.2f}s.")
    return results


# ==============================================================================
# Core Workflow Functions
# ==============================================================================

def build_database_from_tables(
    cn_path: Path, en_path: Path, db_path: Path
) -> int:
    """Extracts Chinese -> English translation pairs directly from matching .bytes tables by row ID."""
    print(f"\n--- Building Translation Database Directly from Tables ---")
    print(f"Chinese table : {cn_path}")
    print(f"English table : {en_path}")
    print(f"Target DB     : {db_path}")

    import langpackage_export
    table_cn = langpackage_export.load_table(cn_path)
    table_en = langpackage_export.load_table(en_path)

    en_by_id = {row.id: row.text for row in table_en.rows}
    counter_map: dict[str, Counter[str]] = defaultdict(Counter)
    conflicts = 0

    for row in table_cn.rows:
        cn = row.text
        if not cn:
            continue
        en = en_by_id.get(row.id, "")
        if not en:
            continue
        if CJK_PATTERN.search(cn) or (en != cn):
            counter_map[cn][en] += 1

    entries_to_save: list[tuple[str, str, int, str]] = []
    for cn, counts in counter_map.items():
        if len(counts) > 1:
            conflicts += 1
        best_en, freq = counts.most_common(1)[0]
        entries_to_save.append((cn, best_en, freq, "matched"))

    print(f"Extracted {len(entries_to_save):,} unique Chinese strings from tables.")
    if conflicts > 0:
        print(f"  Note: Resolved {conflicts:,} strings with multiple English variations (used most frequent translation).")

    db = TranslationMemory(db_path)
    print("Writing to database...")
    db.upsert_bulk(entries_to_save)
    total_db_entries = db.count()
    print(f"[Success] Database updated! Total stored translations in memory: {total_db_entries:,}.\n")
    return len(entries_to_save)


def build_database_from_files(
    cn_path: Path, en_path: Path, db_path: Path, update: bool = False
) -> int:
    """Extracts Chinese -> English translation pairs from baseline files (.bytes or .json) and stores in SQLite."""
    # If both inputs are binary .bytes files, extract directly from tables by row ID
    if cn_path.suffix.lower() == ".bytes" and en_path.suffix.lower() == ".bytes":
        return build_database_from_tables(cn_path, en_path, db_path)

    print(f"\n--- Building Translation Database ---")
    print(f"Chinese baseline : {cn_path}")
    print(f"English baseline : {en_path}")
    print(f"Target Database  : {db_path}")

    if not cn_path.is_file():
        raise FileNotFoundError(f"Chinese file not found: {cn_path}")
    if not en_path.is_file():
        raise FileNotFoundError(f"English file not found: {en_path}")

    print("Loading JSON files (this may take a few seconds for large tables)...")
    t0 = time.time()
    with cn_path.open("r", encoding="utf-8") as f:
        cn_doc = json.load(f)
        cn_texts = cn_doc.get("texts", cn_doc.get("translations", cn_doc))
    with en_path.open("r", encoding="utf-8") as f:
        en_doc = json.load(f)
        en_texts = en_doc.get("texts", en_doc.get("translations", en_doc))

    print(f"Loaded {len(cn_texts):,} CN entries and {len(en_texts):,} EN entries in {time.time() - t0:.2f}s.")

    # Match by key and collect frequency
    print("Analyzing string mappings and resolving variations...")
    counter_map: dict[str, Counter[str]] = defaultdict(Counter)
    conflicts = 0

    for key, cn in cn_texts.items():
        if not cn:
            continue
        en = en_texts.get(key, "")
        if not en:
            continue

        if CJK_PATTERN.search(cn) or (en != cn):
            counter_map[cn][en] += 1

    entries_to_save: list[tuple[str, str, int, str]] = []
    for cn, counts in counter_map.items():
        if len(counts) > 1:
            conflicts += 1
        best_en, freq = counts.most_common(1)[0]
        entries_to_save.append((cn, best_en, freq, "matched"))

    print(f"Extracted {len(entries_to_save):,} unique Chinese strings.")
    if conflicts > 0:
        print(f"  Note: Resolved {conflicts:,} strings with multiple English variations (used most frequent translation).")

    db = TranslationMemory(db_path)
    print("Writing to database...")
    db.upsert_bulk(entries_to_save)
    total_db_entries = db.count()
    print(f"[Success] Database updated! Total stored translations in memory: {total_db_entries:,}.\n")
    return len(entries_to_save)


def sync_and_translate(
    new_cn_path: Path,
    output_en_path: Path,
    untranslated_path: Path,
    db_path: Path,
    auto_translate_new: bool = False,
    workers: int = 4,
) -> tuple[int, int, int]:
    """Takes a new translations.json (from an update), applies known translations,

    and handles untranslated text.
    """
    print(f"\n--- Synchronizing Game Update Translations ---")
    print(f"New Update CN file  : {new_cn_path}")
    print(f"Output EN file       : {output_en_path}")
    print(f"Untranslated output  : {untranslated_path}")
    print(f"Database             : {db_path}")

    if not new_cn_path.is_file():
        raise FileNotFoundError(f"Input Chinese JSON not found: {new_cn_path}")

    db = TranslationMemory(db_path)
    total_db = db.count()
    if total_db == 0:
        raise ValueError(
            f"Translation database is empty ({db_path})!\n"
            f"Run 'build' first using your baseline translations.json and translations_eng.json."
        )

    print(f"Loading translation memory ({total_db:,} phrases)...")
    t0 = time.time()
    memory = db.get_all_dict()
    print(f"Loaded memory in {time.time() - t0:.2f}s.")

    print(f"Reading new update file: {new_cn_path.name}...")
    with new_cn_path.open("r", encoding="utf-8-sig") as f:
        doc = json.load(f)

    is_untranslated_file = False
    if "texts" in doc and isinstance(doc["texts"], dict):
        texts_dict = doc["texts"]
    elif "translations" in doc and isinstance(doc["translations"], dict):
        is_untranslated_file = True
        # Passed an untranslated.json or chunk file directly!
        texts_dict = {cn: cn for cn in doc["translations"].keys() if not cn.startswith("_")}
    elif isinstance(doc, dict):
        texts_dict = {k: (v if isinstance(v, str) and v else k) for k, v in doc.items() if not k.startswith("_")}
    else:
        raise ValueError(f"Unrecognized format in {new_cn_path.name}")

    total_keys = len(texts_dict)
    matched_count = 0
    identical_count = 0
    untranslated_unique: set[str] = set()
    untranslated_id_map: dict[str, str] = {}
    new_en_texts: dict[str, str] = {}

    print(f"Matching {total_keys:,} rows against translation memory...")
    for key, cn_text in texts_dict.items():
        if not cn_text:
            new_en_texts[key] = ""
            continue

        # Check if text exists in translation memory
        if cn_text in memory:
            new_en_texts[key] = memory[cn_text]
            matched_count += 1
        elif not CJK_PATTERN.search(cn_text):
            # No Chinese characters (e.g. pure numbers, codes like "3-1", "test", tags)
            new_en_texts[key] = cn_text
            identical_count += 1
        else:
            # Contains Chinese, not yet in memory -> Needs translation!
            untranslated_unique.add(cn_text)
            untranslated_id_map[key] = cn_text
            new_en_texts[key] = cn_text  # Temporary fallback to Chinese until translated

    untranslated_count = len(untranslated_id_map)
    unique_untranslated_count = len(untranslated_unique)
    match_pct = (matched_count * 100 / total_keys) if total_keys > 0 else 0.0

    print("\n--- Synchronization Summary ---")
    print(f"Total Rows in Update File : {total_keys:,}")
    print(f"Matched from Memory       : {matched_count:,} ({match_pct:.2f}%)")
    print(f"Non-Chinese (Kept As-Is)  : {identical_count:,}")
    print(f"New / Untranslated Rows   : {untranslated_count:,} ({unique_untranslated_count:,} unique strings)")

    # Auto-translate if requested
    translated_map: dict[str, str] = {}
    if untranslated_unique and auto_translate_new:
        print(f"\n[Auto-Translate] Translating {unique_untranslated_count:,} new unique Chinese strings...")
        translated_map = batch_auto_translate(list(untranslated_unique), max_workers=workers, db=db)

        # Apply newly translated strings to new_en_texts
        for key, cn_text in untranslated_id_map.items():
            if cn_text in translated_map:
                new_en_texts[key] = translated_map[cn_text]
                matched_count += 1
                untranslated_count -= 1

        print(f"[Auto-Translate] All new strings translated and applied!")

    # Write translated output file
    output_en_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"\nWriting translated file to: {output_en_path}...")
    if is_untranslated_file:
        out_doc = {
            "translations": {cn: (translated_map.get(cn) or memory.get(cn) or "") for cn in texts_dict.keys()}
        }
    else:
        out_doc = {
            "format": FORMAT_NAME,
            "texts": new_en_texts
        }

    with output_en_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(out_doc, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # If an untranslated file was translated, also update output/translations_eng.json in place if it exists
    std_eng_path = output_en_path.parent / "translations_eng.json"
    if is_untranslated_file and translated_map and std_eng_path.is_file():
        print(f"Also updating {std_eng_path.name} with newly translated strings...")
        try:
            with std_eng_path.open("r", encoding="utf-8") as f:
                std_doc = json.load(f)
            std_texts = std_doc.get("texts", {})
            updated_count = 0
            for k, v in std_texts.items():
                if v in translated_map:
                    std_texts[k] = translated_map[v]
                    updated_count += 1
            if "format" not in std_doc:
                std_doc["format"] = FORMAT_NAME
            with std_eng_path.open("w", encoding="utf-8", newline="\n") as f:
                json.dump(std_doc, f, ensure_ascii=False, indent=2)
                f.write("\n")
            print(f"[Success] Updated {updated_count:,} occurrences in {std_eng_path.name}!")
        except Exception as e:
            print(f"  [Warning] Could not update {std_eng_path.name}: {e}")

    # If untranslated strings still remain, export them
    if untranslated_count > 0 and not auto_translate_new:
        untranslated_path.parent.mkdir(parents=True, exist_ok=True)
        sorted_untranslated = sorted(untranslated_unique)

        # 1. Main single untranslated file
        untranslated_doc = {
            "_info": "Translate the English values for each Chinese string, then run 'import-translated'.",
            "translations": {cn: "" for cn in sorted_untranslated}
        }
        with untranslated_path.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(untranslated_doc, f, ensure_ascii=False, indent=2)
            f.write("\n")

        # 2. Bite-sized chunks for ChatGPT / Claude (e.g. 250 items per chunk)
        chunk_size = 250
        chunks_dir = untranslated_path.parent / "untranslated_chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)
        num_chunks = (len(sorted_untranslated) + chunk_size - 1) // chunk_size

        for i in range(num_chunks):
            batch = sorted_untranslated[i * chunk_size : (i + 1) * chunk_size]
            chunk_file = chunks_dir / f"chunk_{i + 1:03d}.json"
            chunk_content = {
                "_prompt": (
                    "Translate the Chinese string values to English for the game Girls' Frontline 2. "
                    "Keep Chinese keys unchanged. Keep tags like {0} and <color=...> unchanged. "
                    "Return valid JSON only."
                ),
                "translations": {cn: "" for cn in batch}
            }
            with chunk_file.open("w", encoding="utf-8", newline="\n") as f:
                json.dump(chunk_content, f, ensure_ascii=False, indent=2)
                f.write("\n")

        print(f"\n[Notice] Saved {unique_untranslated_count:,} untranslated strings to:")
        print(f"  - Full file : {untranslated_path}")
        print(f"  - Chunks    : {chunks_dir} ({num_chunks} files of ~{chunk_size} lines each for ChatGPT)")
        print(f"  Paste chunks into ChatGPT/Claude, save them, then run Option 4 to import!")

    print(f"\n[Success] Updated {output_en_path.name} is ready for langpackage_import.py!")
    return total_keys, matched_count, untranslated_count


def load_json_tolerant(path: Path) -> dict:
    """Reads a JSON file, automatically stripping any markdown ```json ... ``` wrappers."""
    raw = path.read_text(encoding="utf-8-sig").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        raw = raw.strip()
    return json.loads(raw)


def import_translated_file(
    translated_input: Path,
    db_path: Path,
    target_en_json: Path | None = None,
    apply_glossary_rules: bool = True,
) -> int:
    """Imports an external or manually translated JSON file or folder of files into the database
    and updates translations_eng.json in place.
    
    Applies Lore Glossary rules to newly imported strings before saving to database.
    Supports both Chinese-keyed and SHA-256 fingerprint-keyed JSON files (Discord community format).
    """
    print(f"\n--- Importing Translations ---")
    print(f"Source   : {translated_input}")
    print(f"Database : {db_path}")

    files: list[Path] = []
    if translated_input.is_dir():
        files = sorted(translated_input.glob("*.json"))
        if not files:
            print(f"No .json files found in directory: {translated_input}")
            return 0
        print(f"Found {len(files)} JSON file(s) in directory.")
    elif translated_input.is_file():
        files = [translated_input]
    else:
        raise FileNotFoundError(f"Input path not found: {translated_input}")

    raw_pairs: list[tuple[str, str]] = []
    seen_cn: set[str] = set()

    for fpath in files:
        try:
            data = load_json_tolerant(fpath)
        except Exception as e:
            print(f"  [Warning] Could not parse {fpath.name}: {e}")
            continue

        target_dict = {}
        if isinstance(data, dict):
            if "translations" in data and isinstance(data["translations"], dict):
                target_dict = data["translations"]
            elif "texts" in data and isinstance(data["texts"], dict):
                target_dict = data["texts"]
            else:
                target_dict = data

        # Check if keys are 16-hex fingerprints (from Discord community format)
        fp_keys = [str(k) for k in target_dict.keys() if re.fullmatch(r"[0-9a-f]{16}", str(k))]
        fp_to_cn = {}
        if fp_keys:
            with sqlite3.connect(db_path) as conn:
                cur = conn.cursor()
                for i in range(0, len(fp_keys), 900):
                    batch_fps = fp_keys[i:i+900]
                    placeholders = ",".join("?" * len(batch_fps))
                    cur.execute(f"SELECT fingerprint, source_cn FROM translations WHERE fingerprint IN ({placeholders});", batch_fps)
                    for fp, cn in cur.fetchall():
                        fp_to_cn[fp] = cn

        for key, en in target_dict.items():
            if str(key).startswith("_"):  # Skip prompt or info keys
                continue
            cn = fp_to_cn.get(str(key), key)
            if isinstance(en, str) and cn and en.strip() and cn != en:
                if cn not in seen_cn:
                    raw_pairs.append((cn, en.strip()))
                    seen_cn.add(cn)

    if not raw_pairs:
        print("No valid translated pairs found (English values must not be empty or identical to Chinese).")
        return 0

    # Apply Lore Glossary rules at ingestion gate
    rules = []
    if apply_glossary_rules:
        try:
            import apply_glossary as ag
            rules = ag.load_active_rules(db_path)
        except Exception as exc:
            print(f"  [Warning] Could not load lore glossary rules: {exc}")

    glossary_fixes = 0
    pairs: list[tuple[str, str, int, str, int]] = []
    for cn, en in raw_pairs:
        clean_en = en
        if rules:
            try:
                import apply_glossary as ag
                clean_en, applied = ag.apply_glossary_to_text(en, cn, rules)
                if applied:
                    glossary_fixes += len(applied)
            except Exception:
                pass
        pairs.append((cn, clean_en, 1, "manual", 1))  # is_verified = 1

    if glossary_fixes > 0:
        print(f"✓ [Lore Glossary] Auto-corrected {glossary_fixes} terms according to canon lore.")

    db = TranslationMemory(db_path)
    db.upsert_bulk(pairs)
    print(f"[Success] Imported {len(pairs):,} unique verified translations into {db_path.name}.")

    if target_en_json and target_en_json.is_file():
        print(f"Updating {target_en_json.name} with newly imported translations...")
        mapping = {cn: en for cn, en, _, _, _ in pairs}
        with target_en_json.open("r", encoding="utf-8") as f:
            en_doc = json.load(f)
        texts = en_doc.get("texts", {})

        cn_file = target_en_json.parent / "translations.json"
        cn_lookup = {}
        if cn_file.exists():
            try:
                with cn_file.open("r", encoding="utf-8") as cf:
                    cn_data = json.load(cf)
                    cn_lookup = cn_data.get("texts", cn_data.get("translations", cn_data))
            except Exception:
                pass

        updated = 0
        for k, v in texts.items():
            cn_src = cn_lookup.get(k, v)
            if cn_src in mapping:
                texts[k] = mapping[cn_src]
                updated += 1
            elif v in mapping:
                texts[k] = mapping[v]
                updated += 1
        if "format" not in en_doc:
            en_doc["format"] = FORMAT_NAME
        with target_en_json.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(en_doc, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"[Success] Updated {updated:,} row occurrences in {target_en_json.name}.")

    return len(pairs)


def export_database_to_file(db_path: Path, output_file: Path) -> int:
    """Exports all stored translation pairs from the SQLite DB to a clean JSON or TSV file."""
    db = TranslationMemory(db_path)
    all_dict = db.get_all_dict()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if output_file.suffix.lower() == ".tsv":
        with output_file.open("w", encoding="utf-8", newline="\n") as f:
            f.write("Chinese\tEnglish\n")
            for cn, en in sorted(all_dict.items()):
                f.write(f"{cn}\t{en}\n")
    else:
        with output_file.open("w", encoding="utf-8", newline="\n") as f:
            json.dump({"translations": all_dict}, f, ensure_ascii=False, indent=2)
            f.write("\n")

    print(f"[Success] Exported {len(all_dict):,} translations to: {output_file}")
    return len(all_dict)


# ==============================================================================
# Interactive Terminal Menu Mode
# ==============================================================================

def interactive_menu():
    """Interactive menu displayed when run without command line arguments."""
    base_dir = Path(__file__).resolve().parent
    default_db = base_dir / DEFAULT_DB_NAME

    # Output folder for generated translations and chunks
    output_dir = base_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    default_cn = output_dir / DEFAULT_CN_FILE
    default_en = output_dir / DEFAULT_EN_FILE
    default_untranslated = output_dir / DEFAULT_UNTRANSLATED_FILE

    while True:
        db = TranslationMemory(default_db)
        count = db.count()

        print("\n" + "=" * 65)
        print("         GFL2 TRANSLATION MEMORY & UPDATE SYNC TOOL")
        print("=" * 65)
        print(f" Database : {default_db.name} (Stored Translations: {count:,})")
        print("=" * 65)
        print("  1. Build / Seed Database from existing translations (CN + EN)")
        print("  2. Sync New Update (Match old translations & generate translations_eng.json)")
        print("  3. Auto-Translate new strings directly with Google Translate")
        print("  4. Import translated file into database")
        print("  5. Export database to JSON / TSV")
        print("  6. Show database statistics")
        print("  7. Exit")
        print("=" * 65)

        choice = input("Select an option (1-7): ").strip()

        if choice == "1":
            print("\n[Option 1: Build Database from CN + EN files]")
            cn_in = input(f"Path to Chinese JSON [{default_cn}]: ").strip() or str(default_cn)
            en_in = input(f"Path to English JSON [{default_en}]: ").strip() or str(default_en)
            try:
                build_database_from_files(Path(cn_in), Path(en_in), default_db)
            except Exception as e:
                print(f"Error: {e}")

        elif choice == "2":
            print("\n[Option 2: Sync New Update]")
            cn_in = input(f"Path to new update Chinese JSON [{default_cn}]: ").strip() or str(default_cn)
            out_en = input(f"Output English JSON [{default_en}]: ").strip() or str(default_en)
            try:
                sync_and_translate(Path(cn_in), Path(out_en), default_untranslated, default_db, auto_translate_new=False)
            except Exception as e:
                print(f"Error: {e}")

        elif choice == "3":
            print("\n[Option 3: Sync & Auto-Translate New Strings]")
            cn_in = input(f"Path to new update Chinese JSON [{default_cn}]: ").strip() or str(default_cn)
            out_en = input(f"Output English JSON [{default_en}]: ").strip() or str(default_en)
            try:
                sync_and_translate(Path(cn_in), Path(out_en), default_untranslated, default_db, auto_translate_new=True)
            except Exception as e:
                print(f"Error: {e}")

        elif choice == "4":
            print("\n[Option 4: Import Translations into Database]")
            imp_default = output_dir / "untranslated_chunks"
            imp_path = input(f"Path to translated JSON or folder [{imp_default}]: ").strip() or str(imp_default)
            if imp_path:
                try:
                    import_translated_file(Path(imp_path), default_db, Path(default_en) if default_en.exists() else None)
                except Exception as e:
                    print(f"Error: {e}")

        elif choice == "5":
            print("\n[Option 5: Export Database]")
            exp_path = input(f"Export filename [{base_dir / 'translations_memory_export.json'}]: ").strip() or str(base_dir / "translations_memory_export.json")
            try:
                export_database_to_file(default_db, Path(exp_path))
            except Exception as e:
                print(f"Error: {e}")

        elif choice == "6":
            print(f"\nDatabase Location: {default_db.resolve()}")
            print(f"Total Unique Translations: {count:,}")
            if default_db.exists():
                size_mb = default_db.stat().st_size / (1024 * 1024)
                print(f"Database File Size: {size_mb:.2f} MB")

        elif choice == "7":
            print("Goodbye!")
            break
        else:
            print("Invalid selection. Please enter 1-7.")

    try:
        input("\nPress Enter to close...")
    except (EOFError, KeyboardInterrupt):
        pass


# ==============================================================================
# Command Line Interface (CLI)
# ==============================================================================

def main():
    if len(sys.argv) == 1:
        return interactive_menu()

    parser = argparse.ArgumentParser(
        description="GFL2 Translation Memory & Sync Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: build
    p_build = subparsers.add_parser("build", help="Build/seed the database from existing CN and EN JSON files.")
    p_build.add_argument("--cn", type=Path, required=True, help="Baseline Chinese translations.json")
    p_build.add_argument("--en", type=Path, required=True, help="Baseline English translations_eng.json")
    p_build.add_argument("--db", type=Path, default=Path(DEFAULT_DB_NAME), help="Database file path")

    # Subcommand: sync
    p_sync = subparsers.add_parser("sync", help="Apply translation memory to a newly updated Chinese JSON file.")
    p_sync.add_argument("--input", type=Path, required=True, help="New update Chinese translations.json")
    p_sync.add_argument("--output", type=Path, default=Path("output/translations_eng.json"), help="Output translated translations_eng.json (default: output/translations_eng.json)")
    p_sync.add_argument("--untranslated", type=Path, default=Path("output/untranslated.json"), help="Output for untranslated texts (default: output/untranslated.json)")
    p_sync.add_argument("--db", type=Path, default=Path(DEFAULT_DB_NAME), help="Database file path")
    p_sync.add_argument("--auto-translate", action="store_true", help="Automatically translate new strings with Google Translate")
    p_sync.add_argument("--workers", type=int, default=4, help="Number of translation worker threads")

    # Subcommand: import
    p_import = subparsers.add_parser("import", help="Import a translated JSON/TSV into the database.")
    p_import.add_argument("file", type=Path, default=Path("output/untranslated_chunks"), nargs="?", help="Path to JSON or folder with translations (default: output/untranslated_chunks)")
    p_import.add_argument("--db", type=Path, default=Path(DEFAULT_DB_NAME), help="Database file path")
    p_import.add_argument("--target-json", type=Path, default=Path("output/translations_eng.json"), help="Optional translations_eng.json to update in place (default: output/translations_eng.json)")

    # Subcommand: export
    p_export = subparsers.add_parser("export", help="Export database to JSON or TSV.")
    p_export.add_argument("output", type=Path, help="Output JSON or TSV file")
    p_export.add_argument("--db", type=Path, default=Path(DEFAULT_DB_NAME), help="Database file path")

    # Subcommand: stats
    p_stats = subparsers.add_parser("stats", help="Show database statistics.")
    p_stats.add_argument("--db", type=Path, default=Path(DEFAULT_DB_NAME), help="Database file path")

    args = parser.parse_args()

    try:
        if args.command == "build":
            build_database_from_files(args.cn, args.en, args.db)
        elif args.command == "sync":
            sync_and_translate(args.input, args.output, args.untranslated, args.db, args.auto_translate, args.workers)
        elif args.command == "import":
            import_translated_file(args.file, args.db, args.target_json)
        elif args.command == "export":
            export_database_to_file(args.db, args.output)
        elif args.command == "stats":
            db = TranslationMemory(args.db)
            print(f"Database: {args.db.resolve()}")
            print(f"Total entries: {db.count():,}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

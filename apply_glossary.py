#!/usr/bin/env python3
"""GFL2 Lore Glossary Manager & Auto-Fixer.

Operates DIRECTLY on the SQLite database (translation_memory.db).
- Reads official terms and bad machine translations from table 'glossary'.
- Audits and fixes mistranslations in translation_memory.db and output/translations_eng.json.
- Allows viewing, adding, exporting, and importing glossary terms.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sqlite3
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


DEFAULT_DB = Path(__file__).resolve().parent / "translation_memory.db"
DEFAULT_CN = Path(__file__).resolve().parent / "output" / "translations.json"
DEFAULT_EN = Path(__file__).resolve().parent / "output" / "translations_eng.json"
DEFAULT_GLOSSARY_JSON = Path(__file__).resolve().parent / "database_source" / "glossary.json"


def get_connection(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS glossary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_cn TEXT UNIQUE NOT NULL,
            target_en TEXT NOT NULL,
            bad_translations TEXT DEFAULT '[]',
            exclusions TEXT DEFAULT '[]',
            category TEXT DEFAULT 'General',
            speaker_context TEXT,
            notes TEXT,
            updated_at TEXT,
            created_at TEXT
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_glossary_source_cn ON glossary (source_cn);")
    cols = [c[1] for c in conn.execute("PRAGMA table_info(glossary);").fetchall()]
    if "created_at" not in cols:
        conn.execute("ALTER TABLE glossary ADD COLUMN created_at TEXT;")
        conn.execute("UPDATE glossary SET created_at = COALESCE(updated_at, datetime('now')) WHERE created_at IS NULL;")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_glossary_created_at ON glossary (created_at);")
    conn.commit()

    # If glossary table is empty, auto-import from database_source/glossary.json
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM glossary;")
    if cur.fetchone()[0] == 0:
        json_file = db_path.parent / "database_source" / "glossary.json"
        if not json_file.exists():
            json_file = db_path.parent / "glossary.json"
        if json_file.exists():
            try:
                with json_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                items = data.get("glossary", data if isinstance(data, list) else [])
                now_str = datetime.now().isoformat()
                for item in items:
                    if "source_cn" in item and "target_en" in item:
                        b_json = json.dumps(item.get("bad_translations", []), ensure_ascii=False)
                        e_json = json.dumps(item.get("exclusions", []), ensure_ascii=False)
                        c_at = item.get("created_at", now_str)
                        u_at = item.get("updated_at", now_str)
                        cur.execute("""
                            INSERT OR IGNORE INTO glossary (source_cn, target_en, bad_translations, exclusions, category, speaker_context, notes, updated_at, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """, (
                            item["source_cn"],
                            item["target_en"],
                            b_json,
                            e_json,
                            item.get("category", "General"),
                            item.get("speaker_context"),
                            item.get("notes"),
                            u_at,
                            c_at
                        ))
                conn.commit()
            except Exception:
                pass
    return conn




def safe_replace_term(text: str, bad_term: str, en_term: str) -> str:
    """Safely replaces a bad translation term with en_term using hyphen-aware boundaries and idempotency checks."""
    if not bad_term or not text or bad_term.lower() == en_term.lower():
        return text

    flags = re.IGNORECASE if bad_term.islower() else 0
    # Hyphen-safe boundary (?<![\w\-]) and (?![\w\-]) ensures no match inside T-Doll, A-Doll, etc.
    pattern = re.compile(rf"(?<![\w\-]){re.escape(bad_term)}(?![\w\-])", flags)

    # Protect existing occurrences of en_term so sub-terms are not replaced inside already-correct terms
    en_pattern = re.compile(rf"(?<![\w\-]){re.escape(en_term)}(?![\w\-])", flags)
    protected_spans = [m.span() for m in en_pattern.finditer(text)]

    def repl(m: re.Match) -> str:
        m_start, m_end = m.span()
        for p_start, p_end in protected_spans:
            if p_start <= m_start and m_end <= p_end:
                return m.group(0)
        return en_term

    return pattern.sub(repl, text)


def list_terms(db_path: Path, category: str | None = None) -> None:
    """Lists all terms stored in the database glossary table."""
    with get_connection(db_path) as conn:
        cur = conn.cursor()
        query = "SELECT id, source_cn, target_en, bad_translations, exclusions, category, speaker_context, notes FROM glossary"
        params = []
        if category:
            query += " WHERE category = ?"
            params.append(category)
        query += " ORDER BY category, source_cn;"

        rows = cur.execute(query, params).fetchall()
        if not rows:
            print("No glossary terms found in database.")
            return

        print("\n" + "=" * 90)
        print(f"{'CN TERM':<18} | {'OFFICIAL EN':<20} | {'CATEGORY':<15} | {'FORBIDDEN / BAD TRANSLATIONS'}")
        print("=" * 90)
        for r in rows:
            _, cn, en, bad_json, _, cat, ctx, _ = r
            bads = json.loads(bad_json) if bad_json else []
            bad_str = ", ".join(bads) if bads else "(none)"
            ctx_str = f" [{ctx}]" if ctx and ctx != "Any" else ""
            print(f"{cn:<18} | {en + ctx_str:<20} | {cat:<15} | {bad_str}")
        print("=" * 90)
        print(f"Total Terms in Database: {len(rows)}\n")


def add_term(
    db_path: Path,
    source_cn: str,
    target_en: str,
    bad_translations: list[str] | None = None,
    exclusions: list[str] | None = None,
    category: str = "General",
    speaker_context: str | None = None,
    notes: str | None = None,
    created_at: str | None = None,
) -> None:
    """Inserts or updates a term in the database glossary table."""
    now_str = datetime.now().isoformat()
    created_str = created_at or now_str
    b_json = json.dumps(bad_translations or [], ensure_ascii=False)
    e_json = json.dumps(exclusions or [], ensure_ascii=False)
    with get_connection(db_path) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO glossary (source_cn, target_en, bad_translations, exclusions, category, speaker_context, notes, updated_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_cn) DO UPDATE SET
                target_en = excluded.target_en,
                bad_translations = excluded.bad_translations,
                exclusions = excluded.exclusions,
                category = excluded.category,
                speaker_context = excluded.speaker_context,
                notes = excluded.notes,
                updated_at = excluded.updated_at;
        """, (source_cn.strip(), target_en.strip(), b_json, e_json, category.strip(), speaker_context, notes, now_str, created_str))
        conn.commit()
    print(f"[Success] Saved to database: {source_cn} -> {target_en}")


def export_terms(db_path: Path, export_path: Path) -> None:
    """Exports glossary table from database to a human-readable JSON file."""
    with get_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        rows = cur.execute("SELECT * FROM glossary ORDER BY category, source_cn;").fetchall()
        entries = []
        for r in rows:
            entries.append({
                "source_cn": r["source_cn"],
                "target_en": r["target_en"],
                "bad_translations": json.loads(r["bad_translations"]) if r["bad_translations"] else [],
                "exclusions": json.loads(r["exclusions"]) if r["exclusions"] else [],
                "category": r["category"],
                "speaker_context": r["speaker_context"],
                "notes": r["notes"],
                "created_at": r["created_at"] if "created_at" in r.keys() else None,
                "updated_at": r["updated_at"] if "updated_at" in r.keys() else None,
            })

    export_path.parent.mkdir(parents=True, exist_ok=True)
    with export_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump({"total_terms": len(entries), "glossary": entries}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[Success] Exported {len(entries)} glossary terms from DB to {export_path}")


def import_terms(db_path: Path, import_path: Path) -> None:
    """Imports glossary terms from a JSON file into the database glossary table."""
    with import_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("glossary", data if isinstance(data, list) else [])
    count = 0
    for item in items:
        if "source_cn" in item and "target_en" in item:
            add_term(
                db_path=db_path,
                source_cn=item["source_cn"],
                target_en=item["target_en"],
                bad_translations=item.get("bad_translations"),
                exclusions=item.get("exclusions"),
                category=item.get("category", "General"),
                speaker_context=item.get("speaker_context"),
                notes=item.get("notes"),
                created_at=item.get("created_at"),
            )
            count += 1
    print(f"[Success] Imported {count} terms into database from {import_path}")


def load_active_rules(db_path: Path) -> list[dict]:
    """Loads active replacement rules from the database glossary table."""
    with get_connection(db_path) as conn:
        cur = conn.cursor()
        rows = cur.execute("SELECT source_cn, target_en, bad_translations, exclusions FROM glossary;").fetchall()

    rules = []
    for r in rows:
        cn_term, en_term, bad_json, exc_json = r
        bads = json.loads(bad_json) if bad_json else []
        excs = json.loads(exc_json) if exc_json else []
        # Filter out self-replacements
        bads = [b for b in bads if b.lower() != en_term.lower()]
        if bads:
            rules.append({
                "source_cn": cn_term,
                "target_en": en_term,
                "bad_translations": sorted(bads, key=len, reverse=True),
                "exclusions": excs,
            })
    return rules


def apply_glossary_to_text(en_text: str, cn_text: str, rules: list[dict]) -> tuple[str, list[str]]:
    """Applies glossary rules to a single (en_text, cn_text) pair.

    Returns (modified_en_text, list_of_applied_rule_descriptions).
    """
    if not en_text or not cn_text:
        return en_text, []

    modified = en_text
    applied = []
    for r in rules:
        cn_term = r["source_cn"]
        en_term = r["target_en"]
        bads = r["bad_translations"]
        excs = r["exclusions"]

        if cn_term not in cn_text or any(exc in cn_text for exc in excs):
            continue

        prev = modified
        for b in bads:
            modified = safe_replace_term(modified, b, en_term)
        if modified != prev:
            applied.append(f"{cn_term} -> {en_term}")

    return modified, applied


def audit_and_fix(
    db_path: Path,
    target_en_path: Path | None = None,
    base_cn_path: Path | None = None,
    dry_run: bool = False,
    audit_db: bool = True,
    only_unverified: bool = True,
) -> dict:
    """Audits and fixes translations in DB and JSON using rules loaded from the database.

    - audit_db: If False, skips database mutations completely (JSON-only mode).
    - only_unverified: If True, only inspects and updates rows where is_verified = 0.
    """
    print("\n--- Auditing Translations with Database Glossary ---")
    if audit_db:
        mode_str = "Unverified rows only" if only_unverified else "ALL rows in database"
        print(f"Database : {db_path.resolve()} ({mode_str})")
    else:
        print(f"Database : {db_path.resolve()} (READ-ONLY / SKIPPED)")
    if target_en_path:
        print(f"JSON Target : {target_en_path.resolve()}")
    if dry_run:
        print("[DRY RUN MODE] No changes will be written.\n")

    # 1. Load rules from glossary table
    rules = load_active_rules(db_path)
    print(f"Loaded {len(rules)} active replacement rules from database glossary table.\n")

    # 2. Audit and fix SQLite translations table
    db_report = {}
    if audit_db:
        with get_connection(db_path) as conn:
            cur = conn.cursor()
            for r in rules:
                cn_term = r["source_cn"]
                en_term = r["target_en"]
                bads = r["bad_translations"]
                excs = r["exclusions"]

                query = "SELECT source_cn, target_en FROM translations WHERE source_cn LIKE ?"
                if only_unverified:
                    query += " AND (is_verified = 0 OR is_verified IS NULL)"
                cur.execute(query + ";", (f"%{cn_term}%",))
                db_rows = cur.fetchall()
                updates = []
            for cn, en in db_rows:
                if any(exc in cn for exc in excs):
                    continue
                modified = en
                for b in bads:
                    modified = safe_replace_term(modified, b, en_term)
                if modified != en:
                    updates.append((modified, datetime.now().isoformat(), cn))

            if updates:
                db_report[f"{cn_term} -> {en_term}"] = len(updates)
                if not dry_run:
                    cur.executemany(
                        "UPDATE translations SET target_en = ?, updated_at = ?, is_verified = 1 WHERE source_cn = ?;",
                        updates,
                    )
                    conn.commit()

    # 3. Audit and fix translations_eng.json if provided
    json_report = {}
    if target_en_path and target_en_path.exists():
        print(f"Scanning {target_en_path.name}...")
        with target_en_path.open("r", encoding="utf-8") as f:
            en_data = json.load(f)

        en_texts = en_data.get("texts", en_data.get("translations", en_data))
        cn_texts = {}
        if base_cn_path and base_cn_path.exists():
            with base_cn_path.open("r", encoding="utf-8") as f:
                cn_obj = json.load(f)
                cn_texts = cn_obj.get("texts", cn_obj.get("translations", cn_obj))

        json_modified = False
        for r in rules:
            cn_term = r["source_cn"]
            en_term = r["target_en"]
            bads = r["bad_translations"]
            excs = r["exclusions"]

            count = 0
            for k, en_val in en_texts.items():
                if cn_texts:
                    cn_val = cn_texts.get(k, "")
                    if cn_term not in cn_val or any(exc in cn_val for exc in excs):
                        continue
                else:
                    if cn_term not in k or any(exc in k for exc in excs):
                        continue

                modified = en_val
                for b in bads:
                    modified = safe_replace_term(modified, b, en_term)
                if modified != en_val:
                    en_texts[k] = modified
                    count += 1
                    json_modified = True

            if count > 0:
                json_report[f"{cn_term} -> {en_term}"] = count

        if not dry_run and json_modified:
            with target_en_path.open("w", encoding="utf-8", newline="\n") as f:
                json.dump(en_data, f, ensure_ascii=False, indent=2)
                f.write("\n")
            print(f"[Success] Saved updated translations to {target_en_path}")

    # Summary Display
    print("\n" + "=" * 65)
    print("                GLOSSARY AUDIT & FIX REPORT")
    print("=" * 65)
    all_keys = set(db_report.keys()) | set(json_report.keys())
    if not all_keys:
        print("All translations are already 100% compliant with the glossary!")
    else:
        for k in sorted(all_keys):
            db_cnt = db_report.get(k, 0)
            js_cnt = json_report.get(k, 0)
            print(f"- {k:<30} : {db_cnt} DB entries fixed, {js_cnt} JSON lines fixed")
        print("=" * 65)
        total_db = sum(db_report.values())
        total_json = sum(json_report.values())
        action_verb = "Identified" if dry_run else "Successfully fixed"
        print(f"Total: {action_verb} {total_db} rows in DB and {total_json} lines in JSON.")

    return {"db": db_report, "json": json_report}


def main():
    parser = argparse.ArgumentParser(description="GFL2 Lore Glossary Manager (Database-Driven)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Database file path")
    subparsers = parser.add_subparsers(dest="command")

    # fix
    p_fix = subparsers.add_parser("fix", help="Audit & auto-fix bad translations in DB & JSON")
    p_fix.add_argument("--json", type=Path, default=DEFAULT_EN, help="Target English JSON file")
    p_fix.add_argument("--cn", type=Path, default=DEFAULT_CN, help="Baseline Chinese JSON file")
    p_fix.add_argument("--dry-run", action="store_true", help="Audit without saving changes")
    p_fix.add_argument("--all", action="store_true", help="Audit ALL rows in DB (ignores is_verified flag)")
    p_fix.add_argument("--no-db", action="store_true", help="Skip database mutations (JSON-only mode)")

    # list
    p_list = subparsers.add_parser("list", help="List terms in the database glossary")
    p_list.add_argument("--category", type=str, default=None, help="Filter by category")

    # add
    p_add = subparsers.add_parser("add", help="Add or update a term in the database")
    p_add.add_argument("cn", help="Chinese source term")
    p_add.add_argument("en", help="Official English translation")
    p_add.add_argument("--bad", nargs="*", default=[], help="Forbidden bad translation strings")
    p_add.add_argument("--exclude", nargs="*", default=[], help="Exclusion substrings in Chinese")
    p_add.add_argument("--category", default="General", help="Category")
    p_add.add_argument("--context", default=None, help="Context/speaker")
    p_add.add_argument("--notes", default=None, help="Notes")

    # export
    p_exp = subparsers.add_parser("export", help="Export DB glossary to JSON")
    p_exp.add_argument("output", type=Path, default=DEFAULT_GLOSSARY_JSON, nargs="?", help="Output file (default: database_source/glossary.json)")

    # import
    p_imp = subparsers.add_parser("import", help="Import glossary JSON into DB")
    p_imp.add_argument("input", type=Path, default=DEFAULT_GLOSSARY_JSON, nargs="?", help="Input file (default: database_source/glossary.json)")


    args = parser.parse_args()

    if args.command == "fix" or args.command is None:
        if args.command is None:
            # Interactive or default fix: by default only unverified rows
            audit_and_fix(args.db, DEFAULT_EN, DEFAULT_CN, dry_run=False, audit_db=True, only_unverified=True)
        else:
            audit_and_fix(
                args.db,
                args.json,
                args.cn,
                dry_run=args.dry_run,
                audit_db=not args.no_db,
                only_unverified=not args.all
            )
    elif args.command == "list":
        list_terms(args.db, args.category)
    elif args.command == "add":
        add_term(args.db, args.cn, args.en, args.bad, args.exclude, args.category, args.context, args.notes)
    elif args.command == "export":
        export_terms(args.db, args.output)
    elif args.command == "import":
        import_terms(args.db, args.input)


if __name__ == "__main__":
    main()

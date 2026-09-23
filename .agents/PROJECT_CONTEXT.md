# 🤖 Agent Context & Memory: GFL2 Translation Toolkit

> **For Future Antigravity / AI Pair Programmers:**
> Read this document first. It contains the complete architectural memory, design decisions, and context for this repository so you can assist the user immediately without guessing.

---

## 🎯 1. Project Purpose & Scope
This toolkit maintains English localization for the game **Girls' Frontline 2: Exilium (GFL2)** across frequent ~20-day version updates.

### The Problem:
With every update, `LangPackageTableCnData.bytes` shifts and renumbers numerical table row IDs. Direct ID-based replacement corrupts translated text.

### The Solution:
A **Translation Memory (TM)** system backed by a local SQLite database (`translation_memory.db`). It maps original Chinese strings directly to their verified English translations, ignoring numerical table IDs.
* Matches **>96% of game text in under 1 second** on update day.
* Isolates new untranslated strings into bite-sized ~250-line JSON chunks for AI / ChatGPT translation.
* Enforces canonical GFL2 lore terminology via a database-driven Lore Glossary (currently 183 active rules).

---

## ⚙️ 2. Core Constraints & Developer Guidelines
1. **Zero External Dependencies (`pip`)**:
   * Must run on Python 3.10+ standard library ONLY.
   * Do NOT introduce `pip install` packages (e.g., do not require `pandas`, `customtkinter`, `requests`, etc.).
   * GUI is built using built-in `tkinter` and `ttk` with custom dark styling.
2. **Database Management**:
   * Database file: `translation_memory.db` (~129 MB, SQLite in WAL mode, contains ~269,314 translations and 192 lore rules).
   * Schema: Tables `translations` and `glossary` feature full audit timestamps (`created_at`, `updated_at`) and verification flags (`is_verified`).
   * **DO NOT track or commit `translation_memory.db` to Git** (GitHub has a 100 MB hard limit). It is ignored via `.gitignore`.
   * The user backs up and shares the database via Google Drive.
3. **Workspace Protection**:
   * Do NOT modify anything inside `Test/` or `private_source/`.
   * Keep outputs isolated in `output/` or user-chosen modal drop destinations.

---

## 📁 3. Repository Architecture & Key Scripts

```text
langpackage_scripts/
├── .agents/
│   └── PROJECT_CONTEXT.md          # THIS FILE (AI Agent Memory & Context)
├── database_source/
│   └── glossary.json               # 183 official lore terms & bad translation rules
├── docs/
│   ├── BUILD_DATABASE_FROM_BYTES.md# Offline setup guide from matching CN+EN .bytes
│   ├── GUIDE.md                    # Complete 20-day patch operational manual
│   └── DISCORD_GUIDE.png           # Reference visual workflow
├── output/                         # Local working output (git-ignored)
│   ├── translations.json           # Extracted Chinese strings from new update
│   ├── translations_eng.json       # Generated English translations for new patch
│   ├── untranslated.json           # All untranslated lines delta
│   ├── untranslated_chunks/        # ~250-line chunks for AI translation
│   └── LangPackageTableCnData.bytes# Final ready-to-play compiled game binary
├── .gitignore                      # Ignores *.bytes, *.db*, /output/, *.zip
├── app_ui.py                       # Modern Dark Desktop GUI (tkinter/ttk)
├── run_ui.bat                      # Double-click launcher for app_ui.py
├── apply_glossary.py               # Database Lore Glossary manager & auto-fixer
├── run_glossary.bat                # Interactive terminal launcher for glossary
├── gfl2_translation_sync.py        # Core Translation Memory sync engine
├── run_translation_sync.bat        # Interactive terminal launcher for sync engine
├── langpackage_export.py           # Binary table extractor (.bytes -> JSON)
├── langpackage_import.py           # Binary table builder (JSON -> .bytes)
└── README.md                       # Main GitHub documentation page
```

---

## 🖥️ 4. GUI Architecture (`app_ui.py`)
Built with `tkinter` and `ttk` using an anime sci-fi dark theme (`#121218`).
* **Thread Safety**: All long-running operations (export, sync, auto-fix, import) run in a `threading.Thread` with a `queue.Queue` log pump (`root.after(100, ...)`) to prevent Windows GUI freezes.
* **Modal Dialogs**: Native Windows file selection (`filedialog.askopenfilename`) and save location selection (`filedialog.asksaveasfilename`).
* **5 Dedicated Tabs**:
  1. `🔄 20-Day Patch Updater`: 1-click full pipeline (Export $\to$ Sync $\to$ Lore Auto-Fix $\to$ Binary Rebuild).
  2. `📦 First-Time Setup`: Builds `translation_memory.db` from matching CN and EN `.bytes` files.
  3. `🛡️ Lore Glossary`: Searchable Treeview of 183 terms, modal term creator, Audit & Auto-fix button, JSON Export/Import.
  4. `🧩 Untranslated Chunks`: Lists any `*.json` chunks in `output/untranslated_chunks/`, 1-click "Copy for ChatGPT", and chunk importer.
  5. `⚙️ Database & Backup`: Live stats card, ZIP backup, JSON export, SQLite `VACUUM` optimizer.

---

## 🛡️ 5. Lore Glossary Mechanics & Exclusions (`apply_glossary.py`)
Protects against recurring AI/machine translation mistranslations:
* Example: `星痕` $\to$ AI translates as `Star Abyss` $\to$ Auto-fixed to official canon **`Ateraxis`**.
* Example: `铁血` $\to$ AI translates as `Iron Blood` $\to$ Auto-fixed to **`Sangvis Ferri`**.
* Example: `艾莫号` $\to$ AI translates as `Emmo` $\to$ Auto-fixed to **`the Elmo`**.

### How It Works:
1. **Ingestion Gate (Chunk Import Auto-Fix)**: The glossary runs automatically when importing new chunks in Tab 4 (`import_translated_file`), cleaning AI mistranslations *before* committing them into `translation_memory.db`.
2. **Database Immutability during Patch Updates**: Tab 1 (20-Day Patch Updater) is **read-only for the database** (`audit_db=False`). It extracts and generates the `.bytes` game file without retroactively mutating verified historical database entries.
3. **Verification Flag (`is_verified`)**: Table `translations` has `is_verified INTEGER DEFAULT 1`. Verified entries are locked against automated regex overwrites, preventing human edits and natural English phrasing (e.g. natural pronouns like `They`) from being corrupted.
4. **Hyphen-Aware Boundary Safeguard**: Bad translations use `(?<![\w\-])term(?![\w\-])` instead of naive `\b`. This guarantees words like `Doll` will never match inside hyphenated compounds (e.g., `T-Doll`, `A-Doll`, `Non-Doll`).
5. **Context & Idempotency Protection**: `safe_replace_term()` ensures that already-correct target phrases (e.g. `Speed Star`, `Project Eden`) are protected from having sub-words re-replaced.
6. **Exclusions (`exclusions`)**:
   * If any string in `exclusions` is found in the Chinese sentence, the auto-fixer **skips that sentence completely**.
   * **Title/Context Guard**: `欧菲露妮` $\to$ `Ophelune` with exclusion `["欧菲露妮小姐"]`. This ensures maid Igia's respectful address `Young Mistress` is 100% protected and never overwritten.
   * **Hierarchical Faction Guard**: `法本集团` $\to$ `FABN Group` with exclusion `["赛诺菲与法本集团"]`. This ensures the longer name `赛诺菲与法本集团` $\to$ `Cecht FABN` is cleanly applied without partial conflict.
7. **Canonical Terms (191 Active Terms)**:
   * `人形` is correctly defined as `Doll` (generic / civilian).
   * `战术人形` is defined as `T-Doll` (combat-configured).
   * Expanded with 112 T-Doll names and lore factions.

---

## 🧩 6. Untranslated Chunks & Importer Format
When importing chunks via Tab 4 (`Import Selected Chunk`):
* **Automatic Glossary Clean-up**: Applied automatically at import time; logs all terms corrected.
* **Sets `is_verified = 1`**: Newly imported strings are saved directly into `translation_memory.db` as verified.
* **Core Rule**: The JSON **Key** must be the original Chinese text, and the **Value** must be the English translation.
* **Standard Format**:
  ```json
  {
    "translations": {
      "原版中文文本": "English translated text"
    }
  }
  ```
* Importer also accepts flat `{ "中文": "English" }` or `{ "texts": { ... } }`.
* Automatically strips markdown fences (```` ```json ````) if copied directly from ChatGPT.
* Skips any values that are empty `""` or identical to Chinese.

---

## 🔍 7. Database Status & Verification Architecture
* **Total Translations**: 269,314 lines (100% verified with `is_verified = 1`).
* **Untranslated in Chinese**: 0 lines (100% translated).
* **Timestamps & Audit Tracking**:
  - `translations`: `source_cn`, `target_en`, `category`, `context`, `created_at`, `updated_at`, `is_verified`.
  - `glossary`: `source_cn`, `target_en`, `bad_translations`, `exclusions`, `category`, `speaker_context`, `notes`, `created_at`, `updated_at`.
* **Database Immutability & Workflow**:
  - The SQLite database is treated as the source of truth and is strictly read-only during routine 20-day patch updates (`audit_db=False`).
  - Automated lore glossary regex rules run strictly as an ingestion gate when importing newly translated chunks (Tab 4).
  - Fine-grained corrections and quality fixes are performed directly row-by-row in DBeaver by the user.
* **The Cecilia Story Quirk**: In a past patch, Mica Team added single characters (e.g. `落入` $\to$ `落入了`, and `劝阻` $\to$ `鼓动`). These have been fully matched and updated with their official English text in `translation_memory.db`.

---

## 🚀 8. Routine Patch Update Flow (Quick Reference)
When a 20-day patch drops:
1. Drop the new update's `LangPackageTableCnData.bytes` into the root directory.
2. Launch `run_ui.bat`.
3. In Tab 1, ensure Input points to the new `.bytes` file and Output points to `output/LangPackageTableCnData.bytes`.
4. Click **🚀 RUN FULL UPDATE PIPELINE**.
5. If untranslated strings exist:
   * Go to Tab 4 (`🧩 Untranslated Chunks`).
   * Copy chunk $\to$ Translate with ChatGPT $\to$ Save in file $\to$ Click Import.
   * Click Rebuild in Tab 1.
6. Copy the resulting `output/LangPackageTableCnData.bytes` into the game directory. Done!

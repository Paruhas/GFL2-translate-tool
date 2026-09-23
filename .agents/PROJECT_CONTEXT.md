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
* Enforces canonical GFL2 lore terminology via a database-driven Lore Glossary.

---

## ⚙️ 2. Core Constraints & Developer Guidelines
1. **Zero External Dependencies (`pip`)**:
   * Must run on Python 3.10+ standard library ONLY.
   * Do NOT introduce `pip install` packages (e.g., do not require `pandas`, `customtkinter`, `requests`, etc.).
   * GUI is built using built-in `tkinter` and `ttk` with custom dark styling.
2. **Database Management**:
   * Database file: `translation_memory.db` (~129 MB, SQLite in WAL mode, contains ~269,000+ translations and 143 lore rules).
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
│   └── glossary.json               # 143 official lore terms & bad translation rules
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
  3. `🛡️ Lore Glossary`: Searchable Treeview of 143 terms, modal term creator, Audit & Auto-fix button, JSON Export/Import.
  4. `🧩 Untranslated Chunks`: Lists ~250-line chunks, 1-click "Copy for ChatGPT", single and batch chunk importer.
  5. `⚙️ Database & Backup`: Live stats card, ZIP backup, JSON export, SQLite `VACUUM` optimizer.

---

## 🛡️ 5. Lore Glossary Mechanics (`apply_glossary.py`)
Protects against recurring AI/machine translation mistranslations:
* Example: `星痕` $\to$ AI translates as `Star Abyss` $\to$ Auto-fixed to official canon **`Ateraxis`**.
* Example: `铁血` $\to$ AI translates as `Iron Blood` $\to$ Auto-fixed to **`Sangvis Ferri`**.
* Example: `艾莫号` $\to$ AI translates as `Emmo` $\to$ Auto-fixed to **`the Elmo`**.

### How It Works:
1. **Target English Only**: The original Chinese text (`source_cn`) is NEVER modified. The glossary only inspects and fixes English text (`target_en`).
2. **Chinese Guard**: Only searches for banned English words if the original Chinese sentence actually contains the Chinese keyword (`source_cn LIKE '%keyword%'`).
3. **Word Boundary Safeguard (`\b`)**: All bad translations are searched using `\b{banned_term}\b`. This ensures normal English words are never damaged (e.g. `\bLandin\b` will **never** match or corrupt `landing`).
4. **Community Glossary Update**: Recently expanded with 112 T-Doll names from Discord (total 143 terms). Four historical typos were resolved:
   * `人形莱娅` $\to$ `T-Doll Leva` (was swapped)
   * `人形莱娜` $\to$ `T-Doll Lenna` (was swapped)
   * `人形六分仪` $\to$ `T-Doll Sextans` (fixed missing 's')
   * `莫辛纳甘` $\to$ `Mosin-Nagant` (canonical hyphenation)

---

## 🚀 6. Routine Patch Update Flow (Quick Reference)
When a 20-day patch drops:
1. Drop the new update's `LangPackageTableCnData.bytes` into the root directory.
2. Launch `run_ui.bat`.
3. In Tab 1, ensure Input points to the new `.bytes` file and Output points to `output/LangPackageTableCnData.bytes`.
4. Click **🚀 RUN FULL UPDATE PIPELINE**.
5. If untranslated strings exist:
   * Go to Tab 4 (`🧩 Untranslated Chunks`).
   * Copy chunk $\to$ Translate with ChatGPT $\to$ Import chunk back.
   * Click Rebuild in Tab 1.
6. Copy the resulting `output/LangPackageTableCnData.bytes` into the game directory. Done!

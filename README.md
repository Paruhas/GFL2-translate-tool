# GFL2 Translation Memory & Update Sync Toolkit

A complete, high-performance localization maintenance toolkit for **Girls' Frontline 2: Exilium (GFL2)** game packages (`LangPackageTableCnData.bytes`).

---

## 📋 Requirements & Prerequisites

> [!IMPORTANT]
> This repository contains **open-source code and tooling only**. To keep the repository lightweight and respect intellectual property, no proprietary game binaries or translation databases are hosted here.

### 1. System Requirements

- **Operating System**: Windows 10 / 11
- **Python**: Python 3.10 or higher (Uses Python standard library only; **no `pip install` required**)
- **Database**: SQLite3 (Pre-bundled with Python standard library — **no database server installation needed**)
- _(Optional Database GUI)_: **[DBeaver](https://dbeaver.io/)** or **[DB Browser for SQLite](https://sqlitebrowser.org/)** (if you want a visual UI to explore `translation_memory.db`)

### 2. Translation Memory Database

To translate and update the game, you need the **Translation Memory Database** (`translation_memory.db`):

- **🌟 Option A (Recommended)**: Download the pre-built database from Google Drive and drop it in this folder.
- **🛠️ Option B (Build from .bytes)**: If you prefer compiling your own database from matching baseline `.bytes` files, see [`docs/BUILD_DATABASE_FROM_BYTES.md`](docs/BUILD_DATABASE_FROM_BYTES.md).

---

## 📖 Overview & Purpose

Whenever GFL2 receives an update (roughly every 20 days), the internal table IDs and row indexes inside `LangPackageTableCnData.bytes` shift and reorder. Direct ID-based replacement breaks older translation files.

This toolkit solves that problem using **Translation Memory (TM)**:

- **String-Based Matching**: Matches Chinese text directly against a local SQLite database, ignoring shifting numerical table IDs.
- **Instant Re-use**: Matches **>96% of existing translations in under 1 second** on patch day.
- **Smart Delta Detection**: Isolates only brand-new Chinese strings and splits them into bite-sized 250-line chunks for AI / ChatGPT translation.
- **Database-Driven Lore Glossary**: Automatically prevents and auto-fixes recurring machine translation mistakes (`Star Abyss` → `Ateraxis`, `Iron Blood` → `Sangvis Ferri`, `Emmo` → `the Elmo`, `Sextant` → `Sextans`, generic `sir` → `Your Excellency`).

---

## 📂 Repository Structure

```text
langpackage_scripts/
├── database_source/
│   └── glossary.json               # Official GFL2 lore terms and substitution rules
├── docs/
│   ├── BUILD_DATABASE_FROM_BYTES.md# Guide for building DB from baseline .bytes files
│   ├── GUIDE.md                    # Detailed operational manual & patch update guide
│   └── DISCORD_GUIDE.png           # Reference visual guide image
├── output/                         # Local working directory (git-ignored)
│   ├── translations_eng.json       # Generated English text matching new table IDs
│   ├── untranslated.json           # All new untranslated lines from update
│   ├── untranslated_chunks/        # ~250-line chunks ready for AI translation
│   └── LangPackageTableCnData.bytes# Final ready-to-play translated game binary
├── .gitignore                      # Git ignore rules
├── app_ui.py                       # Modern Desktop GUI application
├── run_ui.bat                      # Double-click launcher for Desktop UI
├── apply_glossary.py               # Database-driven Lore Glossary auditor & auto-fixer
├── gfl2_translation_sync.py        # Core Translation Memory & update sync engine
├── langpackage_export.py           # Extracts .bytes files into readable JSON
├── langpackage_import.py           # Rebuilds translated JSON back into .bytes
├── README.md                       # Main GitHub project landing page
├── run_glossary.bat                # Double-click launcher for Lore Glossary manager
└── run_translation_sync.bat        # Double-click launcher for translation sync
```

---

## 🖥️ Graphical User Interface (Desktop UI)

For a one-click visual experience, double-click **`run_ui.bat`** (or run `python app_ui.py`):

- **Modal Upload Dialog**: Select any input `.bytes` file with a native Windows file browser.
- **Modal Download/Save Dialog**: Choose custom output destinations to drop your finished translated mod file.
- **Integrated Tools**: Includes 20-Day Patch Updater, First-Time Database Builder, Lore Glossary Manager, Untranslated Chunks Manager, and Database Backup in a single sleek dark-mode window.

---

## 🚀 First-Time Setup

To get started, you need the local **Translation Memory Database** (`translation_memory.db`). Choose whichever option is easiest for you:

### 🌟 Option A: Download Pre-Built Database (Recommended — Instant Start!)

1. Download **`translation_memory.db`** (or `translation_memory.zip`) from our community drive:
   - **[📥 Download translation_memory.db from Google Drive](https://drive.google.com/file/d/1VvAQsDt59hJ8sALiksX9opzOPz548L1r/view?usp=sharing)**
2. Place `translation_memory.db` directly inside this `langpackage_scripts/` folder.
3. **You are ready!** You can skip setup completely and start updating new patches immediately by double-clicking **`run_ui.bat`**.

---

### 🛠️ Option B: Build Your Own Database (From Baseline .bytes Files)

If you prefer compiling your own database from original matching baseline `.bytes` files instead of downloading the pre-built database:

👉 **See the complete step-by-step instructions in [`docs/BUILD_DATABASE_FROM_BYTES.md`](docs/BUILD_DATABASE_FROM_BYTES.md)**

_(Supports 1-click build via Desktop UI **📦 First-Time Setup** tab, interactive terminal menu, or direct CLI commands)._

---

## 📖 Detailed User Manual & Guides

For detailed step-by-step instructions on updating the game every 20 days, translating new chunks with AI, and managing the Lore Glossary, please consult the complete manual:

👉 **See [`docs/GUIDE.md`](docs/GUIDE.md)** for:

- **Patch Update Workflow**: Detailed 5-step routine for each 20-day game update.
- **AI Translation Guide**: How to translate new strings using ChatGPT, Claude, or Google Translate.
- **Lore Glossary & Rulebook**: Complete table of enforced lore terms (`Ateraxis`, `Sangvis Ferri`, `the Elmo`, `Sextans`, `Your Excellency`, etc.) and how to add new terms.

---

## 🛠️ CLI Quick Reference Table

| Task                             | Command                                                                        |
| :------------------------------- | :----------------------------------------------------------------------------- |
| **Export .bytes to JSON**        | `python langpackage_export.py <input.bytes> <output.json>`                     |
| **Build DB from baseline files** | `python gfl2_translation_sync.py build --cn <cn.json> --en <en.json>`          |
| **Sync update & export chunks**  | `python gfl2_translation_sync.py sync --input translations.json`               |
| **Import translated chunk(s)**   | `python gfl2_translation_sync.py import output/untranslated_chunks`            |
| **Audit & Fix Lore Glossary**    | `python apply_glossary.py fix`                                                 |
| **List Glossary terms**          | `python apply_glossary.py list`                                                |
| **Export Glossary to JSON**      | `python apply_glossary.py export`                                              |
| **Import Glossary from JSON**    | `python apply_glossary.py import`                                              |
| **Rebuild final .bytes file**    | `python langpackage_import.py <source.bytes> <translated.json> <output.bytes>` |

---

## 💡 Best Practices

- **Preserve In-Game Markup**: Strings in GFL2 contain formatting tags like `<color=#FFA800>text</color>`, `{0}`, and `\n`. The sync tool preserves these automatically during string matching.
- **Local Database Safety**: Your `translation_memory.db` stays strictly on your local machine and will never be overwritten or deleted by git pulls.

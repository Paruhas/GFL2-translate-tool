# GFL2 Translation Memory & Sync Toolkit

A complete, high-performance translation management suite for **Girls' Frontline 2: Exilium (GFL2)** localization files (`LangPackageTableCnData.bytes`).

---

## 📖 Overview & Purpose

When GFL2 updates, the internal table IDs and row indexes in `LangPackageTableCnData.bytes` frequently change, shift, or get reordered. Previously, this broke older translated files and forced translators to re-translate from scratch.

This toolkit solves that problem by using **Translation Memory (TM)**:
* **String-Based Matching:** Matches Chinese text directly against a persistent database, ignoring shifting ID numbers.
* **Instant Re-use:** Re-applies over **96% of existing translations in under 1 second** across game updates.
* **Smart Delta Detection:** Automatically isolates only the brand-new or updated Chinese lines.
* **Flexible Translation Workflows:** Allows automatic translation, AI/ChatGPT chunking, or direct assistant translation.
* **Permanent Learning:** Every newly translated string is saved to the database so you never have to translate it again.

---

## 📂 File Structure

```text
langpackage_scripts/
├── LangPackageTableCnData.bytes   # The untouched Chinese file from the game update
├── langpackage_export.py           # Extracts .bytes into translations.json
├── gfl2_translation_sync.py        # Core Translation Memory & synchronization engine
├── run_translation_sync.bat        # Double-click launcher with interactive menu
├── apply_glossary.py               # Database-driven Lore Glossary auditor & auto-fixer
├── run_glossary.bat                # Double-click launcher for Lore Glossary Manager
├── glossary.json                   # Exported / editable lore glossary and rulebook
├── translation_memory.db          # SQLite database (stores translations & glossary table)
├── translations.json              # Extracted Chinese texts (with new IDs)
├── langpackage_import.py           # Rebuilds translated JSON into .bytes
└── output/
    ├── translations_eng.json      # Generated translated English texts (matches new IDs)
    ├── untranslated.json          # Full list of new untranslated strings from update
    ├── untranslated_chunks/       # Bite-sized JSON files (~250 lines each) for AI translation
    └── LangPackageTableCnData.bytes # Final translated game file ready to play!
```

---

## 🚀 Quick Start Guide (Step-by-Step)

Whenever the game receives an update, follow these simple steps:

### Step 1: Place the New Chinese File
Copy the new `LangPackageTableCnData.bytes` from your game update into this folder:
`C:\Users\Paruhas.c\Downloads\langpackage_scripts\`

---

### Step 2: Export Text to JSON
Double-click **`langpackage_export.py`** (or run `python langpackage_export.py`).  
* This extracts the game package and produces **`translations.json`** with the update's new table IDs.
* Press Enter to close when it completes.

---

### Step 3: Match Previous Translations
Double-click **`run_translation_sync.bat`** (or run `python gfl2_translation_sync.py`):
1. Select **Option 2** (*Sync New Update*).
2. Press **Enter** to accept default paths (outputs directly to `output/`).
3. **What happens:**
   * It matches existing phrases from the database in **< 1 second**.
   * It creates **`output/translations_eng.json`** (already ~96% translated!).
   * It exports all new/untranslated text into **`output/untranslated_chunks/`** (split into manageable ~250-line files).

> [!TIP]
> Even if you don't translate the new text yet, your game file is already 96% translated and fully playable!

---

### Step 4: Translate the New Strings

You have three ways to translate the remaining chunks in `output/untranslated_chunks/`:

#### Option A: Ask Antigravity (Easiest)
Simply ask in chat:
> *"Please translate `chunk_001.json` through `chunk_005.json`."*
Antigravity will translate the files directly in your workspace and update your database automatically.

#### Option B: Use ChatGPT / Claude Web
1. Open any file in `output/untranslated_chunks/` (e.g. `chunk_001.json`).
2. Copy the contents (`Ctrl+A`, `Ctrl+C`).
3. Paste into ChatGPT or Claude. The file already has the system prompt at the top.
4. Copy the AI's response and save it back into the file.
5. In `run_translation_sync.bat`, choose **Option 4** (*Import translated file*) and press Enter.

#### Option C: Built-in Auto-Translate
In `run_translation_sync.bat`, choose **Option 3** (*Auto-Translate new strings*).  
* It will translate new strings via Google Translate and save them to the database.  
*(Note: Large batches of 5,000+ lines may be throttled by Google; Options A and B are recommended for large updates).*

---

### Step 5: Audit & Auto-Fix Lore Glossary (Recommended)
Before rebuilding your game file, run the lore auditor to clean up any machine translation quirks (e.g. `Star Abyss` → `Ateraxis`, `Sextant` → `Sextans`, generic `sir` → `Your Excellency`):

* Double-click **`run_glossary.bat`** and select **Option 1** (*Audit & Auto-Fix*).
* Or run in terminal:
  ```powershell
  python apply_glossary.py fix
  ```
This instantly verifies both `translation_memory.db` and `output/translations_eng.json` against the database glossary rules.

---

### Step 6: Rebuild the Game File
Once you are ready to build:

```powershell
python langpackage_import.py LangPackageTableCnData.bytes output/translations_eng.json output/LangPackageTableCnData.bytes
```

Your finished translated game package will be located at:
`output\LangPackageTableCnData.bytes`

Copy this file into your game's data folder, and you are ready to play!

---

## 🛡️ Lore Glossary & Terminology Protection (Database-Driven)

To prevent generic AI and machine translators from mistranslating official Girls' Frontline lore across 20-day update cycles, all official terms, forbidden translations, and character contexts are stored **directly inside the database** (`translation_memory.db` in table `glossary`).

### Key Lore Rules Enforced

| Chinese Term | Official English | Forbidden / Machine Translations Replaced | Context / Notes |
| :--- | :--- | :--- | :--- |
| **星渊** | **Ateraxis** | `Star Abyss`, `Star Abyss-a`, `Astral Abyss` | Avatar of Boojum |
| **铁血** / **铁血工造** | **Sangvis Ferri** | `Iron Blood`, `Iron-Blood`, `IronBlood` | Faction name |
| **艾莫号** / **艾莫** | **the Elmo** / **Elmo** | `Emmo`, `Aimo` | Commander's mobile base |
| **六分仪** | **Sextans** | `Sextant` | Tactical Doll (brass sextant instrument kept intact) |
| **六分仪小姐** | **Miss Sextans** | `Miss Sextant` | Doll address |
| **阁下** | **Your Excellency** | `sir`, `Sir`, `Milord` | Formal address used towards the Commander |
| **伯介姆** | **Boojum** | `Bojem`, `Bergam` | Extraterrestrial entity |
| **塌陷液** | **Collapse Fluid** | `Collapse Liquid` | Relic energy substance |
| **心智云图** | **Neural Cloud** | `Mental Cloud` | Doll consciousness storage |
| **希岸空间** | **Nirvana space** | `Xi'an space`, `Xian space` | Virtual realm |
| **科德韦尔** | **Caldwell** | `Coldwell` | Key story researcher |
| **新苏联** | **Neo-Soviet** | `New Soviet` | Faction |

### Managing the Glossary

* **View terms**: Double-click `run_glossary.bat` (Option 2) or run `python apply_glossary.py list`
* **Auto-Fix**: Double-click `run_glossary.bat` (Option 1) or run `python apply_glossary.py fix`
* **Export to JSON**: Run `python apply_glossary.py export glossary.json` to share or edit in VS Code
* **Import from JSON**: Edit `glossary.json` and sync it back into the DB with `python apply_glossary.py import glossary.json`
* **Add new term via CLI**:
  ```powershell
  python apply_glossary.py add "源石" "Originium" --bad "Source Stone" --category "Lore"
  ```

---

## 🛠️ Command-Line Interface (CLI) Reference

For automated scripts or terminal users, all commands can be run directly:

| Task | Command |
| :--- | :--- |
| **Sync update & export chunks** | `python gfl2_translation_sync.py sync --input translations.json` |
| **Sync & auto-translate** | `python gfl2_translation_sync.py sync --input translations.json --auto-translate` |
| **Import translated chunk(s)** | `python gfl2_translation_sync.py import output/untranslated_chunks` |
| **Import single JSON file** | `python gfl2_translation_sync.py import output/my_translations.json` |
| **Export database to JSON** | `python gfl2_translation_sync.py export output/translation_memory_backup.json` |
| **Audit & Fix Lore Glossary** | `python apply_glossary.py fix` |
| **List Glossary terms** | `python apply_glossary.py list` |
| **Export Glossary to JSON** | `python apply_glossary.py export glossary.json` |
| **Import Glossary from JSON** | `python apply_glossary.py import glossary.json` |
| **View database statistics** | `python gfl2_translation_sync.py stats` |

---

## 💡 Key Tips & Best Practices

* **Formatting Tags:** In GFL2, strings often contain tags like `<color=#FFA800>text</color>`, `{0}`, and `\n`. The sync tool preserves these automatically during string matching.
* **Database Safety:** The SQLite database `translation_memory.db` is stored locally. You can back it up anytime using Option 5 or by copying the `.db` file.
* **Incremental Updates:** You can translate as few or as many chunks as you want. Any imported chunk is permanently stored in the database.


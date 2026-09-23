# Building Database from Baseline `.bytes` Files (Alternative / Offline Setup)

This guide documents the original / alternative setup procedure for building your local `translation_memory.db` from scratch using matching Chinese and English `.bytes` files.

---

## 📌 When to Use This Guide
* You prefer to compile your own personal database from original game files instead of downloading the pre-built `translation_memory.db` from Google Drive.
* You are operating in an offline environment without internet access.
* You are creating a custom localization database from a different baseline game version.

---

## 📋 Requirements
To generate your personal Translation Memory database without data corruption, you **MUST** provide two `.bytes` files from the **SAME game version**:
1. **Original Chinese file**: `LangPackageTableCnData_CN.bytes` (version X)
2. **English translated mod file**: `LangPackageTableCnData_EN.bytes` (from the **same** version X)

> [!WARNING]
> Do NOT mix files from different game patches! If the Chinese and English files come from different game versions, their numerical table IDs will not match, causing strings to be paired incorrectly in your database.

---

## 🖥️ Method 1: Using the Desktop UI (Recommended)

1. Double-click **`run_ui.bat`** to open the GFL2 Translation Manager.
2. Navigate to the **`📦 First-Time Setup`** tab.
3. Click **📁 Choose Chinese...** and select your `LangPackageTableCnData_CN.bytes`.
4. Click **📁 Choose English...** and select your `LangPackageTableCnData_EN.bytes`.
5. Click **⚡ BUILD TRANSLATION MEMORY DATABASE**.
6. The toolkit will automatically:
   * Extract both binary tables to temporary JSON.
   * Match string IDs and insert all ~260,000+ pairs into `translation_memory.db`.
   * Automatically import all official lore glossary rules from `database_source/glossary.json`.

---

## 🖱️ Method 2: Using the Interactive Terminal Menu

### Step 1: Place and rename the files
Place your matching `.bytes` files in the root folder and name them:
* `LangPackageTableCnData_CN.bytes`
* `LangPackageTableCnData_EN.bytes`

### Step 2: Export both files to JSON
Open PowerShell or Command Prompt in the repository folder:
```powershell
python langpackage_export.py LangPackageTableCnData_CN.bytes output/translations.json
python langpackage_export.py LangPackageTableCnData_EN.bytes output/translations_eng.json
```

### Step 3: Run the interactive builder
1. Double-click **`run_translation_sync.bat`** (or run `python gfl2_translation_sync.py`).
2. Type **`1`** (*Build / Seed Database from existing translations*) and press Enter.
3. Press **Enter** to accept the default file paths:
   * Chinese input: `output/translations.json`
   * English input: `output/translations_eng.json`
   * Database: `translation_memory.db`

---

## ⚙️ Method 3: Direct CLI Command (PowerShell / Command Prompt)

If you prefer a one-line headless command:
```powershell
# 1. Export tables
python langpackage_export.py LangPackageTableCnData_CN.bytes output/translations.json
python langpackage_export.py LangPackageTableCnData_EN.bytes output/translations_eng.json

# 2. Build Translation Memory database
python gfl2_translation_sync.py build --cn output/translations.json --en output/translations_eng.json --db translation_memory.db
```

---

## 🔍 Verification
Once complete:
1. `translation_memory.db` will be created in your root directory (~129 MB).
2. Open **`run_ui.bat`** $\to$ **`⚙️ Database & Backup`** tab to verify that the translation count shows ~260,000+ learned phrases and 30 active Lore Glossary rules.
3. You can now delete the temporary files or `.bytes` files and proceed with updating future patches!

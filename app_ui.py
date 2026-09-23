#!/usr/bin/env python3
"""GFL2 Localization Manager - Modern Graphical User Interface (UI).

A complete, self-contained desktop UI for Girls' Frontline 2: Exilium translation.
- Exports, matches, translates, and rebuilds LangPackageTableCnData.bytes.
- Manages translation memory (SQLite) and database-driven lore glossary.
- Modal file upload & download dialogs for choosing custom input and output files.
- Thread-safe background processing with real-time logs and progress feedback.
"""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import queue
import re
import shutil
import sqlite3
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import zipfile

# Core project modules
import apply_glossary
import gfl2_translation_sync
import langpackage_export
import langpackage_import

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = BASE_DIR / "translation_memory.db"
DEFAULT_OUTPUT_DIR = BASE_DIR / "output"
DEFAULT_GLOSSARY_JSON = BASE_DIR / "database_source" / "glossary.json"

# Color Palette (Dark Theme / Sci-Fi Anime Accent)
BG_DARK = "#121218"
BG_CARD = "#1a1a24"
BG_CARD_LIGHT = "#242434"
BG_INPUT = "#1e1e2c"
FG_MAIN = "#f3f4f6"
FG_MUTED = "#94a3b8"
ACCENT_ORANGE = "#f26c1c"
ACCENT_BLUE = "#3b82f6"
ACCENT_GREEN = "#10b981"
ACCENT_RED = "#ef4444"
BORDER_COLOR = "#2d2d3f"


class GFL2TranslatorApp(tk.Tk):
    """Main Application Window for GFL2 Translation Manager."""

    def __init__(self):
        super().__init__()

        self.title("GFL2 Translation Manager & Sync Tool")
        self.geometry("1020x720")
        self.minsize(880, 600)
        self.configure(bg=BG_DARK)

        # Set taskbar icon if available
        self.log_queue = queue.Queue()

        self._setup_styles()
        self._build_header()
        self._build_notebook()
        self._build_statusbar()

        # Start periodic log pump
        self.after(100, self._process_log_queue)

        # Initial data load
        self.after(200, self.refresh_glossary_table)
        self.after(300, self.refresh_database_stats)
        self.after(400, self.refresh_chunks_list)

    # ==========================================================================
    # Styling & Theming
    # ==========================================================================
    def _setup_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(".", background=BG_DARK, foreground=FG_MAIN, font=("Segoe UI", 10))

        # Notebook (Tabs)
        style.configure(
            "TNotebook",
            background=BG_DARK,
            borderwidth=0,
            tabmargins=[10, 8, 10, 0]
        )
        style.configure(
            "TNotebook.Tab",
            background=BG_CARD,
            foreground=FG_MUTED,
            padding=[16, 8],
            font=("Segoe UI", 10, "bold"),
            borderwidth=0
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", BG_CARD_LIGHT), ("active", "#2d2d42")],
            foreground=[("selected", ACCENT_ORANGE), ("active", FG_MAIN)]
        )

        # Frames & Labels
        style.configure("Card.TFrame", background=BG_CARD)
        style.configure("CardHeader.TLabel", background=BG_CARD, foreground=FG_MAIN, font=("Segoe UI", 12, "bold"))
        style.configure("CardSub.TLabel", background=BG_CARD, foreground=FG_MUTED, font=("Segoe UI", 9))
        style.configure("TLabel", background=BG_CARD, foreground=FG_MAIN)

        # Treeview (Glossary Table)
        style.configure(
            "Treeview",
            background=BG_INPUT,
            foreground=FG_MAIN,
            fieldbackground=BG_INPUT,
            rowheight=28,
            font=("Segoe UI", 10),
            borderwidth=0
        )
        style.configure(
            "Treeview.Heading",
            background=BG_CARD_LIGHT,
            foreground=FG_MAIN,
            font=("Segoe UI", 10, "bold"),
            borderwidth=1,
            relief="flat"
        )
        style.map(
            "Treeview",
            background=[("selected", ACCENT_BLUE)],
            foreground=[("selected", "#ffffff")]
        )

        # Progressbar
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor=BG_INPUT,
            background=ACCENT_ORANGE,
            thickness=8,
            borderwidth=0
        )

    # ==========================================================================
    # UI Header
    # ==========================================================================
    def _build_header(self):
        header = tk.Frame(self, bg=BG_DARK, height=65)
        header.pack(fill=tk.X, padx=20, pady=(15, 5))

        title_lbl = tk.Label(
            header,
            text="GIRLS' FRONTLINE 2: EXILIUM",
            font=("Segoe UI", 16, "bold"),
            fg=ACCENT_ORANGE,
            bg=BG_DARK
        )
        title_lbl.pack(anchor=tk.W)

        sub_lbl = tk.Label(
            header,
            text="Translation Memory & Update Sync Toolkit • Database-Driven Lore Protection",
            font=("Segoe UI", 10),
            fg=FG_MUTED,
            bg=BG_DARK
        )
        sub_lbl.pack(anchor=tk.W)

    # ==========================================================================
    # UI Tabs (Notebook)
    # ==========================================================================
    def _build_notebook(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # Tab 1: Patch Updater (Home)
        self.tab_updater = ttk.Frame(self.notebook, style="Card.TFrame")
        self.notebook.add(self.tab_updater, text="  🔄 20-Day Patch Updater  ")
        self._init_tab_updater()

        # Tab 2: First-Time Setup
        self.tab_setup = ttk.Frame(self.notebook, style="Card.TFrame")
        self.notebook.add(self.tab_setup, text="  📦 First-Time Setup  ")
        self._init_tab_setup()

        # Tab 3: Lore Glossary
        self.tab_glossary = ttk.Frame(self.notebook, style="Card.TFrame")
        self.notebook.add(self.tab_glossary, text="  🛡️ Lore Glossary  ")
        self._init_tab_glossary()

        # Tab 4: Untranslated Chunks
        self.tab_chunks = ttk.Frame(self.notebook, style="Card.TFrame")
        self.notebook.add(self.tab_chunks, text="  🧩 Untranslated Chunks  ")
        self._init_tab_chunks()

        # Tab 5: Database & Tools
        self.tab_tools = ttk.Frame(self.notebook, style="Card.TFrame")
        self.notebook.add(self.tab_tools, text="  ⚙️ Database & Backup  ")
        self._init_tab_tools()

    # ==========================================================================
    # Tab 1: Patch Updater
    # ==========================================================================
    def _init_tab_updater(self):
        container = tk.Frame(self.tab_updater, bg=BG_CARD)
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)

        # Description
        tk.Label(
            container,
            text="One-Click Game Update Routine",
            font=("Segoe UI", 13, "bold"),
            fg=FG_MAIN,
            bg=BG_CARD
        ).pack(anchor=tk.W, pady=(0, 2))

        tk.Label(
            container,
            text="Drop or select the new Chinese .bytes file from the update. The toolkit will export, match translations, auto-fix lore terms, and rebuild your ready-to-play file.",
            font=("Segoe UI", 9),
            fg=FG_MUTED,
            bg=BG_CARD,
            wraplength=850,
            justify=tk.LEFT
        ).pack(anchor=tk.W, pady=(0, 15))

        # File Inputs Frame
        file_box = tk.Frame(container, bg=BG_CARD_LIGHT, padx=15, pady=15, highlightthickness=1, highlightbackground=BORDER_COLOR)
        file_box.pack(fill=tk.X, pady=(0, 15))

        # Input File (Modal Upload Dialog)
        r1 = tk.Frame(file_box, bg=BG_CARD_LIGHT)
        r1.pack(fill=tk.X, pady=5)
        tk.Label(r1, text="Input Game File (.bytes):", font=("Segoe UI", 10, "bold"), fg=FG_MAIN, bg=BG_CARD_LIGHT, width=22, anchor=tk.W).pack(side=tk.LEFT)
        self.updater_input_entry = tk.Entry(r1, bg=BG_INPUT, fg=FG_MAIN, insertbackground=FG_MAIN, relief="flat", font=("Segoe UI", 10))
        self.updater_input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 10), ipady=4)
        default_in = BASE_DIR / "LangPackageTableCnData.bytes"
        if default_in.exists():
            self.updater_input_entry.insert(0, str(default_in))
        btn_browse_in = tk.Button(
            r1,
            text="📁 Browse (Upload)...",
            command=self._choose_updater_input,
            bg="#2c2c3e",
            fg=FG_MAIN,
            activebackground=ACCENT_BLUE,
            relief="flat",
            padx=12,
            pady=4,
            cursor="hand2"
        )
        btn_browse_in.pack(side=tk.RIGHT)

        # Output File (Modal Download/Save Dialog)
        r2 = tk.Frame(file_box, bg=BG_CARD_LIGHT)
        r2.pack(fill=tk.X, pady=5)
        tk.Label(r2, text="Save Output Mod To:", font=("Segoe UI", 10, "bold"), fg=FG_MAIN, bg=BG_CARD_LIGHT, width=22, anchor=tk.W).pack(side=tk.LEFT)
        self.updater_output_entry = tk.Entry(r2, bg=BG_INPUT, fg=FG_MAIN, insertbackground=FG_MAIN, relief="flat", font=("Segoe UI", 10))
        self.updater_output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 10), ipady=4)
        default_out = DEFAULT_OUTPUT_DIR / "LangPackageTableCnData.bytes"
        self.updater_output_entry.insert(0, str(default_out))
        btn_browse_out = tk.Button(
            r2,
            text="💾 Choose Destination...",
            command=self._choose_updater_output,
            bg="#2c2c3e",
            fg=FG_MAIN,
            activebackground=ACCENT_BLUE,
            relief="flat",
            padx=12,
            pady=4,
            cursor="hand2"
        )
        btn_browse_out.pack(side=tk.RIGHT)

        # Options & Action Bar
        action_bar = tk.Frame(container, bg=BG_CARD)
        action_bar.pack(fill=tk.X, pady=(0, 10))

        self.var_autofix = tk.BooleanVar(value=True)
        chk_autofix = tk.Checkbutton(
            action_bar,
            text="Auto-Apply Lore Glossary (Fix Star Abyss -> Ateraxis, Sextant -> Sextans, etc.)",
            variable=self.var_autofix,
            bg=BG_CARD,
            fg=FG_MAIN,
            activebackground=BG_CARD,
            selectcolor=BG_INPUT,
            font=("Segoe UI", 9)
        )
        chk_autofix.pack(side=tk.LEFT)

        self.btn_run_update = tk.Button(
            action_bar,
            text="🚀 RUN FULL UPDATE PIPELINE",
            command=self._start_full_update,
            bg=ACCENT_ORANGE,
            fg="#ffffff",
            activebackground="#d95d14",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=20,
            pady=8,
            cursor="hand2"
        )
        self.btn_run_update.pack(side=tk.RIGHT)

        # Progress bar
        self.updater_progress = ttk.Progressbar(container, style="Horizontal.TProgressbar", mode="indeterminate")
        self.updater_progress.pack(fill=tk.X, pady=(0, 10))

        # Log Window
        log_label_frame = tk.Frame(container, bg=BG_CARD)
        log_label_frame.pack(fill=tk.X)
        tk.Label(log_label_frame, text="Execution Log Console:", font=("Segoe UI", 9, "bold"), fg=FG_MUTED, bg=BG_CARD).pack(side=tk.LEFT)
        btn_clear_log = tk.Button(log_label_frame, text="Clear Log", command=self._clear_updater_log, bg=BG_CARD, fg=FG_MUTED, relief="flat", font=("Segoe UI", 8), cursor="hand2")
        btn_clear_log.pack(side=tk.RIGHT)

        self.log_text = tk.Text(
            container,
            bg="#0f0f16",
            fg="#38bdf8",
            insertbackground="#ffffff",
            font=("Consolas", 9),
            height=12,
            relief="flat",
            wrap=tk.WORD,
            padx=10,
            pady=8
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

    def _choose_updater_input(self):
        filename = filedialog.askopenfilename(
            title="Select New Chinese Game File (LangPackageTableCnData.bytes)",
            filetypes=[("GFL2 Table Binary (*.bytes)", "*.bytes"), ("All Files (*.*)", "*.*")],
            initialdir=str(BASE_DIR)
        )
        if filename:
            self.updater_input_entry.delete(0, tk.END)
            self.updater_input_entry.insert(0, filename)

    def _choose_updater_output(self):
        filename = filedialog.asksaveasfilename(
            title="Select Output Destination for Translated Game File",
            filetypes=[("GFL2 Table Binary (*.bytes)", "*.bytes"), ("All Files (*.*)", "*.*")],
            defaultextension=".bytes",
            initialfile="LangPackageTableCnData.bytes",
            initialdir=str(DEFAULT_OUTPUT_DIR)
        )
        if filename:
            self.updater_output_entry.delete(0, tk.END)
            self.updater_output_entry.insert(0, filename)

    def _clear_updater_log(self):
        self.log_text.delete("1.0", tk.END)

    def _start_full_update(self):
        in_file = Path(self.updater_input_entry.get().strip())
        out_file = Path(self.updater_output_entry.get().strip())
        auto_fix = self.var_autofix.get()

        if not in_file.exists():
            messagebox.showerror("Error", f"Input file not found:\n{in_file}\n\nPlease select a valid .bytes file.")
            return

        self.btn_run_update.config(state=tk.DISABLED)
        self.updater_progress.start(10)

        def worker():
            try:
                self.log(f"[{datetime.now().strftime('%H:%M:%S')}] Starting Full Game Update Pipeline...")
                self.log(f"Source file: {in_file.name} ({in_file.stat().st_size / (1024*1024):.2f} MB)")
                self.log(f"Destination: {out_file}")

                DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                exported_cn = DEFAULT_OUTPUT_DIR / "translations.json"
                target_en = DEFAULT_OUTPUT_DIR / "translations_eng.json"
                untranslated_file = DEFAULT_OUTPUT_DIR / "untranslated.json"

                # Step 1: Export .bytes -> translations.json
                self.log("\n[Step 1/4] Exporting strings from .bytes file...")
                if exported_cn.exists():
                    exported_cn.unlink()
                total_entries, _ = langpackage_export.export_table(in_file, exported_cn)
                self.log(f"✓ Exported {total_entries:,} Chinese strings to {exported_cn.name}")

                # Step 2: Match with Translation Memory
                self.log("\n[Step 2/4] Matching against Translation Memory database...")
                db = gfl2_translation_sync.TranslationMemory(DEFAULT_DB)
                total, matched, untrans = gfl2_translation_sync.sync_and_translate(
                    input_cn_path=exported_cn,
                    output_en_path=target_en,
                    untranslated_path=untranslated_file,
                    db=db,
                    auto_translate_new=False
                )
                ratio = (matched / total * 100) if total > 0 else 0
                self.log(f"✓ Matched {matched:,} / {total:,} ({ratio:.2f}%) strings successfully!")
                if untrans > 0:
                    self.log(f"ℹ Found {untrans:,} new/untranslated strings. Saved to untranslated_chunks/ for translation.")

                # Step 3: Lore Glossary Audit & Auto-Fix
                if auto_fix:
                    self.log("\n[Step 3/4] Running Lore Glossary audit & auto-fixer...")
                    report = apply_glossary.audit_and_fix(DEFAULT_DB, target_en, exported_cn, dry_run=False)
                    self.log("✓ Lore glossary audit complete. All official terms enforced!")

                # Step 4: Rebuild .bytes
                self.log(f"\n[Step 4/4] Compiling final game binary package: {out_file.name}...")
                out_file.parent.mkdir(parents=True, exist_ok=True)
                if out_file.exists():
                    out_file.unlink()
                tot, sup, chg = langpackage_import.import_table(in_file, target_en, out_file)
                self.log(f"✓ Successfully wrote: {out_file}")
                self.log(f"✓ {chg:,} of {tot:,} entries updated in binary table!")
                self.log(f"\n🎉 SUCCESS! Your playable English game file is ready:\n{out_file}")

                self.after(0, lambda: messagebox.showinfo("Update Complete", f"Successfully built translated game file:\n\n{out_file}\n\nCopy this file to your game directory!"))
            except Exception as exc:
                self.log(f"\n❌ ERROR: {exc}")
                self.after(0, lambda err=exc: messagebox.showerror("Pipeline Error", f"An error occurred:\n\n{err}"))
            finally:
                self.after(0, self._finish_update_ui)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_update_ui(self):
        self.updater_progress.stop()
        self.btn_run_update.config(state=tk.NORMAL)
        self.refresh_database_stats()
        self.refresh_chunks_list()

    # ==========================================================================
    # Tab 2: First-Time Setup (Build Database)
    # ==========================================================================
    def _init_tab_setup(self):
        container = tk.Frame(self.tab_setup, bg=BG_CARD)
        container.pack(fill=tk.BOTH, expand=True, padx=25, pady=20)

        tk.Label(
            container,
            text="First-Time Database Initialization",
            font=("Segoe UI", 13, "bold"),
            fg=FG_MAIN,
            bg=BG_CARD
        ).pack(anchor=tk.W, pady=(0, 2))

        tk.Label(
            container,
            text="If you just cloned this project and have no database yet, pair the original Chinese .bytes file with your English mod .bytes file from the SAME game version to generate your personal translation database in seconds.",
            font=("Segoe UI", 9),
            fg=FG_MUTED,
            bg=BG_CARD,
            wraplength=850,
            justify=tk.LEFT
        ).pack(anchor=tk.W, pady=(0, 20))

        box = tk.Frame(container, bg=BG_CARD_LIGHT, padx=20, pady=20, highlightthickness=1, highlightbackground=BORDER_COLOR)
        box.pack(fill=tk.X, pady=(0, 20))

        # Chinese File
        f1 = tk.Frame(box, bg=BG_CARD_LIGHT)
        f1.pack(fill=tk.X, pady=8)
        tk.Label(f1, text="Chinese Base File (.bytes):", font=("Segoe UI", 10, "bold"), fg=FG_MAIN, bg=BG_CARD_LIGHT, width=24, anchor=tk.W).pack(side=tk.LEFT)
        self.setup_cn_entry = tk.Entry(f1, bg=BG_INPUT, fg=FG_MAIN, insertbackground=FG_MAIN, relief="flat", font=("Segoe UI", 10))
        self.setup_cn_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 10), ipady=4)
        tk.Button(f1, text="📁 Choose Chinese...", command=self._choose_setup_cn, bg="#2c2c3e", fg=FG_MAIN, relief="flat", padx=12, pady=4, cursor="hand2").pack(side=tk.RIGHT)

        # English File
        f2 = tk.Frame(box, bg=BG_CARD_LIGHT)
        f2.pack(fill=tk.X, pady=8)
        tk.Label(f2, text="English Mod File (.bytes):", font=("Segoe UI", 10, "bold"), fg=FG_MAIN, bg=BG_CARD_LIGHT, width=24, anchor=tk.W).pack(side=tk.LEFT)
        self.setup_en_entry = tk.Entry(f2, bg=BG_INPUT, fg=FG_MAIN, insertbackground=FG_MAIN, relief="flat", font=("Segoe UI", 10))
        self.setup_en_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 10), ipady=4)
        tk.Button(f2, text="📁 Choose English...", command=self._choose_setup_en, bg="#2c2c3e", fg=FG_MAIN, relief="flat", padx=12, pady=4, cursor="hand2").pack(side=tk.RIGHT)

        # Action Button
        self.btn_build_db = tk.Button(
            container,
            text="⚡ BUILD TRANSLATION MEMORY DATABASE",
            command=self._start_build_database,
            bg=ACCENT_BLUE,
            fg="#ffffff",
            activebackground="#2563eb",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=25,
            pady=10,
            cursor="hand2"
        )
        self.btn_build_db.pack(anchor=tk.W, pady=(0, 15))

        self.setup_log = tk.Text(
            container,
            bg="#0f0f16",
            fg="#38bdf8",
            insertbackground="#ffffff",
            font=("Consolas", 9),
            height=10,
            relief="flat",
            wrap=tk.WORD,
            padx=10,
            pady=8
        )
        self.setup_log.pack(fill=tk.BOTH, expand=True)

    def _choose_setup_cn(self):
        f = filedialog.askopenfilename(
            title="Select Chinese .bytes File",
            filetypes=[("GFL2 Table Binary (*.bytes)", "*.bytes"), ("All Files (*.*)", "*.*")],
            initialdir=str(BASE_DIR)
        )
        if f:
            self.setup_cn_entry.delete(0, tk.END)
            self.setup_cn_entry.insert(0, f)

    def _choose_setup_en(self):
        f = filedialog.askopenfilename(
            title="Select English Mod .bytes File (Same Version)",
            filetypes=[("GFL2 Table Binary (*.bytes)", "*.bytes"), ("All Files (*.*)", "*.*")],
            initialdir=str(BASE_DIR)
        )
        if f:
            self.setup_en_entry.delete(0, tk.END)
            self.setup_en_entry.insert(0, f)

    def _start_build_database(self):
        cn_file = Path(self.setup_cn_entry.get().strip())
        en_file = Path(self.setup_en_entry.get().strip())

        if not cn_file.exists() or not en_file.exists():
            messagebox.showerror("Error", "Please select BOTH matching Chinese and English .bytes files.")
            return

        self.btn_build_db.config(state=tk.DISABLED)

        def worker():
            try:
                self._setup_log(f"Starting Database Build from matching files...")
                temp_dir = DEFAULT_OUTPUT_DIR / "temp_setup"
                temp_dir.mkdir(parents=True, exist_ok=True)

                cn_json = temp_dir / "temp_cn.json"
                en_json = temp_dir / "temp_en.json"

                self._setup_log(f"Extracting Chinese strings from {cn_file.name}...")
                if cn_json.exists(): cn_json.unlink()
                langpackage_export.export_table(cn_file, cn_json)

                self._setup_log(f"Extracting English strings from {en_file.name}...")
                if en_json.exists(): en_json.unlink()
                langpackage_export.export_table(en_file, en_json)

                self._setup_log(f"Building Translation Memory database: {DEFAULT_DB.name}...")
                count = gfl2_translation_sync.build_database_from_files(cn_json, en_json, DEFAULT_DB)

                self._setup_log(f"Importing lore rules from database_source/glossary.json...")
                apply_glossary.get_connection(DEFAULT_DB)

                self._setup_log(f"\n✓ SUCCESS! Stored {count:,} translation pairs in database!")
                self.after(0, lambda: messagebox.showinfo("Build Complete", f"Successfully built database with {count:,} translation pairs!\n\nDatabase: {DEFAULT_DB.name}"))
            except Exception as e:
                self._setup_log(f"❌ Error: {e}")
                self.after(0, lambda err=e: messagebox.showerror("Error", str(err)))
            finally:
                self.after(0, lambda: self.btn_build_db.config(state=tk.NORMAL))
                self.refresh_database_stats()
                self.refresh_glossary_table()

        threading.Thread(target=worker, daemon=True).start()

    def _setup_log(self, msg: str):
        self.setup_log.insert(tk.END, msg + "\n")
        self.setup_log.see(tk.END)

    # ==========================================================================
    # Tab 3: Lore Glossary Manager
    # ==========================================================================
    def _init_tab_glossary(self):
        container = tk.Frame(self.tab_glossary, bg=BG_CARD)
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)

        # Toolbar
        toolbar = tk.Frame(container, bg=BG_CARD)
        toolbar.pack(fill=tk.X, pady=(0, 10))

        tk.Label(toolbar, text="Search Term:", font=("Segoe UI", 10), fg=FG_MUTED, bg=BG_CARD).pack(side=tk.LEFT, padx=(0, 5))
        self.glossary_search_entry = tk.Entry(toolbar, bg=BG_INPUT, fg=FG_MAIN, insertbackground=FG_MAIN, relief="flat", font=("Segoe UI", 10), width=25)
        self.glossary_search_entry.pack(side=tk.LEFT, padx=(0, 15), ipady=3)
        self.glossary_search_entry.bind("<KeyRelease>", lambda e: self.filter_glossary())

        btn_autofix = tk.Button(
            toolbar,
            text="✨ Audit & Auto-Fix Translations",
            command=self._glossary_autofix,
            bg=ACCENT_ORANGE,
            fg="#ffffff",
            relief="flat",
            padx=12,
            pady=4,
            cursor="hand2",
            font=("Segoe UI", 9, "bold")
        )
        btn_autofix.pack(side=tk.LEFT, padx=5)

        btn_add = tk.Button(
            toolbar,
            text="➕ Add New Term",
            command=self._open_add_term_modal,
            bg=ACCENT_BLUE,
            fg="#ffffff",
            relief="flat",
            padx=12,
            pady=4,
            cursor="hand2",
            font=("Segoe UI", 9, "bold")
        )
        btn_add.pack(side=tk.LEFT, padx=5)

        btn_exp = tk.Button(
            toolbar,
            text="📤 Export JSON",
            command=self._glossary_export_modal,
            bg="#2c2c3e",
            fg=FG_MAIN,
            relief="flat",
            padx=10,
            pady=4,
            cursor="hand2"
        )
        btn_exp.pack(side=tk.RIGHT, padx=4)

        btn_imp = tk.Button(
            toolbar,
            text="📥 Import JSON",
            command=self._glossary_import_modal,
            bg="#2c2c3e",
            fg=FG_MAIN,
            relief="flat",
            padx=10,
            pady=4,
            cursor="hand2"
        )
        btn_imp.pack(side=tk.RIGHT, padx=4)

        # Treeview (Glossary Table)
        columns = ("cn", "en", "category", "bads", "context")
        self.tree_glossary = ttk.Treeview(container, columns=columns, show="headings", selectmode="browse")
        self.tree_glossary.heading("cn", text="Chinese Term")
        self.tree_glossary.heading("en", text="Official English Translation")
        self.tree_glossary.heading("category", text="Category")
        self.tree_glossary.heading("bads", text="Banned / Bad Translations Automatically Replaced")
        self.tree_glossary.heading("context", text="Context / Exclusions")

        self.tree_glossary.column("cn", width=140, anchor=tk.W)
        self.tree_glossary.column("en", width=180, anchor=tk.W)
        self.tree_glossary.column("category", width=110, anchor=tk.W)
        self.tree_glossary.column("bads", width=280, anchor=tk.W)
        self.tree_glossary.column("context", width=180, anchor=tk.W)

        tree_scroll = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.tree_glossary.yview)
        self.tree_glossary.configure(yscrollcommand=tree_scroll.set)

        self.tree_glossary.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def refresh_glossary_table(self):
        if not DEFAULT_DB.exists():
            return
        for item in self.tree_glossary.get_children():
            self.tree_glossary.delete(item)

        try:
            with apply_glossary.get_connection(DEFAULT_DB) as conn:
                rows = conn.execute("SELECT source_cn, target_en, bad_translations, exclusions, category, speaker_context FROM glossary ORDER BY category, source_cn;").fetchall()
                for r in rows:
                    cn, en, bad_json, exc_json, cat, ctx = r
                    bads = json.loads(bad_json) if bad_json else []
                    excs = json.loads(exc_json) if exc_json else []
                    bad_str = ", ".join(bads) if bads else "-"
                    ctx_str = ctx if ctx else ("Excludes: " + ", ".join(excs) if excs else "-")
                    self.tree_glossary.insert("", tk.END, values=(cn, en, cat, bad_str, ctx_str))
        except Exception:
            pass

    def filter_glossary(self):
        query = self.glossary_search_entry.get().lower().strip()
        self.refresh_glossary_table()
        if not query:
            return
        for item in self.tree_glossary.get_children():
            vals = [str(v).lower() for v in self.tree_glossary.item(item, "values")]
            if not any(query in v for v in vals):
                self.tree_glossary.detach(item)

    def _glossary_autofix(self):
        target_en = DEFAULT_OUTPUT_DIR / "translations_eng.json"
        base_cn = DEFAULT_OUTPUT_DIR / "translations.json"
        if not target_en.exists():
            messagebox.showwarning("Notice", f"Target file not found:\n{target_en}\n\nPlease run the Patch Updater first.")
            return

        def worker():
            try:
                self.log(f"[{datetime.now().strftime('%H:%M:%S')}] Auditing Lore Glossary rules against database and translations_eng.json...")
                report = apply_glossary.audit_and_fix(DEFAULT_DB, target_en, base_cn, dry_run=False)
                self.after(0, lambda: messagebox.showinfo("Audit Complete", "Glossary audit and auto-fix complete!\nAll official GFL2 lore terms are enforced."))
            except Exception as e:
                self.after(0, lambda err=e: messagebox.showerror("Error", str(err)))

        threading.Thread(target=worker, daemon=True).start()

    def _open_add_term_modal(self):
        modal = tk.Toplevel(self)
        modal.title("Add / Edit Lore Glossary Term")
        modal.geometry("520x460")
        modal.configure(bg=BG_CARD)
        modal.transient(self)
        modal.grab_set()

        tk.Label(modal, text="Glossary Term Details", font=("Segoe UI", 12, "bold"), fg=FG_MAIN, bg=BG_CARD).pack(anchor=tk.W, padx=20, pady=(15, 10))

        f = tk.Frame(modal, bg=BG_CARD)
        f.pack(fill=tk.BOTH, expand=True, padx=20)

        def make_row(lbl_text):
            r = tk.Frame(f, bg=BG_CARD)
            r.pack(fill=tk.X, pady=4)
            tk.Label(r, text=lbl_text, width=20, anchor=tk.W, font=("Segoe UI", 9, "bold"), fg=FG_MUTED, bg=BG_CARD).pack(side=tk.LEFT)
            e = tk.Entry(r, bg=BG_INPUT, fg=FG_MAIN, insertbackground=FG_MAIN, relief="flat", font=("Segoe UI", 10))
            e.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)
            return e

        e_cn = make_row("Chinese Source Term:")
        e_en = make_row("Official English:")
        e_bads = make_row("Banned Translations (comma-separated):")
        e_excs = make_row("Exclusions (comma-separated):")
        e_cat = make_row("Category:")
        e_ctx = make_row("Context / Speaker:")

        e_cat.insert(0, "General")

        def save_term():
            cn = e_cn.get().strip()
            en = e_en.get().strip()
            if not cn or not en:
                messagebox.showerror("Validation Error", "Both Chinese and English terms are required.", parent=modal)
                return
            bads = [b.strip() for b in e_bads.get().split(",") if b.strip()]
            excs = [x.strip() for x in e_excs.get().split(",") if x.strip()]
            cat = e_cat.get().strip() or "General"
            ctx = e_ctx.get().strip() or None

            apply_glossary.add_term(DEFAULT_DB, cn, en, bads, excs, cat, ctx)
            modal.destroy()
            self.refresh_glossary_table()
            messagebox.showinfo("Saved", f"Term saved to database:\n{cn} -> {en}")

        btn_box = tk.Frame(modal, bg=BG_CARD)
        btn_box.pack(fill=tk.X, padx=20, pady=15)
        tk.Button(btn_box, text="Save to Database", command=save_term, bg=ACCENT_GREEN, fg="#ffffff", relief="flat", padx=16, pady=6, cursor="hand2", font=("Segoe UI", 9, "bold")).pack(side=tk.RIGHT, padx=5)
        tk.Button(btn_box, text="Cancel", command=modal.destroy, bg="#2c2c3e", fg=FG_MAIN, relief="flat", padx=14, pady=6, cursor="hand2").pack(side=tk.RIGHT)

    def _glossary_export_modal(self):
        f = filedialog.asksaveasfilename(
            title="Export Glossary to JSON",
            filetypes=[("JSON Files (*.json)", "*.json")],
            defaultextension=".json",
            initialfile="glossary.json",
            initialdir=str(DEFAULT_GLOSSARY_JSON.parent)
        )
        if f:
            apply_glossary.export_terms(DEFAULT_DB, Path(f))
            messagebox.showinfo("Exported", f"Successfully exported glossary to:\n{f}")

    def _glossary_import_modal(self):
        f = filedialog.askopenfilename(
            title="Import Glossary from JSON",
            filetypes=[("JSON Files (*.json)", "*.json")],
            initialdir=str(DEFAULT_GLOSSARY_JSON.parent)
        )
        if f:
            apply_glossary.import_terms(DEFAULT_DB, Path(f))
            self.refresh_glossary_table()
            messagebox.showinfo("Imported", f"Successfully imported glossary from:\n{f}")

    # ==========================================================================
    # Tab 4: Untranslated Chunks & AI Tool
    # ==========================================================================
    def _init_tab_chunks(self):
        container = tk.Frame(self.tab_chunks, bg=BG_CARD)
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)

        # Header
        tk.Label(container, text="Untranslated Chunks Manager", font=("Segoe UI", 13, "bold"), fg=FG_MAIN, bg=BG_CARD).pack(anchor=tk.W, pady=(0, 2))
        tk.Label(container, text="When the game updates, new strings are split into ~250-line chunks for AI translation. Copy them to ChatGPT/Claude, then import them back.", font=("Segoe UI", 9), fg=FG_MUTED, bg=BG_CARD).pack(anchor=tk.W, pady=(0, 12))

        paned = tk.PanedWindow(container, orient=tk.HORIZONTAL, bg=BG_CARD, sashrelief="flat", sashwidth=6)
        paned.pack(fill=tk.BOTH, expand=True)

        # Left pane: Chunk List
        left = tk.Frame(paned, bg=BG_CARD_LIGHT, padx=10, pady=10)
        paned.add(left, width=280)

        tk.Label(left, text="Available Chunks:", font=("Segoe UI", 10, "bold"), fg=FG_MAIN, bg=BG_CARD_LIGHT).pack(anchor=tk.W, pady=(0, 5))
        self.chunks_listbox = tk.Listbox(left, bg=BG_INPUT, fg=FG_MAIN, selectbackground=ACCENT_BLUE, relief="flat", font=("Consolas", 10))
        self.chunks_listbox.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        self.chunks_listbox.bind("<<ListboxSelect>>", self._on_chunk_selected)

        btn_refresh_chunks = tk.Button(left, text="🔄 Refresh Chunks List", command=self.refresh_chunks_list, bg="#2c2c3e", fg=FG_MAIN, relief="flat", pady=4, cursor="hand2")
        btn_refresh_chunks.pack(fill=tk.X)

        # Right pane: Preview & Actions
        right = tk.Frame(paned, bg=BG_CARD, padx=15)
        paned.add(right)

        btn_bar = tk.Frame(right, bg=BG_CARD)
        btn_bar.pack(fill=tk.X, pady=(0, 8))

        btn_copy = tk.Button(
            btn_bar,
            text="📋 Copy Chunk to Clipboard (for ChatGPT)",
            command=self._copy_selected_chunk,
            bg=ACCENT_ORANGE,
            fg="#ffffff",
            relief="flat",
            padx=12,
            pady=5,
            cursor="hand2",
            font=("Segoe UI", 9, "bold")
        )
        btn_copy.pack(side=tk.LEFT, padx=(0, 8))

        btn_imp_single = tk.Button(
            btn_bar,
            text="📥 Import Selected Chunk",
            command=self._import_selected_chunk,
            bg=ACCENT_GREEN,
            fg="#ffffff",
            relief="flat",
            padx=12,
            pady=5,
            cursor="hand2",
            font=("Segoe UI", 9, "bold")
        )
        btn_imp_single.pack(side=tk.LEFT, padx=8)

        btn_imp_all = tk.Button(
            btn_bar,
            text="📥 Import ALL Chunks in Folder",
            command=self._import_all_chunks,
            bg="#2c2c3e",
            fg=FG_MAIN,
            relief="flat",
            padx=12,
            pady=5,
            cursor="hand2"
        )
        btn_imp_all.pack(side=tk.RIGHT)

        self.chunk_preview_text = tk.Text(
            right,
            bg="#0f0f16",
            fg="#38bdf8",
            insertbackground="#ffffff",
            font=("Consolas", 9),
            relief="flat",
            wrap=tk.WORD,
            padx=10,
            pady=8
        )
        self.chunk_preview_text.pack(fill=tk.BOTH, expand=True)

    def refresh_chunks_list(self):
        self.chunks_listbox.delete(0, tk.END)
        chunks_dir = DEFAULT_OUTPUT_DIR / "untranslated_chunks"
        if chunks_dir.exists():
            files = sorted(chunks_dir.glob("chunk_*.json"))
            for f in files:
                self.chunks_listbox.insert(tk.END, f.name)
        if self.chunks_listbox.size() > 0:
            self.chunks_listbox.select_set(0)
            self._on_chunk_selected(None)

    def _on_chunk_selected(self, event):
        sel = self.chunks_listbox.curselection()
        if not sel:
            return
        filename = self.chunks_listbox.get(sel[0])
        chunk_path = DEFAULT_OUTPUT_DIR / "untranslated_chunks" / filename
        if chunk_path.exists():
            with chunk_path.open("r", encoding="utf-8") as f:
                content = f.read()
            self.chunk_preview_text.delete("1.0", tk.END)
            self.chunk_preview_text.insert(tk.END, content)

    def _copy_selected_chunk(self):
        content = self.chunk_preview_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("Notice", "No chunk selected to copy.")
            return
        self.clipboard_clear()
        self.clipboard_append(content)
        messagebox.showinfo("Copied", "Chunk content copied to clipboard!\n\nPaste it into ChatGPT or Claude to translate.")

    def _import_selected_chunk(self):
        sel = self.chunks_listbox.curselection()
        if not sel:
            return
        filename = self.chunks_listbox.get(sel[0])
        chunk_path = DEFAULT_OUTPUT_DIR / "untranslated_chunks" / filename
        target_en = DEFAULT_OUTPUT_DIR / "translations_eng.json"

        count = gfl2_translation_sync.import_translated_file(chunk_path, DEFAULT_DB, target_en)
        self.refresh_database_stats()
        messagebox.showinfo("Imported", f"Successfully imported {count:,} translations from {filename} into database and translations_eng.json!")

    def _import_all_chunks(self):
        chunks_dir = DEFAULT_OUTPUT_DIR / "untranslated_chunks"
        target_en = DEFAULT_OUTPUT_DIR / "translations_eng.json"
        if not chunks_dir.exists():
            messagebox.showwarning("Notice", "Chunks directory not found.")
            return

        count = gfl2_translation_sync.import_translated_file(chunks_dir, DEFAULT_DB, target_en)
        self.refresh_database_stats()
        messagebox.showinfo("Imported", f"Successfully imported {count:,} translations from all chunk files into database and translations_eng.json!")

    # ==========================================================================
    # Tab 5: Database & Tools
    # ==========================================================================
    def _init_tab_tools(self):
        container = tk.Frame(self.tab_tools, bg=BG_CARD)
        container.pack(fill=tk.BOTH, expand=True, padx=25, pady=20)

        tk.Label(container, text="Translation Memory Database Info & Maintenance", font=("Segoe UI", 13, "bold"), fg=FG_MAIN, bg=BG_CARD).pack(anchor=tk.W, pady=(0, 5))

        # Stats Card
        stats_box = tk.Frame(container, bg=BG_CARD_LIGHT, padx=20, pady=20, highlightthickness=1, highlightbackground=BORDER_COLOR)
        stats_box.pack(fill=tk.X, pady=(0, 20))

        self.lbl_stat_count = tk.Label(stats_box, text="Total Translations: Loading...", font=("Segoe UI", 11, "bold"), fg=ACCENT_ORANGE, bg=BG_CARD_LIGHT)
        self.lbl_stat_count.pack(anchor=tk.W, pady=3)

        self.lbl_stat_glossary = tk.Label(stats_box, text="Total Lore Glossary Terms: Loading...", font=("Segoe UI", 10), fg=FG_MAIN, bg=BG_CARD_LIGHT)
        self.lbl_stat_glossary.pack(anchor=tk.W, pady=3)

        self.lbl_stat_size = tk.Label(stats_box, text="Database File Size: Loading...", font=("Segoe UI", 10), fg=FG_MUTED, bg=BG_CARD_LIGHT)
        self.lbl_stat_size.pack(anchor=tk.W, pady=3)

        self.lbl_stat_path = tk.Label(stats_box, text=f"Location: {DEFAULT_DB}", font=("Segoe UI", 9), fg=FG_MUTED, bg=BG_CARD_LIGHT)
        self.lbl_stat_path.pack(anchor=tk.W, pady=3)

        # Action Buttons
        btn_grid = tk.Frame(container, bg=BG_CARD)
        btn_grid.pack(fill=tk.X, pady=10)

        tk.Button(btn_grid, text="💾 Backup Database to .ZIP", command=self._backup_database, bg=ACCENT_BLUE, fg="#ffffff", relief="flat", padx=16, pady=8, font=("Segoe UI", 10, "bold"), cursor="hand2").pack(side=tk.LEFT, padx=(0, 10))
        tk.Button(btn_grid, text="📤 Export DB to JSON", command=self._export_db_json, bg="#2c2c3e", fg=FG_MAIN, relief="flat", padx=14, pady=8, cursor="hand2").pack(side=tk.LEFT, padx=10)
        tk.Button(btn_grid, text="🧹 Optimize Database (VACUUM)", command=self._vacuum_database, bg="#2c2c3e", fg=FG_MAIN, relief="flat", padx=14, pady=8, cursor="hand2").pack(side=tk.LEFT, padx=10)

    def refresh_database_stats(self):
        if not DEFAULT_DB.exists():
            self.lbl_stat_count.config(text="Total Translations: 0 (Database not initialized)")
            self.lbl_stat_glossary.config(text="Total Lore Glossary Terms: 0")
            self.lbl_stat_size.config(text="Database File Size: 0 MB")
            return

        try:
            db = gfl2_translation_sync.TranslationMemory(DEFAULT_DB)
            count = db.count()
            size_mb = DEFAULT_DB.stat().st_size / (1024 * 1024)

            with db.get_connection() as conn:
                g_cnt = conn.execute("SELECT COUNT(*) FROM glossary;").fetchone()[0]

            self.lbl_stat_count.config(text=f"Total Learned Translations: {count:,} phrases")
            self.lbl_stat_glossary.config(text=f"Active Lore Glossary Rules: {g_cnt:,} terms")
            self.lbl_stat_size.config(text=f"Database File Size: {size_mb:.2f} MB (SQLite WAL mode)")
        except Exception:
            pass

    def _backup_database(self):
        if not DEFAULT_DB.exists():
            messagebox.showwarning("Notice", "No database to backup.")
            return

        dest = filedialog.asksaveasfilename(
            title="Choose Backup Destination",
            filetypes=[("ZIP Archive (*.zip)", "*.zip")],
            defaultextension=".zip",
            initialfile=f"translation_memory_backup_{datetime.now().strftime('%Y%m%d')}.zip",
            initialdir=str(BASE_DIR)
        )
        if dest:
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(DEFAULT_DB, arcname="translation_memory.db")
            messagebox.showinfo("Backup Created", f"Successfully backed up database to:\n{dest}")

    def _export_db_json(self):
        if not DEFAULT_DB.exists():
            messagebox.showwarning("Notice", "No database to export.")
            return

        dest = filedialog.asksaveasfilename(
            title="Choose Export Destination",
            filetypes=[("JSON File (*.json)", "*.json")],
            defaultextension=".json",
            initialfile="translations_memory_export.json",
            initialdir=str(BASE_DIR)
        )
        if dest:
            gfl2_translation_sync.export_database_to_file(DEFAULT_DB, Path(dest))
            messagebox.showinfo("Exported", f"Successfully exported database to:\n{dest}")

    def _vacuum_database(self):
        if not DEFAULT_DB.exists():
            return
        with sqlite3.connect(DEFAULT_DB) as conn:
            conn.execute("VACUUM;")
        self.refresh_database_stats()
        messagebox.showinfo("Optimized", "Database VACUUM and optimization complete!")

    # ==========================================================================
    # Statusbar & Thread Logging
    # ==========================================================================
    def _build_statusbar(self):
        status = tk.Frame(self, bg="#0d0d12", height=24)
        status.pack(fill=tk.X, side=tk.BOTTOM)

        self.lbl_status = tk.Label(status, text="Ready", font=("Segoe UI", 9), fg=FG_MUTED, bg="#0d0d12")
        self.lbl_status.pack(side=tk.LEFT, padx=15)

    def log(self, msg: str):
        self.log_queue.put(msg)

    def _process_log_queue(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get_nowait()
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
            self.lbl_status.config(text=msg.strip()[:80] if msg.strip() else "Ready")
        self.after(100, self._process_log_queue)


def main():
    app = GFL2TranslatorApp()
    app.mainloop()


if __name__ == "__main__":
    main()

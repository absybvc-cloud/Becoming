#!/usr/bin/env python3
"""
Unified GUI for Becoming.

Combines:
- Engine control (start/stop, state, tension, density, mutate)
- Sound ingest / harvest runner
- Auto-tag runner
- Library stats / quick status

This is a light orchestration UI around existing scripts/modules.
"""

from __future__ import annotations

import queue
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import sys
import os

# Ensure project root imports work no matter where this is launched from.
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.engine.library import SoundLibrary
from src.engine.states import STATE_NAMES


class UnifiedGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Becoming - Unified Control")
        self.geometry("1160x760")
        self.minsize(980, 640)

        self.engine_proc: subprocess.Popen | None = None
        self.engine_reader_thread: threading.Thread | None = None
        self.worker_threads: list[threading.Thread] = []

        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()

        self._build_style()
        self._build_ui()
        self.after(100, self._drain_log_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        bg = "#0f172a"
        panel = "#111827"
        fg = "#e5e7eb"
        accent = "#0ea5e9"

        self.configure(bg=bg)
        style.configure("TFrame", background=bg)
        style.configure("Panel.TFrame", background=panel)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("Title.TLabel", font=("Avenir Next", 16, "bold"), foreground="#f8fafc", background=bg)
        style.configure("CardTitle.TLabel", font=("Avenir Next", 12, "bold"), foreground="#f1f5f9", background=panel)
        style.configure("TButton", font=("Avenir Next", 11))
        style.configure("Accent.TButton", font=("Avenir Next", 11, "bold"))
        style.map("Accent.TButton", background=[("active", "#0284c7"), ("!disabled", accent)], foreground=[("!disabled", "white")])

        style.configure("TNotebook", background=bg, borderwidth=0)
        style.configure("TNotebook.Tab", font=("Avenir Next", 11, "bold"), padding=(14, 8))

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=14, pady=(12, 4))

        ttk.Label(top, text="Becoming", style="Title.TLabel").pack(side="left")
        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(top, textvariable=self.status_var).pack(side="right")

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=14, pady=(4, 8))

        self.engine_tab = ttk.Frame(notebook)
        self.ingest_tab = ttk.Frame(notebook)
        self.tag_tab = ttk.Frame(notebook)
        self.library_tab = ttk.Frame(notebook)

        notebook.add(self.engine_tab, text="Engine")
        notebook.add(self.ingest_tab, text="Ingest")
        notebook.add(self.tag_tab, text="Auto Tag")
        notebook.add(self.library_tab, text="Library")

        self._build_engine_tab()
        self._build_ingest_tab()
        self._build_tag_tab()
        self._build_library_tab()

        log_wrap = ttk.Frame(self)
        log_wrap.pack(fill="both", expand=False, padx=14, pady=(0, 12))
        ttk.Label(log_wrap, text="Live Log").pack(anchor="w")

        self.log_text = tk.Text(
            log_wrap,
            height=13,
            wrap="word",
            bg="#020617",
            fg="#e2e8f0",
            insertbackground="#e2e8f0",
            font=("Menlo", 11),
        )
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")

    def _build_engine_tab(self):
        frame = ttk.Frame(self.engine_tab)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        card = ttk.Frame(frame, style="Panel.TFrame")
        card.pack(fill="x", pady=(0, 10))

        inner = ttk.Frame(card)
        inner.pack(fill="x", padx=12, pady=12)

        ttk.Label(inner, text="Engine Controls", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=8, sticky="w", pady=(0, 8))

        ttk.Label(inner, text="Initial State").grid(row=1, column=0, sticky="w")
        self.state_var = tk.StringVar(value="submerged")
        ttk.Combobox(inner, textvariable=self.state_var, values=STATE_NAMES, state="readonly", width=14).grid(row=1, column=1, padx=6)

        ttk.Label(inner, text="Tension").grid(row=1, column=2, sticky="w")
        self.tension_var = tk.DoubleVar(value=0.3)
        ttk.Scale(inner, from_=0.0, to=1.0, variable=self.tension_var, orient="horizontal", length=170,
                  command=lambda _: self._auto_apply_slider("t", self.tension_var)).grid(row=1, column=3, padx=6)

        ttk.Label(inner, text="Density").grid(row=1, column=4, sticky="w")
        self.density_var = tk.DoubleVar(value=0.5)
        ttk.Scale(inner, from_=0.0, to=1.0, variable=self.density_var, orient="horizontal", length=170,
                  command=lambda _: self._auto_apply_slider("d", self.density_var)).grid(row=1, column=5, padx=6)

        ttk.Label(inner, text="Temperature").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.temperature_var = tk.DoubleVar(value=0.5)
        ttk.Scale(inner, from_=0.0, to=1.0, variable=self.temperature_var, orient="horizontal", length=170,
                  command=lambda _: self._auto_apply_slider("T", self.temperature_var)).grid(row=2, column=1, padx=6, pady=(8, 0))

        self.start_engine_btn = ttk.Button(inner, text="Start Engine", style="Accent.TButton", command=self._start_engine)
        self.start_engine_btn.grid(row=2, column=6, padx=(8, 4), pady=(8, 0))

        self.stop_engine_btn = ttk.Button(inner, text="Stop Engine", command=self._stop_engine)
        self.stop_engine_btn.grid(row=2, column=7, padx=(4, 0), pady=(8, 0))

        runtime = ttk.Frame(frame, style="Panel.TFrame")
        runtime.pack(fill="x")

        run_inner = ttk.Frame(runtime)
        run_inner.pack(fill="x", padx=12, pady=12)

        ttk.Label(run_inner, text="Runtime Commands", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=10, sticky="w", pady=(0, 8))

        ttk.Button(run_inner, text="Mutate Replace", command=lambda: self._send_engine_cmd("m")).grid(row=1, column=0, padx=4)
        ttk.Button(run_inner, text="Rare Silence", command=lambda: self._send_engine_cmd("!")).grid(row=1, column=1, padx=4)

        ttk.Label(run_inner, text="Force State").grid(row=1, column=2, padx=(18, 4), sticky="e")
        self.force_state_var = tk.StringVar(value="drifting")
        ttk.Combobox(run_inner, textvariable=self.force_state_var, values=STATE_NAMES, state="readonly", width=13).grid(row=1, column=3, padx=4)
        ttk.Button(run_inner, text="Apply", command=lambda: self._send_engine_cmd(f"s {self.force_state_var.get()}\n")).grid(row=1, column=4, padx=4)



    def _build_ingest_tab(self):
        frame = ttk.Frame(self.ingest_tab)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        card = ttk.Frame(frame, style="Panel.TFrame")
        card.pack(fill="x")

        inner = ttk.Frame(card)
        inner.pack(fill="x", padx=12, pady=12)

        ttk.Label(inner, text="Harvest / Ingest", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=8, sticky="w", pady=(0, 8))

        ttk.Label(inner, text="Limit / Query / Source").grid(row=1, column=0, sticky="w")

        self.ingest_limit_var = tk.IntVar(value=3)
        ttk.Spinbox(inner, from_=1, to=200, textvariable=self.ingest_limit_var, width=6).grid(row=1, column=1, padx=6)

        self.ingest_query_var = tk.StringVar(value="")
        ttk.Entry(inner, textvariable=self.ingest_query_var, width=36).grid(row=1, column=2, padx=6)

        self.ingest_source_var = tk.StringVar(value="all")
        ttk.Combobox(inner, textvariable=self.ingest_source_var, values=["all", "freesound", "internet_archive", "wikimedia"], state="readonly", width=16).grid(row=1, column=3, padx=6)

        self.ingest_category_var = tk.StringVar(value="")
        ttk.Entry(inner, textvariable=self.ingest_category_var, width=16).grid(row=1, column=4, padx=6)

        self.ingest_dry_run = tk.BooleanVar(value=False)
        ttk.Checkbutton(inner, text="Dry Run", variable=self.ingest_dry_run).grid(row=1, column=5, padx=6)

        self.ingest_auto_tag = tk.BooleanVar(value=True)
        ttk.Checkbutton(inner, text="Auto-tag", variable=self.ingest_auto_tag).grid(row=2, column=5, padx=6)

        ttk.Button(inner, text="Run Harvest", style="Accent.TButton", command=self._run_harvest).grid(row=1, column=6, padx=8)

        hint = (
            "Leave query empty to run default curated batch. "
            "Set category to filter default batch (e.g. drone, texture, field_recording)."
        )
        ttk.Label(inner, text=hint, wraplength=880).grid(row=2, column=0, columnspan=7, sticky="w", pady=(10, 2))

    def _build_tag_tab(self):
        frame = ttk.Frame(self.tag_tab)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        card = ttk.Frame(frame, style="Panel.TFrame")
        card.pack(fill="x")

        inner = ttk.Frame(card)
        inner.pack(fill="x", padx=12, pady=12)

        ttk.Label(inner, text="Auto Tag (Ollama)", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=8, sticky="w", pady=(0, 8))

        ttk.Label(inner, text="Model").grid(row=1, column=0, sticky="w")
        self.tag_model_var = tk.StringVar(value="qwen3-coder:30b")
        ttk.Entry(inner, textvariable=self.tag_model_var, width=28).grid(row=1, column=1, padx=6)

        ttk.Label(inner, text="Limit").grid(row=1, column=2, sticky="w")
        self.tag_limit_var = tk.IntVar(value=20)
        ttk.Spinbox(inner, from_=0, to=10000, textvariable=self.tag_limit_var, width=8).grid(row=1, column=3, padx=6)

        ttk.Label(inner, text="Asset ID (optional)").grid(row=1, column=4, sticky="w")
        self.tag_asset_id_var = tk.StringVar(value="")
        ttk.Entry(inner, textvariable=self.tag_asset_id_var, width=14).grid(row=1, column=5, padx=6)

        self.tag_retag_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(inner, text="Retag existing", variable=self.tag_retag_var).grid(row=1, column=6, padx=6)

        self.tag_dry_run_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(inner, text="Dry Run", variable=self.tag_dry_run_var).grid(row=1, column=7, padx=6)

        ttk.Button(inner, text="Run Auto Tag", style="Accent.TButton", command=self._run_auto_tag).grid(row=2, column=7, pady=(10, 0), sticky="e")

    def _build_library_tab(self):
        frame = ttk.Frame(self.library_tab)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        card = ttk.Frame(frame, style="Panel.TFrame")
        card.pack(fill="x")

        inner = ttk.Frame(card)
        inner.pack(fill="x", padx=12, pady=12)

        ttk.Label(inner, text="Library Snapshot", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))

        self.lib_summary_var = tk.StringVar(value="Not loaded yet")
        self.lib_detail_var = tk.StringVar(value="")

        ttk.Label(inner, textvariable=self.lib_summary_var, font=("Avenir Next", 13, "bold")).grid(row=1, column=0, sticky="w")
        ttk.Label(inner, textvariable=self.lib_detail_var, wraplength=880).grid(row=2, column=0, sticky="w", pady=(6, 10))

        row = ttk.Frame(inner)
        row.grid(row=3, column=0, sticky="w")

        ttk.Button(row, text="Refresh Stats", command=self._refresh_library).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Open Review Tool", command=self._open_review_tool).pack(side="left")

        # ── Balance / Rebalance card ────────────────────────────────────
        bal_card = ttk.Frame(frame, style="Panel.TFrame")
        bal_card.pack(fill="x", pady=(10, 0))

        bal_inner = ttk.Frame(bal_card)
        bal_inner.pack(fill="x", padx=12, pady=12)

        ttk.Label(bal_inner, text="Cluster Balance", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=6, sticky="w", pady=(0, 8))

        self.balance_text = tk.Text(
            bal_inner, height=12, wrap="word",
            bg="#020617", fg="#e2e8f0", font=("Menlo", 11),
        )
        self.balance_text.grid(row=1, column=0, columnspan=6, sticky="ew", pady=(0, 8))
        self.balance_text.configure(state="disabled")

        bal_row = ttk.Frame(bal_inner)
        bal_row.grid(row=2, column=0, columnspan=6, sticky="w")

        ttk.Button(bal_row, text="Analyze Balance", command=self._analyze_balance).pack(side="left", padx=(0, 8))

        ttk.Label(bal_row, text="Limit/query").pack(side="left", padx=(12, 4))
        self.rebalance_limit_var = tk.IntVar(value=5)
        ttk.Spinbox(bal_row, from_=1, to=50, textvariable=self.rebalance_limit_var, width=5).pack(side="left", padx=(0, 8))

        self.rebalance_auto_tag_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bal_row, text="Auto-tag", variable=self.rebalance_auto_tag_var).pack(side="left", padx=(0, 8))

        ttk.Button(bal_row, text="Rebalance Library", style="Accent.TButton", command=self._run_rebalance).pack(side="left", padx=(0, 8))
        ttk.Button(bal_row, text="Dry Run", command=self._run_rebalance_dry).pack(side="left")

        self._refresh_library()

    # ------------------------------------------------------------------
    # Engine actions
    # ------------------------------------------------------------------

    def _auto_apply_slider(self, cmd: str, var: tk.DoubleVar):
        """Send slider value to running engine automatically on change."""
        if self.engine_proc and self.engine_proc.poll() is None and self.engine_proc.stdin:
            try:
                self.engine_proc.stdin.write(f"{cmd} {var.get():.3f}\n")
                self.engine_proc.stdin.flush()
            except Exception:
                pass

    def _start_engine(self):
        if self.engine_proc and self.engine_proc.poll() is None:
            messagebox.showinfo("Engine", "Engine is already running.")
            return

        cmd = [
            str(ROOT / ".venv" / "bin" / "python"),
            str(ROOT / "engine.py"),
            "--state",
            self.state_var.get(),
            "--tension",
            f"{self.tension_var.get():.3f}",
            "--density",
            f"{self.density_var.get():.3f}",
            "--temperature",
            f"{self.temperature_var.get():.3f}",
        ]

        try:
            self.engine_proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as e:
            messagebox.showerror("Engine", f"Failed to start engine:\n{e}")
            return

        self.status_var.set("Engine running")
        self._log("engine", f"started: {' '.join(cmd)}")
        self._start_engine_output_reader()

    def _start_engine_output_reader(self):
        if not self.engine_proc or not self.engine_proc.stdout:
            return

        def read_loop():
            proc = self.engine_proc
            if not proc or not proc.stdout:
                return
            for line in proc.stdout:
                self.log_queue.put(("engine", line.rstrip("\n")))
            code = proc.poll()
            self.log_queue.put(("engine", f"[process exited code={code}]") )
            self.log_queue.put(("status", "Engine stopped"))

        self.engine_reader_thread = threading.Thread(target=read_loop, daemon=True)
        self.engine_reader_thread.start()

    def _send_engine_cmd(self, cmd: str):
        if not self.engine_proc or self.engine_proc.poll() is not None or not self.engine_proc.stdin:
            messagebox.showwarning("Engine", "Engine is not running.")
            return

        if not cmd.endswith("\n"):
            cmd = cmd + "\n"

        try:
            self.engine_proc.stdin.write(cmd)
            self.engine_proc.stdin.flush()
            self._log("engine", f"> {cmd.strip()}")
        except Exception as e:
            messagebox.showerror("Engine", f"Failed to send command:\n{e}")

    def _stop_engine(self):
        if not self.engine_proc or self.engine_proc.poll() is not None:
            self.status_var.set("Engine stopped")
            return

        try:
            if self.engine_proc.stdin:
                self.engine_proc.stdin.write("q\n")
                self.engine_proc.stdin.flush()
        except Exception:
            pass

        try:
            self.engine_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.engine_proc.terminate()

        self.status_var.set("Engine stopped")
        self._log("engine", "stop requested")

    # ------------------------------------------------------------------
    # Background command runners
    # ------------------------------------------------------------------

    def _run_harvest(self):
        cmd = [str(ROOT / ".venv" / "bin" / "python"), str(ROOT / "harvest_sounds.py"), "--limit", str(self.ingest_limit_var.get())]

        query = self.ingest_query_var.get().strip()
        source = self.ingest_source_var.get().strip()
        category = self.ingest_category_var.get().strip()

        if query:
            cmd.extend(["--queries", query])
        if source and source != "all":
            cmd.extend(["--source", source])
        if category:
            cmd.extend(["--category", category])
        if self.ingest_dry_run.get():
            cmd.append("--dry-run")
        if self.ingest_auto_tag.get():
            cmd.append("--auto-tag")

        self._run_cmd_async("harvest", cmd)

    def _run_auto_tag(self):
        cmd = [
            str(ROOT / ".venv" / "bin" / "python"),
            str(ROOT / "auto_tag.py"),
            "--model",
            self.tag_model_var.get().strip() or "qwen3-coder:30b",
            "--limit",
            str(self.tag_limit_var.get()),
        ]

        asset_id = self.tag_asset_id_var.get().strip()
        if asset_id:
            cmd.extend(["--asset-id", asset_id])
        if self.tag_retag_var.get():
            cmd.append("--retag")
        if self.tag_dry_run_var.get():
            cmd.append("--dry-run")

        self._run_cmd_async("auto_tag", cmd)

    def _run_cmd_async(self, label: str, cmd: list[str]):
        self._log(label, f"running: {' '.join(cmd)}")

        def worker():
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(ROOT),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                assert proc.stdout is not None
                for line in proc.stdout:
                    self.log_queue.put((label, line.rstrip("\n")))
                code = proc.wait()
                self.log_queue.put((label, f"[done exit={code}]") )
                if label == "harvest" and code == 0:
                    self.log_queue.put(("status", "Harvest complete"))
                elif label == "auto_tag" and code == 0:
                    self.log_queue.put(("status", "Auto-tag complete"))
            except Exception as e:
                self.log_queue.put((label, f"ERROR: {e}"))

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        self.worker_threads.append(t)

    # ------------------------------------------------------------------
    # Library / Review
    # ------------------------------------------------------------------

    def _refresh_library(self):
        try:
            lib = SoundLibrary()
            lib.load()
            summary = lib.summary()
            total = sum(summary.values())
            self.lib_summary_var.set(f"{total} sounds loaded")
            self.lib_detail_var.set(
                f"ground={summary.get('ground', 0)} | "
                f"texture={summary.get('texture', 0)} | "
                f"event={summary.get('event', 0)} | "
                f"pulse={summary.get('pulse', 0)}"
            )
            self._log("library", f"summary: total={total} {summary}")
        except Exception as e:
            self.lib_summary_var.set("Failed to load library")
            self.lib_detail_var.set(str(e))
            self._log("library", f"ERROR: {e}")

    def _open_review_tool(self):
        cmd = [str(ROOT / ".venv" / "bin" / "python"), "-m", "review_tool.gui"]
        self._run_cmd_async("review_tool", cmd)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log(self, source: str, line: str):
        self.log_queue.put((source, line))

    def _drain_log_queue(self):
        try:
            while True:
                source, line = self.log_queue.get_nowait()
                if source == "status":
                    self.status_var.set(line)
                    continue
                self._append_log_line(source, line)
        except queue.Empty:
            pass
        self.after(120, self._drain_log_queue)

    def _append_log_line(self, source: str, line: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{source}] {line}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Balance / Rebalance
    # ------------------------------------------------------------------

    def _analyze_balance(self):
        """Run balance analysis and display in the text widget."""
        def worker():
            try:
                from balance import analyze_balance, get_db
                db = get_db()
                report = analyze_balance(db)

                lines = []
                lines.append(f"Total assets: {report['total']}")
                lines.append(f"Entropy: {report['entropy']:.3f} / {report['max_entropy']:.3f}")
                lines.append(f"Balance score: {report['balance_score']:.1%}")
                lines.append("")

                for name in sorted(report["clusters"], key=lambda n: -report["clusters"][n]["count"]):
                    s = report["clusters"][name]
                    bar = "█" * int(s["pct"] / 2)
                    deficit_str = f"  (need +{s['deficit']})" if s["deficit"] > 0 else ""
                    lines.append(f"  {name:<20s} {s['count']:>4d}  {s['pct']:5.1f}%  {bar}{deficit_str}")

                if report["underrepresented"]:
                    lines.append("")
                    lines.append("⚠ Under-represented clusters:")
                    for item in report["underrepresented"]:
                        lines.append(f"  {item['cluster']}: {item['count']} sounds (need +{item['deficit']})")
                else:
                    lines.append("")
                    lines.append("✓ All clusters are reasonably balanced")

                text = "\n".join(lines)
                self.after(0, lambda: self._set_balance_text(text))
                self.log_queue.put(("balance", f"analysis complete — balance={report['balance_score']:.1%}"))
            except Exception as e:
                self.after(0, lambda: self._set_balance_text(f"ERROR: {e}"))
                self.log_queue.put(("balance", f"ERROR: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def _set_balance_text(self, text: str):
        self.balance_text.configure(state="normal")
        self.balance_text.delete("1.0", "end")
        self.balance_text.insert("1.0", text)
        self.balance_text.configure(state="disabled")

    def _run_rebalance(self):
        self._run_rebalance_cmd(dry_run=False)

    def _run_rebalance_dry(self):
        self._run_rebalance_cmd(dry_run=True)

    def _run_rebalance_cmd(self, dry_run: bool = False):
        cmd = [
            str(ROOT / ".venv" / "bin" / "python"),
            str(ROOT / "balance.py"),
            "--rebalance",
            "--limit", str(self.rebalance_limit_var.get()),
        ]
        if self.rebalance_auto_tag_var.get():
            cmd.append("--auto-tag")
        if dry_run:
            cmd.append("--dry-run")
        self._run_cmd_async("rebalance", cmd)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def _on_close(self):
        try:
            self._stop_engine()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    app = UnifiedGUI()
    app.mainloop()

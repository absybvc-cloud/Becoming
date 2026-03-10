import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from review_tool.loader import load_from_db, load_from_manifest
from review_tool.models import ReviewAsset, ReviewRecord
from review_tool.writer import save_review, load_last_review

ROLES = ["", "pulse", "drift", "texture", "accent", "pad", "rhythm", "noise", "field"]
DECISIONS = ["keep", "maybe", "reject", "skip"]



def _make_btn(parent, text, command, bg="#c0392b", fg="#ffffff", font=("Helvetica", 12, "bold"), padx=18, pady=8):
    """Canvas-based button that respects bg color on macOS."""
    f = tk.Frame(parent, bg=bg, cursor="hand2")
    lbl = tk.Label(f, text=text, bg=bg, fg=fg, font=font,
                   padx=padx, pady=pady, cursor="hand2")
    lbl.pack()
    def on_click(e=None):
        command()
    def on_enter(e):
        f.config(bg="#e74c3c")
        lbl.config(bg="#e74c3c")
    def on_leave(e):
        f.config(bg=bg)
        lbl.config(bg=bg)
    f.bind("<Button-1>", on_click)
    lbl.bind("<Button-1>", on_click)
    f.bind("<Enter>", on_enter)
    lbl.bind("<Enter>", on_enter)
    f.bind("<Leave>", on_leave)
    lbl.bind("<Leave>", on_leave)
    return f, lbl

class ReviewGUI(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Becoming - Review Tool")
        self.geometry("820x620")
        self.configure(bg="#1a1a1a")
        self.resizable(True, True)
        self._assets = []
        self._index = 0
        self._show_approved = tk.BooleanVar(value=True)
        self._play_proc = None
        self._build_menu()
        self._build_ui()
        self._load_assets()
        self.bind("<Right>", lambda e: self._save_and_next())
        self.bind("<Left>", lambda e: self._prev())

    def _build_menu(self):
        menubar = tk.Menu(self, bg="#2a2a2a", fg="white")
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_checkbutton(
            label="Show approved assets",
            variable=self._show_approved,
            command=self._load_assets,
        )
        menubar.add_cascade(label="View", menu=view_menu)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Reload", command=self._load_assets)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        self.config(menu=menubar)

    def _build_ui(self):
        BG, FG, ACC, CARD = "#1a1a1a", "#e0e0e0", "#4a9eff", "#242424"

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=16, pady=(12, 0))
        self._counter_var = tk.StringVar(value="0 / 0")
        tk.Label(top, textvariable=self._counter_var, bg=BG, fg=ACC, font=("Helvetica", 11)).pack(side="left")
        self._progress = ttk.Progressbar(top, length=400, mode="determinate")
        self._progress.pack(side="left", padx=16, pady=4)
        self._reviewed_var = tk.StringVar(value="")
        self._reviewed_lbl = tk.Label(top, textvariable=self._reviewed_var, bg=BG, fg="#2ecc71",
                                      font=("Helvetica", 11, "bold"))
        self._reviewed_lbl.pack(side="left", padx=12)

        info = tk.Frame(self, bg=BG)
        info.pack(fill="x", padx=16, pady=8)
        self._title_var = tk.StringVar(value="-")
        tk.Label(info, textvariable=self._title_var, bg=BG, fg=FG, font=("Helvetica", 15, "bold"), wraplength=760, justify="left").pack(anchor="w")
        self._creator_var = tk.StringVar(value="")
        tk.Label(info, textvariable=self._creator_var, bg=BG, fg="#888", font=("Helvetica", 11)).pack(anchor="w")

        meta_card = tk.Frame(self, bg=CARD, bd=0)
        meta_card.pack(fill="x", padx=16, pady=4)
        self._meta_var = tk.StringVar(value="")
        tk.Label(meta_card, textvariable=self._meta_var, bg=CARD, fg="#aaa", font=("Helvetica", 10), justify="left", wraplength=760).pack(anchor="w", padx=12, pady=8)

        stag_frame = tk.Frame(self, bg=BG)
        stag_frame.pack(fill="x", padx=16, pady=2)
        tk.Label(stag_frame, text="Source tags:", bg=BG, fg="#666", font=("Helvetica", 10)).pack(side="left")
        self._stag_var = tk.StringVar(value="")
        tk.Label(stag_frame, textvariable=self._stag_var, bg=BG, fg="#888", font=("Helvetica", 10)).pack(side="left", padx=6)

        play_frame = tk.Frame(self, bg=BG)
        play_frame.pack(pady=10)
        self._play_frame_btn, self._play_btn = _make_btn(play_frame, "Play", self._toggle_play)
        self._play_frame_btn.pack(side="left", padx=6)
        _make_btn(play_frame, "Stop", self._stop_play)[0].pack(side="left", padx=6)
        self._status_var = tk.StringVar(value="")
        tk.Label(play_frame, textvariable=self._status_var, bg=BG, fg="#666", font=("Helvetica", 10)).pack(side="left", padx=10)

        form = tk.Frame(self, bg=BG)
        form.pack(fill="x", padx=16, pady=6)
        tk.Label(form, text="Decision:", bg=BG, fg=FG, font=("Helvetica", 11)).grid(row=0, column=0, sticky="w", padx=6)
        self._decision_var = tk.StringVar(value="keep")
        ttk.Combobox(form, textvariable=self._decision_var, values=DECISIONS, state="readonly", width=12).grid(row=0, column=1, sticky="w", padx=6)
        tk.Label(form, text="Role:", bg=BG, fg=FG, font=("Helvetica", 11)).grid(row=0, column=2, sticky="w", padx=6)
        self._role_var = tk.StringVar(value="")
        ttk.Combobox(form, textvariable=self._role_var, values=ROLES, state="readonly", width=12).grid(row=0, column=3, sticky="w", padx=6)
        tk.Label(form, text="Tags:", bg=BG, fg=FG, font=("Helvetica", 11)).grid(row=1, column=0, sticky="w", padx=6, pady=6)
        self._tags_var = tk.StringVar(value="")
        tk.Entry(form, textvariable=self._tags_var, width=40, bg="#2a2a2a", fg=FG, insertbackground=FG, relief="flat").grid(row=1, column=1, columnspan=3, sticky="w", padx=6, pady=6)
        tk.Label(form, text="Notes:", bg=BG, fg=FG, font=("Helvetica", 11)).grid(row=2, column=0, sticky="nw", padx=6)
        self._notes = tk.Text(form, width=50, height=3, bg="#2a2a2a", fg=FG, insertbackground=FG, relief="flat", font=("Helvetica", 11))
        self._notes.grid(row=2, column=1, columnspan=3, sticky="w", padx=6, pady=4)

        nav = tk.Frame(self, bg=BG)
        nav.pack(pady=14)
        _make_btn(nav, "Prev", self._prev, font=("Helvetica", 13, "bold"), padx=22, pady=10)[0].pack(side="left", padx=8)
        _make_btn(nav, "Apply and Next", self._save_and_next, font=("Helvetica", 13, "bold"), padx=22, pady=10)[0].pack(side="left", padx=8)
        _make_btn(nav, "+ Ingest New Sounds", self._ingest_new,
                  bg="#1a6b3a", font=("Helvetica", 13, "bold"), padx=22, pady=10)[0].pack(side="left", padx=16)

        self._ingest_status_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self._ingest_status_var, bg=BG, fg="#2ecc71",
                 font=("Helvetica", 10)).pack(pady=0)
        tk.Label(self, text="Left/Right: navigate", bg=BG, fg="#444", font=("Helvetica", 9)).pack(pady=2)

    def _load_assets(self):
        self._stop_play()
        if self._show_approved.get():
            status = ("pending_review", "approved")
        else:
            status = "pending_review"
        assets = load_from_db(status=status)
        # Only fall back to manifest if the DB itself doesn't exist
        from pathlib import Path as _Path
        if not assets and not _Path("library/becoming.db").exists():
            assets = load_from_manifest()
        self._assets = assets
        self._index = 0
        self._refresh_progress()
        if assets:
            self._show_asset(0)
        else:
            self._title_var.set("No assets found")
            self._meta_var.set("Ingest sounds first, or toggle View > Show approved")

    def _show_asset(self, idx):
        if not self._assets:
            return
        a = self._assets[idx]
        self._title_var.set(a.title or a.local_id or "Asset " + str(a.asset_id))
        self._creator_var.set("by " + a.creator if a.creator else "")
        dur = "{:.1f}s".format(a.duration_seconds) if a.duration_seconds else "?"
        scores = []
        for name, val in [("world_fit", a.world_fit_score), ("pulse", a.pulse_fit_score), ("drift", a.drift_fit_score), ("quality", a.quality_score), ("silence", a.silence_ratio)]:
            if val is not None:
                scores.append("{}={:.2f}".format(name, val))

        # Load any previously saved review from DB
        saved = load_last_review(a.asset_id)

        # Show "reviewed" badge if this asset has a saved review
        if saved:
            badge = "✓ reviewed ({})".format(saved.get("approval_status", ""))
            self._reviewed_var.set(badge)
            self._reviewed_lbl.config(fg="#2ecc71")
        else:
            self._reviewed_var.set("○ not yet reviewed")
            self._reviewed_lbl.config(fg="#555555")

        meta_lines = [
            "Source: {}  Duration: {}  Status: {}".format(
                a.source_name, dur,
                saved.get("approval_status", a.approval_status) if saved else a.approval_status
            ),
            "  ".join(scores) if scores else "",
            "File: {}".format(a.normalized_file_path or "(no file)"),
        ]
        self._meta_var.set("\n".join(l for l in meta_lines if l))
        self._stag_var.set(", ".join(a.source_tags) if a.source_tags else "none")

        # Pre-populate form with saved values (or defaults for unreviewed)
        if saved:
            self._decision_var.set(saved.get("decision", "keep"))
            self._role_var.set(saved.get("role", ""))
            self._tags_var.set(", ".join(saved.get("becoming_tags", [])))
            self._notes.delete("1.0", "end")
            self._notes.insert("1.0", saved.get("notes", ""))
        else:
            self._decision_var.set("keep")
            self._role_var.set("")
            self._tags_var.set(", ".join(a.model_tags) if a.model_tags else "")
            self._notes.delete("1.0", "end")

        self._status_var.set("")
        self._play_btn.config(text="Play")
        self._refresh_progress()

    def _refresh_progress(self):
        total = len(self._assets)
        idx = self._index
        self._counter_var.set("{} / {}".format(idx + 1 if total else 0, total))
        if total:
            self._progress["maximum"] = total
            self._progress["value"] = idx + 1

    def _toggle_play(self):
        if self._play_proc and self._play_proc.poll() is None:
            self._stop_play()
        else:
            self._start_play()

    def _start_play(self):
        if not self._assets:
            return
        a = self._assets[self._index]
        path = a.normalized_file_path
        if not path or not Path(path).exists():
            self._status_var.set("file not found")
            return
        self._stop_play()
        self._play_btn.config(text="Pause")
        self._status_var.set("playing...")
        def _run():
            self._play_proc = subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._play_proc.wait()
            self.after(0, lambda: self._play_btn.config(text="Play"))
            self.after(0, lambda: self._status_var.set(""))
        threading.Thread(target=_run, daemon=True).start()

    def _stop_play(self):
        if self._play_proc and self._play_proc.poll() is None:
            self._play_proc.terminate()
        self._play_proc = None
        self._play_btn.config(text="Play")
        self._status_var.set("")

    def _prev(self):
        self._stop_play()
        if self._index > 0:
            self._index -= 1
            self._show_asset(self._index)

    def _save_and_next(self):
        self._stop_play()
        if not self._assets:
            return
        a = self._assets[self._index]
        decision = self._decision_var.get()
        role = self._role_var.get().strip()
        tags = [t.strip() for t in self._tags_var.get().split(",") if t.strip()]
        notes = self._notes.get("1.0", "end").strip()
        try:
            rec = ReviewRecord(
                asset_id=a.asset_id,
                decision=decision,
                role=role or None,
                becoming_tags=tags,
                notes=notes,
            )
            save_review(rec)
            self._status_var.set("saved: " + decision)
        except Exception as exc:
            messagebox.showerror("Save error", str(exc))
            return
        if self._index < len(self._assets) - 1:
            self._index += 1
            self._show_asset(self._index)
        else:
            messagebox.showinfo("Done", "All assets reviewed!")

    # ------------------------------------------------------------------ #
    #  Ingest new sounds                                                   #
    # ------------------------------------------------------------------ #

    def _ingest_new(self):
        """Open a dialog to ingest a fresh batch of sounds, then reload."""
        dlg = _IngestDialog(self)
        self.wait_window(dlg)
        if not dlg.result:
            return
        query, limit = dlg.result
        self._ingest_status_var.set('⏳ ingesting "%s" ...' % query)
        self.update_idletasks()

        def _run():
            try:
                from dotenv import load_dotenv
                load_dotenv()
                from src.ingestion.database import Database
                from src.ingestion.models import PipelineConfigModel
                from src.ingestion.pipeline import IngestionPipeline
                from src.ingestion.sources.freesound import FreesoundConnector

                config = PipelineConfigModel(
                    database_url="library/becoming.db",
                    raw_dir="library/audio_raw",
                    normalized_dir="library/audio_normalized",
                    embeddings_dir="library/embeddings",
                    spectrogram_dir="library/spectrograms",
                    waveform_dir="library/waveforms",
                    rejected_dir="library/rejected",
                    review_required=True,   # keep as pending_review so GUI can load them
                )
                db = Database("library/becoming.db")
                db.connect()
                pipeline = IngestionPipeline(config=config, db=db)
                api_key = os.getenv("FREESOUND_API_KEY", "")
                if api_key:
                    pipeline.register_source(FreesoundConnector(api_key=api_key))
                ingested = pipeline.run(query=query, source_name="freesound", limit=limit)
                db.close()   # release lock before GUI reloads
                n, q = ingested, query
                self.after(0, lambda n=n, q=q: self._on_ingest_done(n, q))
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda msg=err_msg: self._on_ingest_error(msg))

        threading.Thread(target=_run, daemon=True).start()

    def _on_ingest_done(self, count: int, query: str):
        self._ingest_status_var.set('✓ ingested %d new sounds for "%s"' % (count, query))
        # switch to show only pending_review so the new sounds appear at front
        self._show_approved.set(False)
        self._load_assets()
        if count == 0:
            messagebox.showinfo(
                "Ingest complete",
                "No new sounds were added (all may have been duplicates or filtered out).\n"
                "Try a different query."
            )

    def _on_ingest_error(self, msg: str):
        self._ingest_status_var.set("")
        messagebox.showerror("Ingest failed", msg)


class _IngestDialog(tk.Toplevel):
    """Modal dialog: enter a search query and how many sounds to fetch."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Ingest New Sounds")
        self.configure(bg="#1a1a1a")
        self.resizable(False, False)
        self.result = None
        self._build()
        self.transient(parent)
        self.grab_set()
        # centre over parent
        self.update_idletasks()
        px, py = parent.winfo_x(), parent.winfo_y()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry("+%d+%d" % (px + pw//2 - w//2, py + ph//2 - h//2))

    def _build(self):
        BG, FG = "#1a1a1a", "#e0e0e0"
        pad = {"padx": 18, "pady": 8}

        tk.Label(self, text="Search query", bg=BG, fg=FG,
                 font=("Helvetica", 12, "bold")).grid(row=0, column=0, sticky="w", **pad)
        self._query_var = tk.StringVar(value="ambient texture")
        tk.Entry(self, textvariable=self._query_var, width=34,
                 bg="#2a2a2a", fg=FG, insertbackground=FG, relief="flat",
                 font=("Helvetica", 12)).grid(row=0, column=1, **pad)

        tk.Label(self, text="How many", bg=BG, fg=FG,
                 font=("Helvetica", 12, "bold")).grid(row=1, column=0, sticky="w", **pad)
        self._limit_var = tk.IntVar(value=10)
        ttk.Spinbox(self, from_=1, to=50, textvariable=self._limit_var,
                    width=6).grid(row=1, column=1, sticky="w", **pad)

        btn_row = tk.Frame(self, bg=BG)
        btn_row.grid(row=2, column=0, columnspan=2, pady=12)
        _make_btn(btn_row, "Fetch", self._ok, padx=20, pady=8)[0].pack(side="left", padx=8)
        _make_btn(btn_row, "Cancel", self.destroy, bg="#444444", padx=20, pady=8)[0].pack(side="left", padx=8)
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())

    def _ok(self):
        query = self._query_var.get().strip()
        if not query:
            return
        self.result = (query, int(self._limit_var.get()))
        self.destroy()


def main():
    app = ReviewGUI()
    app.mainloop()


if __name__ == "__main__":
    main()

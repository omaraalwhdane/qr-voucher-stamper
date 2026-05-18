#!/usr/bin/env python3
"""
Petra Drug Store — QR Voucher Stamper
Batch-stamps QR codes onto pharmacy voucher images using OCR auto-fill.

Requirements:
    pip install Pillow "qrcode[pil]" pytesseract
    brew install tesseract
"""

import os
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    import qrcode
    import pytesseract
    from PIL import Image, ImageEnhance, ImageFilter
    # Auto-detect Tesseract on Windows
    if os.name == "nt":
        _win_tess = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.exists(_win_tess):
            pytesseract.pytesseract.tesseract_cmd = _win_tess
    DEPS_OK = True
    MISSING = ""
except ImportError as exc:
    DEPS_OK = False
    MISSING = str(exc)

# ── Constants ────────────────────────────────────────────────────────────────
QR_SIZE   = 150
QR_MARGIN = 20

TYPE_OPTIONS = ["T9 - مبيعات (Sales)", "T2 - مرتجع (Return)"]
TYPE_MAP     = {"T9 - مبيعات (Sales)": "T9", "T2 - مرتجع (Return)": "T2"}


# ── Tooltip ──────────────────────────────────────────────────────────────────
class Tooltip:
    def __init__(self, widget, text):
        self._tip = None
        widget.bind("<Enter>", lambda e: self._show(widget, text))
        widget.bind("<Leave>", lambda e: self._hide())

    def _show(self, w, text):
        x = w.winfo_rootx() + 4
        y = w.winfo_rooty() + w.winfo_height() + 4
        self._tip = tw = tk.Toplevel(w)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=text, background="#FFFFE0", foreground="#333",
                 relief="solid", borderwidth=1,
                 font=("Helvetica", 10), padx=6, pady=3).pack()

    def _hide(self):
        if self._tip:
            self._tip.destroy()
            self._tip = None


# ── Editable Treeview ────────────────────────────────────────────────────────
class EditableTreeview(ttk.Treeview):
    READ_ONLY = ("filename", "match")

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._widget = self._edit_item = self._edit_col = None
        self.bind("<Double-1>", self._on_double_click)
        self.bind("<Button-1>", lambda e: self._commit())
        self.bind("<FocusOut>", lambda e: self._commit())

    def _on_double_click(self, event):
        if self.identify_region(event.x, event.y) != "cell":
            return
        col  = self.identify_column(event.x)
        item = self.identify_row(event.y)
        if not item:
            return
        col_idx  = int(col.lstrip("#")) - 1
        col_name = self["columns"][col_idx]
        if col_name in self.READ_ONLY:
            return
        self._commit()
        bbox = self.bbox(item, col)
        if not bbox:
            return
        x, y, w, h = bbox
        self._edit_item = item
        self._edit_col  = col_name
        current = self._get_cell(item, col_name)

        if col_name == "type":
            combo = ttk.Combobox(self, values=TYPE_OPTIONS, state="readonly")
            combo.set(current if current in TYPE_OPTIONS else TYPE_OPTIONS[0])
            combo.place(x=x, y=y, width=w, height=h)
            combo.focus_set()
            combo.event_generate("<Button-1>")
            combo.bind("<<ComboboxSelected>>", lambda _e: self._commit())
            combo.bind("<Escape>", lambda _e: self._cancel())
            self._widget = combo
        else:
            entry = ttk.Entry(self)
            entry.insert(0, current)
            entry.select_range(0, tk.END)
            entry.place(x=x, y=y, width=w, height=h)
            entry.focus_set()
            entry.bind("<Return>", lambda _e: self._commit())
            entry.bind("<Tab>",    lambda _e: self._commit())
            entry.bind("<Escape>", lambda _e: self._cancel())
            self._widget = entry

    def _commit(self):
        if not self._widget:
            return
        self._set_cell(self._edit_item, self._edit_col, self._widget.get())
        self._widget.destroy()
        self._widget = self._edit_item = self._edit_col = None

    def _cancel(self):
        if self._widget:
            self._widget.destroy()
            self._widget = self._edit_item = self._edit_col = None

    def _get_cell(self, item, col_name):
        idx = list(self["columns"]).index(col_name)
        vals = self.item(item, "values")
        return vals[idx] if idx < len(vals) else ""

    def _set_cell(self, item, col_name, value):
        idx  = list(self["columns"]).index(col_name)
        vals = list(self.item(item, "values"))
        while len(vals) <= idx:
            vals.append("")
        vals[idx] = value
        self.item(item, values=vals)


# ── Progress dialog ──────────────────────────────────────────────────────────
class ProgressDialog(tk.Toplevel):
    def __init__(self, parent, total, title="Processing…"):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.total = total
        self.cancelled = False
        self._t0 = time.time()

        pw, ph = 480, 160
        px = parent.winfo_rootx() + parent.winfo_width()  // 2 - pw // 2
        py = parent.winfo_rooty() + parent.winfo_height() // 2 - ph // 2
        self.geometry(f"{pw}x{ph}+{px}+{py}")

        ttk.Label(self, text=title,
                  font=("Helvetica", 13, "bold")).pack(pady=(18, 4))

        self._status = tk.StringVar(value="Starting…")
        ttk.Label(self, textvariable=self._status,
                  font=("Helvetica", 10),
                  foreground="#555").pack(padx=20, anchor="w")

        self._var = tk.DoubleVar()
        ttk.Progressbar(self, variable=self._var,
                        maximum=total, length=440).pack(pady=8, padx=20)

        row = ttk.Frame(self)
        row.pack(fill="x", padx=20)
        self._pct = tk.StringVar(value="0%")
        self._eta = tk.StringVar(value="")
        ttk.Label(row, textvariable=self._pct,
                  font=("Helvetica", 10, "bold")).pack(side="left")
        ttk.Label(row, textvariable=self._eta,
                  font=("Helvetica", 10),
                  foreground="#777").pack(side="right")

        ttk.Button(self, text="Cancel",
                   command=self._cancel).pack(pady=(8, 14))

    def update(self, done, filename):
        self._var.set(done)
        pct = int(done / self.total * 100)
        self._pct.set(f"{pct}%")
        elapsed = time.time() - self._t0
        if done > 0:
            eta = elapsed / done * (self.total - done)
            self._eta.set(f"~{int(eta)}s remaining")
        short = filename if len(filename) <= 50 else "…" + filename[-48:]
        self._status.set(f"({done}/{self.total})  {short}")
        self.update_idletasks()

    def _cancel(self):
        self.cancelled = True


# ── OCR extraction ───────────────────────────────────────────────────────────
def _preprocess_for_ocr(img, top_pct, bot_pct, right_pct=0.45):
    w, h = img.size
    img = img.crop((0, int(h * top_pct), int(w * right_pct), int(h * bot_pct)))
    img = img.resize((img.width * 3, img.height * 3), Image.LANCZOS)
    img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(2.5)
    return img.filter(ImageFilter.SHARPEN)


def ocr_extract_fields(path):
    img = Image.open(path)
    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGB")
    cfg = "--psm 6 --oem 3"

    text1 = pytesseract.image_to_string(
        _preprocess_for_ocr(img, 0.14, 0.28), lang="eng", config=cfg)
    voucher = client = year = ""

    m = re.search(r"INVOICE\s*[:\s]\s*(\d{5,})", text1, re.IGNORECASE)
    if m:
        voucher = m.group(1).strip()

    m = re.search(r"ACCOUNT\s*[:\s]\s*([\d]+-[\d]+)", text1, re.IGNORECASE)
    if m:
        raw   = m.group(1).strip()
        parts = raw.split("-", 1)
        client = parts[1] if len(parts) == 2 else raw

    text2 = pytesseract.image_to_string(
        _preprocess_for_ocr(img, 0.18, 0.24), lang="eng", config=cfg)
    m = re.search(r"DATE\s*[:\s=]+\s*\d{1,2}[-/]\d{1,2}[-/](\d{4})",
                  text2, re.IGNORECASE)
    if m:
        year = m.group(1)
    else:
        m = re.search(r"\b\d{1,2}[-/]\d{1,2}[-/](\d{4})\b", text2)
        if m:
            year = m.group(1)

    return {"voucher": voucher, "year": year, "client": client,
            "type_label": TYPE_OPTIONS[0]}


# ── QR stamping ──────────────────────────────────────────────────────────────
def stamp_qr(src, dst, voucher, client, year, type_code):
    type_num = type_code.replace("T", "")
    data = f"PDS:C1:T{type_num}:Y{year}:V{voucher}:A{client}"

    qr = qrcode.QRCode(version=None,
                       error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black",
                            back_color="white").convert("RGB")
    qr_img = qr_img.resize((QR_SIZE, QR_SIZE), Image.LANCZOS)

    img = Image.open(src)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    paste_fn = img.paste
    x, y     = QR_MARGIN, img.height - QR_SIZE - QR_MARGIN
    if img.mode == "RGBA":
        paste_fn(qr_img.convert("RGBA"), (x, y))
    else:
        paste_fn(qr_img, (x, y))

    ext = Path(dst).suffix.lower()
    if ext in (".jpg", ".jpeg"):
        img.save(dst, format="JPEG", quality=100, subsampling=0)
    elif ext == ".png":
        img.save(dst, format="PNG", compress_level=0)
    else:
        img.save(dst, quality=100)


# ── Main application ─────────────────────────────────────────────────────────
class VoucherQRApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Petra Drug Store — QR Voucher Stamper")
        self.geometry("1150x740")
        self.minsize(920, 580)

        if not DEPS_OK:
            messagebox.showerror(
                "Missing Dependencies",
                f"Required libraries not found:\n{MISSING}\n\n"
                "Install with:\n  pip install Pillow \"qrcode[pil]\" pytesseract\n"
                "  brew install tesseract")
            self.destroy()
            return

        self._output_folder = tk.StringVar(value="")
        self._paths: dict[str, str] = {}

        self._setup_styles()
        self._build_ui()
        self._bind_shortcuts()

    # ── Styles ────────────────────────────────────────────────────────────────
    def _setup_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")

        # General
        s.configure(".", font=("Helvetica", 11))
        s.configure("TFrame",  background="#F0F4F8")
        s.configure("TLabel",  background="#F0F4F8")

        # Section label
        s.configure("Section.TLabel", font=("Helvetica", 11, "bold"),
                    foreground="#1A3A5C")

        # Header frame
        s.configure("Header.TFrame", background="#1A3A5C")
        s.configure("Header.TLabel", background="#1A3A5C",
                    foreground="white")
        s.configure("HeaderSub.TLabel", background="#1A3A5C",
                    foreground="#7EB3E8", font=("Helvetica", 10))

        # Toolbar frame
        s.configure("Toolbar.TFrame",    background="#FFFFFF")
        s.configure("Toolbar.TLabel",    background="#FFFFFF",
                    font=("Helvetica", 10))
        s.configure("ToolbarSep.TFrame", background="#DADFE8")

        # Buttons — primary (blue)
        s.configure("Primary.TButton",
                    font=("Helvetica", 11, "bold"),
                    padding=(14, 7))
        s.map("Primary.TButton",
              foreground=[("!disabled", "#1A3A5C")],
              background=[("active", "#D0DFF0"), ("!active", "#E8EFF8")])

        # Buttons — accent (generate)
        s.configure("Accent.TButton",
                    font=("Helvetica", 12, "bold"),
                    padding=(18, 9))
        s.map("Accent.TButton",
              foreground=[("!disabled", "#7B1C0A")],
              background=[("active", "#F5C6B0"), ("!active", "#FAE0D5")])

        # Buttons — danger (remove/clear)
        s.configure("Danger.TButton",
                    font=("Helvetica", 11),
                    padding=(12, 7))
        s.map("Danger.TButton",
              foreground=[("!disabled", "#5C2020")],
              background=[("active", "#EDD0D0"), ("!active", "#F5E8E8")])

        # Treeview
        s.configure("Treeview",
                    background="white",
                    fieldbackground="white",
                    foreground="#1A1A1A",
                    rowheight=30,
                    font=("Helvetica", 11))
        s.configure("Treeview.Heading",
                    background="#1A3A5C",
                    foreground="white",
                    font=("Helvetica", 11, "bold"),
                    relief="flat",
                    padding=(8, 8))
        s.map("Treeview",
              background=[("selected", "#C8DEFA")],
              foreground=[("selected", "#0D1B2A")])
        s.map("Treeview.Heading",
              background=[("active", "#254E80")])

        # Scrollbars
        s.configure("TScrollbar",
                    troughcolor="#E8ECF2",
                    background="#B0BEC5",
                    relief="flat", width=9)

        # Separator
        s.configure("TSeparator", background="#DADFE8")

        # Progressbar
        s.configure("TProgressbar",
                    troughcolor="#DDE3EE",
                    background="#2A6099",
                    thickness=12)

        # Status bar
        s.configure("Status.TFrame",  background="#ECEFF4")
        s.configure("Status.TLabel",  background="#ECEFF4",
                    foreground="#546E7A", font=("Helvetica", 10))

    # ── Keyboard shortcuts ────────────────────────────────────────────────────
    def _bind_shortcuts(self):
        self.bind_all("<Command-o>",      lambda _e: self._add_images())
        self.bind_all("<Command-r>",      lambda _e: self._auto_read_all())
        self.bind_all("<Command-k>",      lambda _e: self._verify_all())
        self.bind_all("<Command-Return>", lambda _e: self._start_processing())

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.configure(background="#F0F4F8")

        self._build_header()     # row 0
        self._build_toolbar()    # row 1
        self._build_table()      # row 2
        self._build_statusbar()  # row 3

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self):
        hdr = ttk.Frame(self, style="Header.TFrame")
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(1, weight=1)

        # Logo box
        logo = tk.Label(hdr, text="🏥", font=("", 26),
                        bg="#1A3A5C", fg="white")
        logo.grid(row=0, column=0, rowspan=2, padx=(16, 10), pady=10)

        ttk.Label(hdr, text="Petra Drug Store  —  QR Voucher Stamper",
                  style="Header.TLabel",
                  font=("Helvetica", 15, "bold")).grid(
                      row=0, column=1, sticky="w", pady=(12, 0))
        ttk.Label(hdr,
                  text="Batch-stamp QR codes onto pharmacy voucher images  •  "
                       "OCR auto-fill  •  Duplicate & mismatch detection",
                  style="HeaderSub.TLabel").grid(
                      row=1, column=1, sticky="w", pady=(0, 10))

    # ── Toolbar ───────────────────────────────────────────────────────────────
    def _build_toolbar(self):
        outer = ttk.Frame(self, style="Toolbar.TFrame")
        outer.grid(row=1, column=0, sticky="ew")
        outer.columnconfigure(0, weight=1)

        ttk.Separator(outer, orient="horizontal").grid(
            row=0, column=0, sticky="ew")

        # ── Row 1: action buttons ─────────────────────────────────────────────
        row1 = ttk.Frame(outer, style="Toolbar.TFrame", padding=(10, 7, 10, 3))
        row1.grid(row=1, column=0, sticky="ew")

        b1 = ttk.Button(row1, text="➕  Add Images",
                        style="Primary.TButton", command=self._add_images)
        b1.pack(side="left", padx=(0, 4))
        Tooltip(b1, "Select voucher JPG/PNG files  (⌘O)")

        b1f = ttk.Button(row1, text="📂  Add Folder",
                         style="Primary.TButton", command=self._add_folder)
        b1f.pack(side="left", padx=(0, 8))
        Tooltip(b1f, "Load ALL images from a folder (great for 1000+ files)")

        ttk.Separator(row1, orient="vertical").pack(side="left", fill="y", padx=6)

        b2 = ttk.Button(row1, text="🔍  Auto-read (OCR)",
                        style="Primary.TButton", command=self._auto_read_all)
        b2.pack(side="left", padx=(4, 4))
        Tooltip(b2, "Read INVOICE, DATE, ACCOUNT via OCR  (⌘R)")

        b3 = ttk.Button(row1, text="✔  Verify Data",
                        style="Primary.TButton", command=self._verify_all)
        b3.pack(side="left", padx=(0, 8))
        Tooltip(b3, "Re-scan and compare table data vs image  (⌘K)")

        ttk.Separator(row1, orient="vertical").pack(side="left", fill="y", padx=6)

        b4 = ttk.Button(row1, text="✖  Remove",
                        style="Danger.TButton", command=self._remove_selected)
        b4.pack(side="left", padx=4)
        Tooltip(b4, "Remove selected rows")

        b_mismatch = ttk.Button(row1, text="❌  Delete Mismatches",
                                style="Danger.TButton",
                                command=self._remove_mismatches)
        b_mismatch.pack(side="left", padx=4)
        Tooltip(b_mismatch, "Remove all rows where OCR data does NOT match  (❌ No)")

        b5 = ttk.Button(row1, text="🗑  Clear All",
                        style="Danger.TButton", command=self._clear_all)
        b5.pack(side="left", padx=4)
        Tooltip(b5, "Remove all rows")

        # ── Row 2: output folder (full width, always visible) ─────────────────
        row2 = ttk.Frame(outer, style="Toolbar.TFrame", padding=(10, 3, 10, 7))
        row2.grid(row=2, column=0, sticky="ew")
        row2.columnconfigure(1, weight=1)

        ttk.Label(row2, text="📁  Output folder:", style="Toolbar.TLabel",
                  foreground="#546E7A",
                  font=("Helvetica", 11, "bold")).grid(
                      row=0, column=0, sticky="w", padx=(0, 6))

        self._out_lbl = ttk.Label(row2, textvariable=self._output_folder,
                                  style="Toolbar.TLabel",
                                  foreground="#1A5C99",
                                  font=("Helvetica", 10, "underline"),
                                  cursor="hand2", anchor="w")
        self._out_lbl.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self._out_lbl.bind("<Button-1>", lambda _e: self._set_output())
        self._output_folder.set("(click Browse to choose output folder)")

        bf = ttk.Button(row2, text="Browse…",
                        command=self._set_output)
        bf.grid(row=0, column=2, sticky="e")
        Tooltip(bf, "Choose where stamped images are saved")

        ttk.Separator(outer, orient="horizontal").grid(
            row=3, column=0, sticky="ew")

    # ── Table ─────────────────────────────────────────────────────────────────
    def _build_table(self):
        outer = ttk.Frame(self, padding=(10, 6, 10, 0))
        outer.grid(row=2, column=0, sticky="nsew")
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        cols     = ("filename", "voucher", "client", "year", "type", "match")
        headings = ("  Filename", "  Voucher # (INVOICE)",
                    "  Client # (ACCOUNT)", "  Year", "  Type", "OCR Match")
        widths   = (250, 145, 155, 70, 200, 95)
        # filename and type stretch; fixed columns stay fixed
        stretches = (True, False, False, False, True, False)

        self.tree = EditableTreeview(outer, columns=cols,
                                     show="headings",
                                     selectmode="extended")
        for col, heading, width, stretch in zip(cols, headings, widths, stretches):
            self.tree.heading(col, text=heading, anchor="w")
            self.tree.column(col, width=width, minwidth=60, anchor="w",
                             stretch=stretch)
        self.tree.column("year",  anchor="center", stretch=False)
        self.tree.column("match", anchor="center", width=95, stretch=False)

        # Row + state tags
        self.tree.tag_configure("odd",     background="#FFFFFF")
        self.tree.tag_configure("even",    background="#EEF4FB")
        self.tree.tag_configure("match_yes",
                                foreground="#1B5E20",
                                font=("Helvetica", 11, "bold"))
        self.tree.tag_configure("match_no",
                                foreground="#B71C1C",
                                background="#FFF5F5",
                                font=("Helvetica", 11, "bold"))
        self.tree.tag_configure("match_partial",
                                foreground="#E65100")

        vsb = ttk.Scrollbar(outer, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(outer, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # Empty-state label (sits on top of tree when no rows)
        self._empty = tk.Label(
            outer,
            text="\n📂  No images loaded\n\n"
                 "Click  ➕ Add Images  to get started\n"
                 "then click  🔍 Auto-read  to extract data automatically",
            bg="white", fg="#B0BEC5",
            font=("Helvetica", 13), justify="center")
        self._empty.grid(row=0, column=0, sticky="nsew")

    # ── Status bar ────────────────────────────────────────────────────────────
    def _build_statusbar(self):
        bar = ttk.Frame(self, style="Status.TFrame")
        bar.grid(row=3, column=0, sticky="ew")
        ttk.Separator(bar, orient="horizontal").pack(fill="x", side="top")

        inner = ttk.Frame(bar, style="Status.TFrame", padding=(12, 6))
        inner.pack(fill="x")

        self._stat_var = tk.StringVar(value="Ready  —  no images loaded")
        ttk.Label(inner, textvariable=self._stat_var,
                  style="Status.TLabel").pack(side="left")

        gen = ttk.Button(inner, text="⚡  Generate QR Codes",
                         style="Accent.TButton",
                         command=self._start_processing)
        gen.pack(side="right", padx=(8, 0))
        Tooltip(gen, "Stamp QR codes onto all loaded images  (⌘↩)")

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _restripe(self):
        for iid in self.tree.get_children():
            cur = [t for t in self.tree.item(iid, "tags")
                   if t not in ("odd", "even")]
            base = "even" if self.tree.index(iid) % 2 == 0 else "odd"
            self.tree.item(iid, tags=(base, *cur))

    def _refresh_stats(self):
        items = self.tree.get_children()
        n = len(items)
        if n == 0:
            self._stat_var.set("Ready  —  no images loaded")
            self._empty.lift()
            return
        self._empty.lower()
        yes = sum(1 for i in items if "match_yes" in self.tree.item(i, "tags"))
        no  = sum(1 for i in items if "match_no"  in self.tree.item(i, "tags"))
        parts = [f"📄 {n} image{'s' if n != 1 else ''}"]
        if yes: parts.append(f"✅ {yes} matched")
        if no:  parts.append(f"❌ {no} mismatch{'es' if no != 1 else ''}")
        out = self._output_folder.get()
        if out and os.path.isdir(out):
            short = out if len(out) <= 44 else "…" + out[-42:]
            parts.append(f"📁 {short}")
        self._stat_var.set("   •   ".join(parts))

    # ── Button handlers ───────────────────────────────────────────────────────
    def _add_images(self):
        paths = filedialog.askopenfilenames(
            title="Select Voucher Images",
            filetypes=[("Images", "*.jpg *.jpeg *.png"), ("All files", "*.*")])
        self._insert_paths(list(paths))

    def _add_folder(self):
        folder = filedialog.askdirectory(title="Select Folder Containing Voucher Images")
        if not folder:
            return
        exts = {".jpg", ".jpeg", ".png"}
        paths = sorted(
            str(p) for p in Path(folder).iterdir()
            if p.is_file() and p.suffix.lower() in exts
        )
        if not paths:
            messagebox.showinfo("No Images Found",
                                f"No JPG/PNG images found in:\n{folder}")
            return
        self._insert_paths(paths)

    def _insert_paths(self, paths):
        """Bulk-insert image paths into the table efficiently."""
        existing = set(self._paths.values())
        new_paths = [p for p in paths if p not in existing]
        if not new_paths:
            messagebox.showinfo("Already Loaded",
                                "All selected images are already in the table.")
            return

        # Batch insert — detach tree for speed when adding large sets
        if len(new_paths) > 50:
            self.tree.pack_forget() if hasattr(self.tree, "pack_info") else None

        for path in new_paths:
            iid = self.tree.insert("", "end",
                                   values=(os.path.basename(path),
                                           "", "", "", TYPE_OPTIONS[0], "—"))
            self._paths[iid] = path

        self._restripe()
        self._refresh_stats()

        if not self._output_folder.get() or \
           not os.path.isdir(self._output_folder.get()):
            first_dir = os.path.dirname(list(self._paths.values())[0])
            out = os.path.join(first_dir, "QR_Output")
            os.makedirs(out, exist_ok=True)
            self._output_folder.set(out)

        messagebox.showinfo(
            "Images Added",
            f"{len(new_paths)} image(s) loaded.\n\n"
            "Click  🔍 Auto-read (OCR)  to extract voucher data automatically."
        )

    def _remove_selected(self):
        for iid in self.tree.selection():
            self._paths.pop(iid, None)
            self.tree.delete(iid)
        self._restripe()
        self._refresh_stats()

    def _remove_mismatches(self):
        mismatched = [
            iid for iid in self.tree.get_children()
            if "match_no" in self.tree.item(iid, "tags")
        ]
        if not mismatched:
            messagebox.showinfo("No Mismatches",
                                "There are no ❌ mismatch rows to remove.\n\n"
                                "Run  ✔ Verify Data  first to detect mismatches.")
            return
        confirm = messagebox.askyesno(
            "Delete Mismatches",
            f"Remove {len(mismatched)} row(s) marked ❌ No (OCR mismatch)?\n\n"
            "This cannot be undone.")
        if not confirm:
            return
        for iid in mismatched:
            self._paths.pop(iid, None)
            self.tree.delete(iid)
        self._restripe()
        self._refresh_stats()

    def _clear_all(self):
        self.tree.delete(*self.tree.get_children())
        self._paths.clear()
        self._refresh_stats()

    def _set_output(self):
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self._output_folder.set(folder)
            self._refresh_stats()

    # ── OCR workers ───────────────────────────────────────────────────────────
    def _run_ocr_worker(self, title, process_fn):
        items = self.tree.get_children()
        if not items:
            messagebox.showinfo("No Images", "Please add voucher images first.")
            return
        dlg = ProgressDialog(self, total=len(items), title=title)
        def worker():
            results = []
            for done, iid in enumerate(items, 1):
                if dlg.cancelled:
                    break
                path = self._paths[iid]
                fname = os.path.basename(path)
                try:
                    results.append(process_fn(iid, path, fname))
                except Exception as exc:
                    results.append({"error": fname, "msg": str(exc)})
                self.after(0, dlg.update, done, fname)

            def finish():
                dlg.destroy()
                self.after(0, self._refresh_stats)
                self._ocr_finish_callback(title, len(items), results)
            self.after(0, finish)
        threading.Thread(target=worker, daemon=True).start()

    def _auto_read_all(self):
        items = self.tree.get_children()
        if not items:
            messagebox.showinfo("No Images", "Please add voucher images first.")
            return
        dlg = ProgressDialog(self, total=len(items), title="Reading Vouchers…")

        def worker():
            failed = []
            for done, iid in enumerate(items, 1):
                if dlg.cancelled:
                    break
                path  = self._paths[iid]
                fname = os.path.basename(path)
                try:
                    f         = ocr_extract_fields(path)
                    all_found = bool(f["voucher"] and f["client"] and f["year"])
                    mval      = "✅ Yes" if all_found else "⚠️ Partial"
                    etag      = "match_yes" if all_found else "match_partial"
                    vals      = self.tree.item(iid, "values")

                    def _upd(iid=iid, f=f, vals=vals, mval=mval, etag=etag):
                        base = "even" if self.tree.index(iid) % 2 == 0 else "odd"
                        self.tree.item(iid, values=(
                            vals[0], f["voucher"], f["client"],
                            f["year"], f["type_label"], mval),
                            tags=(base, etag))
                    self.after(0, _upd)
                    if not all_found:
                        failed.append(fname)
                except Exception as exc:
                    failed.append(f"{fname}: {exc}")
                self.after(0, dlg.update, done, fname)

            def finish():
                dlg.destroy()
                self.after(0, self._refresh_stats)
                n = len(items)
                if failed:
                    messagebox.showwarning(
                        "OCR — Partial Results",
                        f"{n - len(failed)} of {n} vouchers read successfully.\n\n"
                        f"Could not fully read {len(failed)} file(s):\n"
                        + "\n".join(failed[:15])
                        + ("\n…" if len(failed) > 15 else "")
                        + "\n\nDouble-click those cells to fill manually.")
                else:
                    messagebox.showinfo(
                        "OCR Complete ✅",
                        f"All {n} vouchers read successfully!\n\n"
                        "Tip: click  ✔ Verify Data  to confirm accuracy\n"
                        "before generating QR codes.")
            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def _verify_all(self):
        items = self.tree.get_children()
        if not items:
            messagebox.showinfo("No Images", "Please add voucher images first.")
            return
        dlg = ProgressDialog(self, total=len(items), title="Verifying Data…")

        def worker():
            mismatches = []
            for done, iid in enumerate(items, 1):
                if dlg.cancelled:
                    break
                path  = self._paths[iid]
                fname = os.path.basename(path)
                try:
                    ocr    = ocr_extract_fields(path)
                    vals   = self.tree.item(iid, "values")
                    t_vou  = vals[1].strip() if len(vals) > 1 else ""
                    t_cli  = vals[2].strip() if len(vals) > 2 else ""
                    t_year = vals[3].strip() if len(vals) > 3 else ""

                    vok = ocr["voucher"] == t_vou
                    cok = ocr["client"]  == t_cli
                    yok = ocr["year"]    == t_year
                    ok  = vok and cok and yok
                    mval = "✅ Yes" if ok else "❌ No"
                    etag = "match_yes" if ok else "match_no"

                    if not ok:
                        detail = []
                        if not vok: detail.append(
                            f"   Voucher:  yours={t_vou!r}  ocr={ocr['voucher']!r}")
                        if not cok: detail.append(
                            f"   Client:   yours={t_cli!r}  ocr={ocr['client']!r}")
                        if not yok: detail.append(
                            f"   Year:     yours={t_year!r}  ocr={ocr['year']!r}")
                        mismatches.append((fname, detail))

                    def _set(iid=iid, vals=vals, mval=mval, etag=etag):
                        base = "even" if self.tree.index(iid) % 2 == 0 else "odd"
                        self.tree.item(iid,
                                       values=(*vals[:5], mval),
                                       tags=(base, etag))
                    self.after(0, _set)
                except Exception as exc:
                    def _err(iid=iid, vals=self.tree.item(iid, "values")):
                        base = "even" if self.tree.index(iid) % 2 == 0 else "odd"
                        self.tree.item(iid,
                                       values=(*vals[:5], "⚠️ Error"),
                                       tags=(base, "match_partial"))
                    self.after(0, _err)

                self.after(0, dlg.update, done, fname)

            def finish():
                dlg.destroy()
                self.after(0, self._refresh_stats)
                n = len(items)
                if not mismatches:
                    messagebox.showinfo(
                        "Verification Passed ✅",
                        f"All {n} rows match their voucher images.\n\n"
                        "You're ready to generate QR codes!")
                else:
                    lines = []
                    for fname, details in mismatches[:15]:
                        lines.append(f"• {fname}")
                        lines.extend(details)
                    messagebox.showwarning(
                        f"⚠️  {len(mismatches)} Mismatch(es) Found",
                        f"{n - len(mismatches)} OK  •  {len(mismatches)} differ:\n\n"
                        + "\n".join(lines)
                        + ("\n…and more." if len(mismatches) > 15 else "")
                        + "\n\nRows marked ❌ — double-click cells to correct.")
            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def _ocr_finish_callback(self, title, n, results):
        pass  # used only if _run_ocr_worker is called directly

    # ── Generation ────────────────────────────────────────────────────────────
    def _collect_rows(self):
        rows, seen = [], {}
        skipped_missing, skipped_dup = [], []

        for iid in self.tree.get_children():
            vals    = self.tree.item(iid, "values")
            fname   = vals[0] if vals else ""
            voucher = vals[1].strip() if len(vals) > 1 else ""
            client  = vals[2].strip() if len(vals) > 2 else ""
            year    = vals[3].strip() if len(vals) > 3 else ""
            traw    = vals[4] if len(vals) > 4 else TYPE_OPTIONS[0]

            if not (voucher and client and year):
                skipped_missing.append(fname)
                continue
            if voucher in seen:
                skipped_dup.append(f"{fname} (same # as {seen[voucher]})")
                continue
            seen[voucher] = fname
            rows.append((self._paths[iid], voucher, client, year,
                         TYPE_MAP.get(traw, "T9")))

        if not rows:
            messagebox.showwarning(
                "Nothing to Process",
                "No rows have complete data (Voucher #, Client #, Year).\n\n"
                "Run  🔍 Auto-read (OCR)  first, then try again.")
            return None

        # Warn about skipped rows — but only ask confirmation for small batches
        skipped = skipped_missing + skipped_dup
        if skipped:
            lines = []
            if skipped_missing:
                lines.append(f"⚠️  {len(skipped_missing)} row(s) skipped — missing data:")
                lines += [f"   • {f}" for f in skipped_missing[:10]]
                if len(skipped_missing) > 10:
                    lines.append(f"   … and {len(skipped_missing) - 10} more")
            if skipped_dup:
                lines.append(f"⚠️  {len(skipped_dup)} row(s) skipped — duplicate voucher #:")
                lines += [f"   • {f}" for f in skipped_dup[:10]]
                if len(skipped_dup) > 10:
                    lines.append(f"   … and {len(skipped_dup) - 10} more")
            lines.append(f"\n✅  {len(rows)} row(s) will be stamped.")
            proceed = messagebox.askyesno(
                "Some Rows Skipped",
                "\n".join(lines) + "\n\nProceed with the valid rows?")
            if not proceed:
                return None

        return rows

    def _start_processing(self):
        if not self.tree.get_children():
            messagebox.showinfo("No Images", "Please add voucher images first.")
            return
        out = self._output_folder.get()
        if not out or not os.path.isdir(out):
            messagebox.showwarning("Output Folder",
                                   "Please select a valid output folder first.")
            return
        rows = self._collect_rows()
        if rows is None:
            return

        dlg = ProgressDialog(self, total=len(rows),
                             title="Generating QR Codes…")

        def worker():
            errors = []
            for done, (src, voucher, client, year, tc) in enumerate(rows, 1):
                if dlg.cancelled:
                    break
                fname = os.path.basename(src)
                dst   = os.path.join(out,
                                     Path(fname).stem + "_QR" + Path(fname).suffix)
                try:
                    stamp_qr(src, dst, voucher, client, year, tc)
                except Exception as exc:
                    errors.append(f"{fname}: {exc}")
                self.after(0, dlg.update, done, fname)

            def finish():
                dlg.destroy()
                ok = len(rows) - len(errors)
                if dlg.cancelled:
                    messagebox.showinfo("Cancelled",
                                        f"Stopped after {ok} image(s) stamped.")
                elif errors:
                    messagebox.showerror(
                        "Done with Errors",
                        f"{ok} succeeded  •  {len(errors)} failed:\n\n"
                        + "\n".join(errors[:20])
                        + (f"\n…and {len(errors)-20} more." if len(errors)>20 else ""))
                else:
                    messagebox.showinfo(
                        "Done ✅",
                        f"Successfully stamped {len(rows)} voucher(s)!\n\n"
                        f"Saved to:\n{out}")
            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = VoucherQRApp()
    app.mainloop()

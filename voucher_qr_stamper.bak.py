#!/usr/bin/env python3
"""
Petra Drug Store — QR Voucher Stamper
Batch generates and stamps QR codes onto pharmacy voucher images.
Includes OCR auto-fill using Tesseract.

Requirements:  pip install Pillow "qrcode[pil]" pytesseract
               brew install tesseract
"""

import os
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    import qrcode
    import pytesseract
    from PIL import Image, ImageEnhance, ImageFilter
    DEPS_OK = True
    MISSING = ""
except ImportError as exc:
    DEPS_OK = False
    MISSING = str(exc)

# ── Constants ────────────────────────────────────────────────────────────────
QR_SIZE   = 150   # pixels
QR_MARGIN = 20    # pixels from edge

TYPE_OPTIONS = ["T9 - مبيعات (Sales)", "T2 - مرتجع (Return)"]
TYPE_MAP     = {
    "T9 - مبيعات (Sales)":  "T9",
    "T2 - مرتجع (Return)": "T2",
}


# ── Editable Treeview ────────────────────────────────────────────────────────

class EditableTreeview(ttk.Treeview):
    """Treeview with inline Entry / Combobox editing on double-click."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._widget     = None   # active overlay widget
        self._edit_item  = None
        self._edit_col   = None
        self.bind("<Double-1>",  self._on_double_click)
        self.bind("<Button-1>",  self._on_single_click)
        self.bind("<FocusOut>",  lambda _e: self._commit())

    # ── internal helpers ─────────────────────────────────────────────────────

    def _on_single_click(self, _event):
        self._commit()

    def _on_double_click(self, event):
        if self.identify_region(event.x, event.y) != "cell":
            return
        col  = self.identify_column(event.x)
        item = self.identify_row(event.y)
        if not item:
            return
        col_idx  = int(col.lstrip("#")) - 1
        col_name = self["columns"][col_idx]
        if col_name in ("filename", "match"):
            return          # read-only columns

        self._commit()      # save any pending edit first
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
            combo.bind("<Escape>",             lambda _e: self._cancel())
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
        if self._widget is None:
            return
        new_val = self._widget.get()
        self._set_cell(self._edit_item, self._edit_col, new_val)
        self._widget.destroy()
        self._widget    = None
        self._edit_item = None
        self._edit_col  = None

    def _cancel(self):
        if self._widget:
            self._widget.destroy()
            self._widget    = None
            self._edit_item = None
            self._edit_col  = None

    def _get_cell(self, item, col_name):
        cols = list(self["columns"])
        idx  = cols.index(col_name)
        vals = self.item(item, "values")
        return vals[idx] if idx < len(vals) else ""

    def _set_cell(self, item, col_name, value):
        cols = list(self["columns"])
        idx  = cols.index(col_name)
        vals = list(self.item(item, "values"))
        while len(vals) <= idx:
            vals.append("")
        vals[idx] = value
        self.item(item, values=vals)


# ── Progress dialog ──────────────────────────────────────────────────────────

class ProgressDialog(tk.Toplevel):
    def __init__(self, parent, total: int):
        super().__init__(parent)
        self.title("Processing…")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.total     = total
        self.cancelled = False

        px = parent.winfo_rootx() + parent.winfo_width()  // 2 - 210
        py = parent.winfo_rooty() + parent.winfo_height() // 2 - 65
        self.geometry(f"420x140+{px}+{py}")

        ttk.Label(self, text="Stamping QR codes onto vouchers…",
                  font=("", 10, "bold")).pack(pady=(14, 4))

        self._status = tk.StringVar(value="Starting…")
        ttk.Label(self, textvariable=self._status,
                  foreground="#555").pack()

        self._var = tk.DoubleVar()
        self._pb  = ttk.Progressbar(self, variable=self._var,
                                    maximum=total, length=370)
        self._pb.pack(pady=8, padx=25)

        ttk.Button(self, text="Cancel", command=self._cancel,
                   width=12).pack(pady=(0, 10))

    def update(self, done: int, filename: str):
        self._var.set(done)
        self._status.set(f"({done}/{self.total})  {filename}")
        self.update_idletasks()

    def _cancel(self):
        self.cancelled = True


# ── OCR extraction ───────────────────────────────────────────────────────────

def _preprocess_for_ocr(img: Image.Image, top_pct=0.14, bot_pct=0.28,
                         left_pct=0.0, right_pct=0.45) -> Image.Image:
    """Crop to a specific region, upscale 3×, and sharpen for OCR."""
    w, h = img.size
    img = img.crop((int(w * left_pct), int(h * top_pct),
                    int(w * right_pct), int(h * bot_pct)))
    img = img.resize((img.width * 3, img.height * 3), Image.LANCZOS)
    img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(2.5)
    img = img.filter(ImageFilter.SHARPEN)
    return img


def ocr_extract_fields(path: str) -> dict:
    """
    Run Tesseract OCR on a voucher image and return extracted fields.
    Uses two targeted crops:
      - Pass 1 (14-28% height, left 45%): INVOICE and ACCOUNT
      - Pass 2 (18-24% height, left 45%): DATE (narrow band for accuracy)
    Returns a dict with keys: voucher, client, year, type_label.
    """
    img = Image.open(path)
    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGB")

    cfg = "--psm 6 --oem 3"

    # ── Pass 1: wide crop for INVOICE + ACCOUNT ───────────────────────────────
    text1 = pytesseract.image_to_string(
        _preprocess_for_ocr(img, 0.14, 0.28, 0.0, 0.45), lang="eng", config=cfg)

    voucher = client = year = ""

    m = re.search(r"INVOICE\s*[:\s]\s*(\d{5,})", text1, re.IGNORECASE)
    if m:
        voucher = m.group(1).strip()

    m = re.search(r"ACCOUNT\s*[:\s]\s*([\d]+-[\d]+)", text1, re.IGNORECASE)
    if m:
        raw    = m.group(1).strip()
        parts  = raw.split("-", 1)
        client = parts[1] if len(parts) == 2 else raw

    # ── Pass 2: narrow crop where DATE line always appears ────────────────────
    text2 = pytesseract.image_to_string(
        _preprocess_for_ocr(img, 0.18, 0.24, 0.0, 0.45), lang="eng", config=cfg)

    # First, try proper "DATE : 16-01-2025" match
    m = re.search(r"DATE\s*[:\s=]+\s*(\d{1,2}[-/]\d{1,2}[-/](\d{4}))",
                  text2, re.IGNORECASE)
    if m:
        year = m.group(2)
    else:
        # Fallback: first date-like pattern in narrow crop (OCR may mangle "DATE")
        m = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", text2)
        if m:
            year = m.group(3)

    return {"voucher": voucher, "year": year, "client": client,
            "type_label": TYPE_OPTIONS[0]}




def stamp_qr(src: str, dst: str,
             voucher: str, client: str, year: str, type_code: str):
    """Paste a QR code onto the bottom-left corner of a voucher image."""
    type_num = type_code.replace("T", "")   # "T9" → "9", "T2" → "2"
    data = f"PDS:C1:T{type_num}:Y{year}:V{voucher}:A{client}"

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black",
                            back_color="white").convert("RGB")
    qr_img = qr_img.resize((QR_SIZE, QR_SIZE), Image.LANCZOS)

    img = Image.open(src)

    # Normalise mode (palette / CMYK / greyscale → RGB/RGBA)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    x = QR_MARGIN
    y = img.height - QR_SIZE - QR_MARGIN

    if img.mode == "RGBA":
        img.paste(qr_img.convert("RGBA"), (x, y))
    else:
        img.paste(qr_img, (x, y))

    ext = Path(dst).suffix.lower()
    if ext in (".jpg", ".jpeg"):
        img.save(dst, format="JPEG", quality=100, subsampling=0)
    elif ext == ".png":
        img.save(dst, format="PNG", compress_level=0)
    else:
        img.save(dst, quality=100)


# ── Main application window ──────────────────────────────────────────────────

class VoucherQRApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Petra Drug Store — QR Voucher Stamper")
        self.geometry("960x640")
        self.minsize(780, 500)

        if not DEPS_OK:
            messagebox.showerror(
                "Missing Dependencies",
                f"Required libraries not found:\n{MISSING}\n\n"
                "Install them with:\n  pip install Pillow \"qrcode[pil]\""
            )
            self.destroy()
            return

        self._output_folder = tk.StringVar(value="(not set)")
        self._paths: dict[str, str] = {}   # iid → full file path

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # ── toolbar ──────────────────────────────────────────────────────────
        toolbar = ttk.Frame(self, padding=(8, 6))
        toolbar.grid(row=0, column=0, sticky="ew")

        ttk.Button(toolbar, text="➕  Add Images",
                   command=self._add_images, width=16).pack(side="left", padx=3)
        ttk.Button(toolbar, text="🔍  Auto-read (OCR)",
                   command=self._auto_read_all, width=20).pack(side="left", padx=3)
        ttk.Button(toolbar, text="✔  Verify Data",
                   command=self._verify_all, width=15).pack(side="left", padx=3)
        ttk.Button(toolbar, text="✖  Remove Selected",
                   command=self._remove_selected, width=18).pack(side="left", padx=3)
        ttk.Button(toolbar, text="🗑  Clear All",
                   command=self._clear_all, width=12).pack(side="left", padx=3)

        ttk.Separator(toolbar, orient="vertical").pack(
            side="left", fill="y", padx=10)

        ttk.Label(toolbar, text="Output folder:").pack(side="left")
        ttk.Label(toolbar, textvariable=self._output_folder,
                  foreground="#555", width=36,
                  anchor="w").pack(side="left", padx=4)
        ttk.Button(toolbar, text="📁  Browse…",
                   command=self._set_output, width=12).pack(side="left", padx=3)

        # ── hint ─────────────────────────────────────────────────────────────
        hint = ttk.Frame(self, padding=(10, 0, 10, 2))
        hint.grid(row=1, column=0, sticky="ew")
        ttk.Label(
            hint,
            text="💡  Auto-read fills fields via OCR. ✔ Verify re-scans and shows ✅Yes/❌No match. "
                 "Double-click cells to edit. Duplicate voucher #s are flagged before generating.",
            foreground="#888", font=("", 9)
        ).pack(anchor="w")

        # ── table ─────────────────────────────────────────────────────────────
        table_frame = ttk.Frame(self, padding=(8, 0, 8, 4))
        table_frame.grid(row=2, column=0, sticky="nsew")
        self.rowconfigure(2, weight=1)

        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        cols     = ("filename", "voucher", "client", "year", "type", "match")
        headings = ("Filename", "Voucher # (INVOICE)",
                    "Client # (ACCOUNT)", "Year (DATE)", "Type", "OCR Match")
        widths   = (220, 135, 150, 70, 190, 85)

        self.tree = EditableTreeview(
            table_frame,
            columns=cols,
            show="headings",
            selectmode="extended",
        )
        for col, heading, width in zip(cols, headings, widths):
            self.tree.heading(col, text=heading, anchor="w")
            self.tree.column(col, width=width, minwidth=60, anchor="w")

        # make match column non-editable (read-only cols handled in EditableTreeview)
        self.tree.column("match", width=85, minwidth=60, anchor="center")

        # colour tags for match column
        self.tree.tag_configure("match_yes", foreground="#1a8a1a")
        self.tree.tag_configure("match_no",  foreground="#cc0000")
        self.tree.tag_configure("match_partial", foreground="#b86000")

        vsb = ttk.Scrollbar(table_frame, orient="vertical",
                            command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal",
                            command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set,
                            xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # ── status / generate bar ─────────────────────────────────────────────
        bottom = ttk.Frame(self, padding=(8, 4))
        bottom.grid(row=3, column=0, sticky="ew")

        self._count_var = tk.StringVar(value="0 images loaded")
        ttk.Label(bottom, textvariable=self._count_var,
                  foreground="#666").pack(side="left")

        ttk.Button(
            bottom,
            text="⚡  Generate QR Codes",
            command=self._start_processing,
            width=22,
        ).pack(side="right", padx=4)

    # ── button handlers ───────────────────────────────────────────────────────

    def _add_images(self):
        paths = filedialog.askopenfilenames(
            title="Select Voucher Images",
            filetypes=[
                ("Images", "*.jpg *.jpeg *.png"),
                ("All files", "*.*"),
            ],
        )
        for path in paths:
            if path in self._paths.values():
                continue        # skip duplicates
            iid = self.tree.insert(
                "", "end",
                values=(os.path.basename(path), "", "", "", TYPE_OPTIONS[0], "—"),
            )
            self._paths[iid] = path
        self._refresh_count()

    def _remove_selected(self):
        for iid in self.tree.selection():
            self._paths.pop(iid, None)
            self.tree.delete(iid)
        self._refresh_count()

    def _clear_all(self):
        self.tree.delete(*self.tree.get_children())
        self._paths.clear()
        self._refresh_count()

    def _set_output(self):
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self._output_folder.set(folder)

    def _refresh_count(self):
        n = len(self.tree.get_children())
        self._count_var.set(f"{n} image{'s' if n != 1 else ''} loaded")

    def _auto_read_all(self):
        """Run OCR on every loaded image and fill in the table automatically."""
        items = self.tree.get_children()
        if not items:
            messagebox.showinfo("No Images", "Please add voucher images first.")
            return

        dlg = ProgressDialog(self, total=len(items))
        dlg.title("Reading vouchers…")

        def worker():
            failed = []
            for done, iid in enumerate(items, 1):
                if dlg.cancelled:
                    break
                path     = self._paths[iid]
                filename = os.path.basename(path)
                try:
                    fields = ocr_extract_fields(path)
                    vals   = self.tree.item(iid, "values")
                    # Determine match status right after fill
                    all_found = bool(fields["voucher"] and fields["client"] and fields["year"])
                    match_val = "✅ Yes" if all_found else "⚠️ Partial"
                    tag = "match_yes" if all_found else "match_partial"
                    def _update(iid=iid, fields=fields, vals=vals,
                                match_val=match_val, tag=tag):
                        self.tree.item(iid, values=(
                            vals[0],
                            fields["voucher"],
                            fields["client"],
                            fields["year"],
                            fields["type_label"],
                            match_val,
                        ), tags=(tag,))
                    self.after(0, _update)
                    if not all_found:
                        failed.append(filename)
                except Exception as exc:       # noqa: BLE001
                    failed.append(f"{filename}: {exc}")

                self.after(0, dlg.update, done, filename)

            def finish():
                dlg.destroy()
                if failed:
                    detail = "\n".join(failed[:20])
                    messagebox.showwarning(
                        "OCR incomplete",
                        f"Could not read all fields for {len(failed)} file(s):\n\n"
                        f"{detail}\n\nPlease fill those rows manually.",
                    )
                else:
                    messagebox.showinfo("OCR Done ✅",
                                        "All fields filled successfully!")

            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def _verify_all(self):
        """Re-run OCR and compare against current table values. Update Match column."""
        items = self.tree.get_children()
        if not items:
            messagebox.showinfo("No Images", "Please add voucher images first.")
            return

        dlg = ProgressDialog(self, total=len(items))
        dlg.title("Verifying data…")

        def worker():
            mismatches = []
            for done, iid in enumerate(items, 1):
                if dlg.cancelled:
                    break
                path     = self._paths[iid]
                filename = os.path.basename(path)
                try:
                    ocr     = ocr_extract_fields(path)
                    vals    = self.tree.item(iid, "values")
                    t_vou   = vals[1].strip() if len(vals) > 1 else ""
                    t_cli   = vals[2].strip() if len(vals) > 2 else ""
                    t_year  = vals[3].strip() if len(vals) > 3 else ""

                    vou_ok  = (ocr["voucher"] == t_vou)
                    cli_ok  = (ocr["client"]  == t_cli)
                    year_ok = (ocr["year"]    == t_year)
                    all_ok  = vou_ok and cli_ok and year_ok

                    if all_ok:
                        match_val, tag = "✅ Yes", "match_yes"
                    else:
                        match_val, tag = "❌ No",  "match_no"
                        detail = []
                        if not vou_ok:
                            detail.append(
                                f"  Voucher: table={t_vou!r}  ocr={ocr['voucher']!r}")
                        if not cli_ok:
                            detail.append(
                                f"  Client:  table={t_cli!r}  ocr={ocr['client']!r}")
                        if not year_ok:
                            detail.append(
                                f"  Year:    table={t_year!r}  ocr={ocr['year']!r}")
                        mismatches.append((filename, detail))

                    def _set_match(iid=iid, vals=vals,
                                   match_val=match_val, tag=tag):
                        self.tree.item(iid,
                                       values=(*vals[:5], match_val),
                                       tags=(tag,))
                    self.after(0, _set_match)

                except Exception as exc:                        # noqa: BLE001
                    def _set_err(iid=iid, vals=self.tree.item(iid, "values")):
                        self.tree.item(iid,
                                       values=(*vals[:5], "⚠️ Error"),
                                       tags=("match_partial",))
                    self.after(0, _set_err)

                self.after(0, dlg.update, done, filename)

            def finish():
                dlg.destroy()
                if not mismatches:
                    messagebox.showinfo(
                        "Verification ✅",
                        "All rows match the voucher images perfectly!")
                else:
                    lines = []
                    for fname, details in mismatches[:15]:
                        lines.append(fname)
                        lines.extend(details)
                    if len(mismatches) > 15:
                        lines.append(f"\n…and {len(mismatches)-15} more.")
                    messagebox.showwarning(
                        f"⚠️  {len(mismatches)} Mismatch(es) Found",
                        "The following rows do NOT match the OCR scan:\n\n"
                        + "\n".join(lines)
                        + "\n\nRows marked ❌ No — please correct them manually.",
                    )

            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    # ── processing ────────────────────────────────────────────────────────────

    def _collect_rows(self):
        """
        Validate all rows and return list of
        (src_path, voucher, client, year, type_code).
        Returns None if validation fails.
        """
        rows = []
        seen_vouchers: dict[str, str] = {}   # voucher# → first filename

        for iid in self.tree.get_children():
            vals     = self.tree.item(iid, "values")
            filename = vals[0] if len(vals) > 0 else ""
            voucher  = (vals[1].strip() if len(vals) > 1 else "")
            client   = (vals[2].strip() if len(vals) > 2 else "")
            year     = (vals[3].strip() if len(vals) > 3 else "")
            type_raw = vals[4] if len(vals) > 4 else TYPE_OPTIONS[0]

            if not voucher or not client or not year:
                messagebox.showwarning(
                    "Missing Data",
                    f"Row for '{filename}' is missing required fields.\n\n"
                    "Fill in Voucher #, Client #, and Year for every row.",
                )
                return None

            # Duplicate voucher number check
            if voucher in seen_vouchers:
                messagebox.showwarning(
                    "Duplicate Voucher #",
                    f"Voucher number '{voucher}' appears more than once:\n\n"
                    f"  • {seen_vouchers[voucher]}\n  • {filename}\n\n"
                    "Please correct the duplicate before generating.",
                )
                return None
            seen_vouchers[voucher] = filename

            rows.append((
                self._paths[iid],
                voucher, client, year,
                TYPE_MAP.get(type_raw, "T9"),
            ))
        return rows

    def _start_processing(self):
        if not self.tree.get_children():
            messagebox.showinfo("No Images",
                                "Please add voucher images first.")
            return

        out = self._output_folder.get()
        if out == "(not set)" or not os.path.isdir(out):
            messagebox.showwarning("Output Folder",
                                   "Please select a valid output folder first.")
            return

        rows = self._collect_rows()
        if rows is None:
            return

        dlg = ProgressDialog(self, total=len(rows))

        def worker():
            errors = []
            for done, (src, voucher, client, year, type_code) in enumerate(rows, 1):
                if dlg.cancelled:
                    break

                filename = os.path.basename(src)
                stem     = Path(filename).stem
                ext      = Path(filename).suffix
                dst      = os.path.join(out, f"{stem}_QR{ext}")

                try:
                    stamp_qr(src, dst, voucher, client, year, type_code)
                except Exception as exc:        # noqa: BLE001
                    errors.append(f"{filename}: {exc}")

                self.after(0, dlg.update, done, filename)

            def finish():
                dlg.destroy()
                total_done = len(rows) - len(errors)
                if dlg.cancelled:
                    messagebox.showinfo(
                        "Cancelled",
                        f"Processing cancelled after {total_done} image(s).",
                    )
                elif errors:
                    detail = "\n".join(errors[:20])
                    if len(errors) > 20:
                        detail += f"\n…and {len(errors) - 20} more."
                    messagebox.showerror(
                        "Completed with Errors",
                        f"{total_done} succeeded, {len(errors)} failed:\n\n{detail}",
                    )
                else:
                    messagebox.showinfo(
                        "Done ✅",
                        f"Successfully stamped {len(rows)} voucher(s).\n\n"
                        f"Saved to:\n{out}",
                    )

            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()


# ── entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = VoucherQRApp()
    app.mainloop()
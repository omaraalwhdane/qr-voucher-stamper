#!/usr/bin/env python3
"""
Petra Drug Store — QR Voucher Stamper
Batch-stamps QR codes onto pharmacy voucher images using OCR auto-fill.

Requirements:
    pip install Pillow "qrcode[pil]" pytesseract anthropic
    brew install tesseract
    Set ANTHROPIC_API_KEY env-var (or enter it in the AI Key dialog) to enable
    Claude vision — much more accurate than Tesseract for invoice numbers.
"""

import os
import re
import threading
import time
import tkinter as tk
import json
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import base64
import io

# ── AI providers (optional — falls back to Tesseract when none available) ────
try:
    import anthropic as _anthropic
    ANTHROPIC_OK = True
except ImportError:
    ANTHROPIC_OK = False

try:
    from google import genai as _genai
    GEMINI_OK = True
except ImportError:
    GEMINI_OK = False

AI_AVAILABLE = ANTHROPIC_OK or GEMINI_OK

_CONFIG_PATH = Path.home() / ".petra_stamper.json"

def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text())
    except Exception:
        return {}

def _save_config(data: dict):
    try:
        _CONFIG_PATH.write_text(json.dumps(data, indent=2))
    except Exception:
        pass

def _get_ai_key() -> str:
    return (os.environ.get("ANTHROPIC_API_KEY")
            or _load_config().get("anthropic_api_key", ""))

def _get_gemini_key() -> str:
    return (os.environ.get("GEMINI_API_KEY")
            or _load_config().get("gemini_api_key", ""))

try:
    import qrcode
    import pytesseract
    from PIL import Image, ImageEnhance, ImageFilter
    # Auto-detect Tesseract — bundled (PyInstaller) or system install
    import sys as _sys
    if getattr(_sys, 'frozen', False):
        # Running as a PyInstaller bundle — use bundled tesseract
        _bundle_tess = os.path.join(_sys._MEIPASS, 'tesseract', 'tesseract.exe')
        if os.path.exists(_bundle_tess):
            pytesseract.pytesseract.tesseract_cmd = _bundle_tess
    elif os.name == "nt":
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

# ── Lazurd IT branding ───────────────────────────────────────────────────────
_LAZURD_LOGO_B64 = """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cGUvUmVzb3VyY2VFdmVudCMiCiAgICB4bWxuczpkYz0iaHR0cDovL3B1cmwub3JnL2RjL2VsZW1lbnRzLzEuMS8iCiAgICB4bWxuczpHSU1QPSJodHRwOi8vd3d3LmdpbXAub3JnL3htcC8iCiAgICB4bWxuczpwaG90b3Nob3A9Imh0dHA6Ly9ucy5hZG9iZS5jb20vcGhvdG9zaG9wLzEuMC8iCiAgICB4bWxuczp0aWZmPSJodHRwOi8vbnMuYWRvYmUuY29tL3RpZmYvMS4wLyIKICAgIHhtbG5zOnhtcD0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLyIKICAgeG1wTU06RG9jdW1lbnRJRD0ieG1wLmRpZDpCNzI2QjFFMTNEN0VFNDExOTA1NkFCRERBNUMxNUQ3RiIKICAgeG1wTU06SW5zdGFuY2VJRD0ieG1wLmlpZDowY2RmNzRmZC1kZmY5LTQ3MDYtYjg3Mi02ZGI3NzE4ZTNlNmEiCiAgIHhtcE1NOk9yaWdpbmFsRG9jdW1lbnRJRD0ieG1wLmRpZDpCQTI2QjFFMTNEN0VFNDExOTA1NkFCRERBNUMxNUQ3RiIKICAgZGM6Zm9ybWF0PSJhcHBsaWNhdGlvbi92bmQuYWRvYmUucGhvdG9zaG9wIgogICBHSU1QOkFQST0iMi4wIgogICBHSU1QOlBsYXRmb3JtPSJNYWMgT1MiCiAgIEdJTVA6VGltZVN0YW1wPSIxNjUzMjE3NTMxMjk0Mjc2IgogICBHSU1QOlZlcnNpb249IjIuMTAuMjQiCiAgIHBob3Rvc2hvcDpDb2xvck1vZGU9IjMiCiAgIHBob3Rvc2hvcDpJQ0NQcm9maWxlPSJzUkdCIElFQzYxOTY2LTIuMSIKICAgdGlmZjpPcmllbnRhdGlvbj0iMSIKICAgeG1wOkNyZWF0ZURhdGU9IjIwMTQtMTItMDdUMjE6NDQ6MTgrMDM6MDAiCiAgIHhtcDpDcmVhdG9yVG9vbD0iR0lNUCAyLjEwIgogICB4bXA6TWV0YWRhdGFEYXRlPSIyMDE0LTEyLTA3VDIxOjQ0OjE4KzAzOjAwIgogICB4bXA6TW9kaWZ5RGF0ZT0iMjAxNC0xMi0wN1QyMTo0NDoxOCswMzowMCI+CiAgIDx4bXBNTTpIaXN0b3J5PgogICAgPHJkZjpTZXE+CiAgICAgPHJkZjpsaQogICAgICBzdEV2dDphY3Rpb249ImNyZWF0ZWQiCiAgICAgIHN0RXZ0Omluc3RhbmNlSUQ9InhtcC5paWQ6QkEyNkIxRTEzRDdFRTQxMTkwNTZBQkREQTVDMTVEN0YiCiAgICAgIHN0RXZ0OnNvZnR3YXJlQWdlbnQ9IkFkb2JlIFBob3Rvc2hvcCBDUzYgKFdpbmRvd3MpIgogICAgICBzdEV2dDp3aGVuPSIyMDE0LTEyLTA3VDIxOjQ0OjE4KzAzOjAwIi8+CiAgICAgPHJkZjpsaQogICAgICBzdEV2dDphY3Rpb249InNhdmVkIgogICAgICBzdEV2dDpjaGFuZ2VkPSIvIgogICAgICBzdEV2dDppbnN0YW5jZUlEPSJ4bXAuaWlkOjk4NWIyY2JlLWYxOGItNGFhYy05NTI1LWQ1YzZlM2ZlNmMzNCIKICAgICAgc3RFdnQ6c29mdHdhcmVBZ2VudD0iR2ltcCAyLjEwIChNYWMgT1MpIgogICAgICBzdEV2dDp3aGVuPSIyMDIyLTA1LTIyVDE0OjA1OjMxKzAzOjAwIi8+CiAgICA8L3JkZjpTZXE+CiAgIDwveG1wTU06SGlzdG9yeT4KICA8L3JkZjpEZXNjcmlwdGlvbj4KIDwvcmRmOlJERj4KPC94OnhtcG1ldGE+CiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAKPD94cGFja2V0IGVuZD0idyI/PmpFDAYAAAAGYktHRAD/AP8A/6C9p5MAAAAJcEhZcwAACxMAAAsTAQCanBgAAAAHdElNRQfmBRYLBR9NccNdAAAPIUlEQVR42u2debhWRR3HP/dy2VQQHXczG3O3TE2tBNOw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"""


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


# ── UI string translations ────────────────────────────────────────────────────
_STRINGS = {
    "en": {
        "app_title":        "Petra Drug Store  —  QR Voucher Stamper",
        "app_sub":          "Batch-stamp QR codes onto pharmacy voucher images  •  "
                            "AI-powered OCR auto-fill  •  Duplicate & mismatch detection",
        "btn_add":          "➕  Add Images",
        "btn_folder":       "📂  Folder",
        "btn_autoread":     "🔍  Auto-read",
        "btn_verify":       "✔  Verify",
        "btn_remove":       "✖  Remove",
        "btn_mismatch":     "❌  Mismatches",
        "btn_clear":        "🗑  Clear All",
        "btn_browse":       "Browse…",
        "btn_generate":     "⚡  Generate QR Codes",
        "lbl_outfolder":    "📁  Output Folder:",
        "out_placeholder":  "(click Browse to choose output folder)",
        "col_filename":     "  Filename",
        "col_voucher":      "  Voucher # (INVOICE)",
        "col_client":       "  Client # (ACCOUNT)",
        "col_year":         "  Year",
        "col_type":         "  Type",
        "col_match":        "OCR Match",
        "col_reader":       "Read by",
        "empty_title":      "No images loaded yet",
        "empty_sub":        "Click  ➕ Add Images  or  📂 Folder  to get started,\n"
                            "then  🔍 Auto-read  to extract invoice data automatically.",
        "status_ready":     "Ready  —  no images loaded",
        "stat_image":       "image",
        "stat_images":      "images",
        "stat_matched":     "matched",
        "stat_mismatch":    "mismatch",
        "stat_mismatches":  "mismatches",
        "footer_tag":       "Petra Drug Store  —  QR Voucher Stamper",
        "ai_claude_on":     "✅  Claude: ON",
        "ai_gemini_on":     "🤖  Gemini: ON",
        "ai_key":           "🔑  AI Key",
        "lang_switch":      "عربي",
        "dlg_no_images":    "No Images",
        "dlg_no_images_msg":"Please add voucher images first.",
        "dlg_no_found":     "No Images Found",
        "dlg_already":      "Already Loaded",
        "dlg_already_msg":  "All selected images are already in the table.",
        "dlg_ai_title":     "AI Settings",
        "dlg_ai_heading":   "AI Vision Settings",
        "dlg_ai_desc":      "Claude is the primary AI reader (highest accuracy).\n"
                            "Gemini is used as a free fallback if no Claude key is set.",
        "dlg_claude_key":   "Claude Key  (PRIMARY):",
        "dlg_claude_hint":  "console.anthropic.com  —  most accurate, requires API credit",
        "dlg_gemini_key":   "Gemini Key  (fallback):",
        "dlg_gemini_hint":  "aistudio.google.com  —  free tier, used only if no Claude key",
        "dlg_show_keys":    "Show keys",
        "dlg_save":         "Save",
        "dlg_cancel":       "Cancel",
        "dlg_ai_enabled":   "AI Enabled",
        "progress_reading": "Reading Vouchers…",
        "progress_verifying":"Verifying Data…",
        "sel_title":        "Select Voucher Images",
        "sel_folder":       "Select Folder Containing Voucher Images",
        "out_choose":       "Choose Output Folder",
        "tip_add":          "Select voucher JPG/PNG files  (⌘O)",
        "tip_folder":       "Load all images from a folder",
        "tip_autoread":     "Read INVOICE, DATE, ACCOUNT via AI+OCR  (⌘R)",
        "tip_verify":       "Re-scan and compare table data vs image  (⌘K)",
        "tip_remove":       "Remove selected rows",
        "tip_mismatch":     "Delete all rows where OCR data does not match",
        "tip_clear":        "Remove all rows",
        "tip_browse":       "Choose where stamped images are saved",
        "tip_generate":     "Stamp QR codes onto all loaded images  (⌘↩)",
        "tip_ai":           "Configure Claude API key for AI-powered OCR",
    },
    "ar": {
        "app_title":        "مستودعات البتراء الطبية  —  ختم رمز QR",
        "app_sub":          "ختم رموز QR على صور سندات الصيدلية  •  "
                            "قراءة ذكية تلقائية  •  كشف التكرار والتعارض",
        "btn_add":          "➕  إضافة صور",
        "btn_folder":       "📂  مجلد",
        "btn_autoread":     "🔍  قراءة تلقائية",
        "btn_verify":       "✔  تحقق",
        "btn_remove":       "✖  حذف",
        "btn_mismatch":     "❌  غير متطابق",
        "btn_clear":        "🗑  مسح الكل",
        "btn_browse":       "استعراض…",
        "btn_generate":     "⚡  توليد رموز QR",
        "lbl_outfolder":    "📁  مجلد الإخراج:",
        "out_placeholder":  "(انقر استعراض لاختيار مجلد الإخراج)",
        "col_filename":     "  اسم الملف",
        "col_voucher":      "  رقم السند",
        "col_client":       "  رقم العميل",
        "col_year":         "  السنة",
        "col_type":         "  النوع",
        "col_match":        "تطابق",
        "col_reader":       "قُرئ بـ",
        "empty_title":      "لم يتم تحميل صور بعد",
        "empty_sub":        "انقر  ➕ إضافة صور  أو  📂 مجلد  للبدء،\n"
                            "ثم  🔍 قراءة تلقائية  لاستخراج البيانات.",
        "status_ready":     "جاهز  —  لا توجد صور",
        "stat_image":       "صورة",
        "stat_images":      "صور",
        "stat_matched":     "متطابق",
        "stat_mismatch":    "غير متطابق",
        "stat_mismatches":  "غير متطابقة",
        "footer_tag":       "مستودعات البتراء الطبية  —  ختم رمز QR",
        "ai_claude_on":     "✅  كلود: فعّال",
        "ai_gemini_on":     "🤖  جيميناي: فعّال",
        "ai_key":           "🔑  مفتاح الذكاء",
        "lang_switch":      "English",
        "dlg_no_images":    "لا توجد صور",
        "dlg_no_images_msg":"يرجى إضافة صور السندات أولاً.",
        "dlg_no_found":     "لا توجد صور",
        "dlg_already":      "محمّل مسبقاً",
        "dlg_already_msg":  "جميع الصور المحددة موجودة بالفعل في الجدول.",
        "dlg_ai_title":     "إعدادات الذكاء الاصطناعي",
        "dlg_ai_heading":   "إعدادات رؤية الذكاء الاصطناعي",
        "dlg_ai_desc":      "كلود هو القارئ الذكي الأساسي (أعلى دقة).\n"
                            "جيميناي يُستخدم كاحتياطي مجاني إذا لم يُضبط مفتاح كلود.",
        "dlg_claude_key":   "مفتاح كلود  (أساسي):",
        "dlg_claude_hint":  "console.anthropic.com  —  الأدق، يتطلب رصيداً في الحساب",
        "dlg_gemini_key":   "مفتاح جيميناي  (احتياطي):",
        "dlg_gemini_hint":  "aistudio.google.com  —  مجاني، يُستخدم فقط بدون مفتاح كلود",
        "dlg_show_keys":    "إظهار المفاتيح",
        "dlg_save":         "حفظ",
        "dlg_cancel":       "إلغاء",
        "dlg_ai_enabled":   "تم تفعيل الذكاء الاصطناعي",
        "progress_reading": "جاري قراءة السندات…",
        "progress_verifying":"جاري التحقق من البيانات…",
        "sel_title":        "اختر صور السندات",
        "sel_folder":       "اختر مجلد صور السندات",
        "out_choose":       "اختر مجلد الإخراج",
        "tip_add":          "اختر ملفات JPG/PNG  (⌘O)",
        "tip_folder":       "تحميل جميع الصور من مجلد",
        "tip_autoread":     "قراءة رقم السند والتاريخ والحساب  (⌘R)",
        "tip_verify":       "إعادة الفحص ومقارنة البيانات  (⌘K)",
        "tip_remove":       "حذف الصفوف المحددة",
        "tip_mismatch":     "حذف جميع الصفوف غير المتطابقة",
        "tip_clear":        "مسح جميع الصفوف",
        "tip_browse":       "اختر مجلد حفظ الصور المختومة",
        "tip_generate":     "ختم رموز QR على جميع الصور  (⌘↩)",
        "tip_ai":           "ضبط مفتاح كلود للقراءة الذكية",
    },
}

# ── Design tokens ─────────────────────────────────────────────────────────────
_BG      = "#F8FAFC"   # page background
_SURF    = "#FFFFFF"   # cards / surfaces
_DARK    = "#0D1B2A"   # header / footer navy
_DARK2   = "#162233"   # nav hover
_ACCENT  = "#2563EB"   # primary blue
_ACCH    = "#1D4ED8"   # primary blue hover
_ACCL    = "#DBEAFE"   # primary blue tint
_VIOLET  = "#7C3AED"   # AI / Claude purple
_VIOH    = "#6D28D9"   # purple hover
_VIOL    = "#EDE9FE"   # purple tint
_SUCCESS = "#059669"   # green
_SUCC_L  = "#D1FAE5"   # green tint
_DANGER  = "#DC2626"   # red
_DANH    = "#B91C1C"   # red hover
_DANL    = "#FEE2E2"   # red tint
_TXT1    = "#0F172A"   # primary text
_TXT2    = "#64748B"   # secondary text
_TXT3    = "#94A3B8"   # muted text
_BORDER  = "#E2E8F0"   # dividers
_ROW_E   = "#F8FAFC"   # even table row
_ROW_O   = "#FFFFFF"   # odd table row


def _chip(parent, text, bg, fg, cmd,
          hover=None, size=11, bold=False, px=14, py=7, tip=None):
    """Flat modern label-button — bg/fg colour works reliably on macOS."""
    b = tk.Label(
        parent, text=text, bg=bg, fg=fg,
        font=("Helvetica", size, "bold" if bold else "normal"),
        padx=px, pady=py, cursor="hand2",
    )
    b.bind("<Button-1>",        lambda _e: cmd())
    b.bind("<ButtonRelease-1>", lambda _e: None)   # prevents focus dot
    if hover:
        b.bind("<Enter>", lambda _e, w=b, c=hover: w.configure(bg=c))
        b.bind("<Leave>", lambda _e, w=b, c=bg:    w.configure(bg=c))
    if tip:
        Tooltip(b, tip)
    return b


# ── Progress dialog ──────────────────────────────────────────────────────────
class ProgressDialog(tk.Toplevel):
    def __init__(self, parent, total, title="Processing…"):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.configure(bg=_SURF)
        self.total = total
        self.cancelled = False
        self._t0 = time.time()

        pw, ph = 520, 188
        px = parent.winfo_rootx() + parent.winfo_width()  // 2 - pw // 2
        py = parent.winfo_rooty() + parent.winfo_height() // 2 - ph // 2
        self.geometry(f"{pw}x{ph}+{px}+{py}")

        # Top accent strip
        tk.Frame(self, bg=_ACCENT, height=3).pack(fill="x")

        body = tk.Frame(self, bg=_SURF)
        body.pack(fill="both", expand=True, padx=26, pady=(18, 8))

        tk.Label(body, text=title, bg=_SURF, fg=_TXT1,
                 font=("Helvetica", 14, "bold"),
                 anchor="w").pack(fill="x", pady=(0, 5))

        self._status = tk.StringVar(value="Starting…")
        tk.Label(body, textvariable=self._status,
                 bg=_SURF, fg=_TXT2,
                 font=("Helvetica", 10), anchor="w").pack(fill="x", pady=(0, 10))

        self._var = tk.DoubleVar()
        ttk.Progressbar(body, variable=self._var,
                        maximum=total, length=460).pack(fill="x", pady=(0, 8))

        row = tk.Frame(body, bg=_SURF)
        row.pack(fill="x")
        self._pct = tk.StringVar(value="0%")
        self._eta = tk.StringVar(value="")
        tk.Label(row, textvariable=self._pct, bg=_SURF, fg=_ACCENT,
                 font=("Helvetica", 11, "bold")).pack(side="left")
        tk.Label(row, textvariable=self._eta, bg=_SURF, fg=_TXT3,
                 font=("Helvetica", 10)).pack(side="right")

        foot = tk.Frame(self, bg=_SURF)
        foot.pack(fill="x", padx=26, pady=(6, 16))
        _chip(foot, "Cancel", _DANL, _DANGER, self._cancel,
              hover="#FECACA", px=16, py=6).pack(side="right")

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
def _preprocess_for_ocr(img, top_pct, bot_pct, right_pct=0.55):
    w, h = img.size
    img = img.crop((0, int(h * top_pct), int(w * right_pct), int(h * bot_pct)))
    img = img.resize((img.width * 3, img.height * 3), Image.LANCZOS)
    img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(2.0)
    return img.filter(ImageFilter.SHARPEN)


def _ocr(img, top_pct, bot_pct, right_pct=0.55, cfg="--psm 6 --oem 3"):
    return pytesseract.image_to_string(
        _preprocess_for_ocr(img, top_pct, bot_pct, right_pct),
        lang="eng", config=cfg)


def _find_invoice(text):
    """Find INVOICE number — robust against OCR colon artifacts and split numbers."""
    for line in text.splitlines():
        if re.search(r"invoice", line, re.IGNORECASE):
            after = re.sub(r".*?invoice", "", line, flags=re.IGNORECASE)
            nums = re.findall(r"\d+", after)
            if not nums:
                continue
            # Case 1 — separate artifact group: "99 2229258" → skip "99" → "2229258"
            while nums and nums[0] in ("9", "99"):
                nums.pop(0)
            if not nums:
                continue
            # If the first group is already ≥5 digits, use it directly
            # (fused colon artifacts are handled by _find_invoice_image)
            if len(nums[0]) >= 5:
                return nums[0]
            # Otherwise join groups until we reach ≥5 digits (handles split numbers)
            joined = ""
            for n in nums:
                joined += n
                if len(joined) >= 5:
                    return joined
    return ""


def _find_invoice_image(img, top_pct=0.12, bot_pct=0.30, right_pct=0.55):
    """Extract invoice number spatially: find the INVOICE word bounding box,
    crop from just past that word to the end of the line, and re-OCR with a
    digit-only whitelist.

    Starting close to the word (5 px gap) ensures the first digit is never
    clipped.  The digit whitelist causes the colon to be read as whitespace or
    a lone '9'; the trailing stripping logic removes any such artifact.
    """
    processed = _preprocess_for_ocr(img, top_pct, bot_pct, right_pct)
    pw, ph = processed.size
    try:
        data = pytesseract.image_to_data(
            processed, lang="eng", config="--psm 6 --oem 3",
            output_type=pytesseract.Output.DICT)
    except Exception:
        return ""
    for i, word in enumerate(data["text"]):
        if not re.match(r"invoice", (word or "").strip(), re.IGNORECASE):
            continue
        x = data["left"][i]
        y = data["top"][i]
        w = data["width"][i]
        h = data["height"][i]
        # Start just 5 px past the word's right edge so we never clip the
        # first digit of the number.  The colon between the word and the number
        # will be in the crop, but the digit whitelist makes Tesseract output
        # it as whitespace or at worst a single '9'.
        x_start = x + w + 5
        x_end   = min(x_start + 480, pw)
        if x_start >= x_end:
            continue
        crop = processed.crop((x_start, max(0, y - 8), x_end, min(ph, y + h + 8)))
        raw = pytesseract.image_to_string(
            crop, lang="eng",
            config="--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789")
        nums = re.findall(r"\d+", raw)
        if not nums:
            continue
        # Strip leading isolated colon artifact ("9" or "99" as a separate group)
        while nums and nums[0] in ("9", "99"):
            nums.pop(0)
        if not nums:
            continue
        # Strip leading fused colon artifact from an 8+ digit group
        if len(nums[0]) >= 8:
            remainder = nums[0].lstrip("9")
            stripped  = len(nums[0]) - len(remainder)
            if 1 <= stripped <= 2 and len(remainder) >= 6:
                nums[0] = remainder
        # Join any split groups
        joined = ""
        for n in nums:
            joined += n
            if len(joined) >= 5:
                return joined
    return ""


def _find_account(text):
    """Find ACCOUNT number — returns the part after the dash (client code)."""
    for line in text.splitlines():
        if re.search(r"account", line, re.IGNORECASE):
            after = re.sub(r".*?account", "", line, flags=re.IGNORECASE)
            # Normalise dashes, then find X-YYYYYYY pattern
            after = re.sub(r"[–—]", "-", after)
            m = re.search(r"(\d+)-(\d+)", after)
            if m:
                return m.group(2)   # part after the dash
            # Fallback: largest number ≥5 digits on line
            nums = re.findall(r"\d+", after)
            large = [n for n in nums if len(n) >= 5]
            if large:
                return max(large, key=len)
    return ""


def _fix_year(year_str):
    """Correct common OCR misreads in 4-digit years (e.g. 2622 → 2022)."""
    if not year_str or len(year_str) != 4:
        return year_str
    try:
        y = int(year_str)
    except ValueError:
        return year_str
    if 2000 <= y <= 2099:
        return year_str  # already valid
    # Try replacing each digit position with a corrected guess
    # Most common: '6'→'0' in position 2 or 3 (e.g. 2622→2022, 2026→2026)
    corrected = list(year_str)
    ocr_fixes = {"6": "0", "8": "0", "5": "5", "O": "0", "o": "0", "l": "1", "I": "1"}
    # Position 1 must be '0' for years 20xx
    if corrected[0] == "2" and corrected[1] in ocr_fixes:
        candidate = "2" + ocr_fixes[corrected[1]] + corrected[2] + corrected[3]
        try:
            if 2000 <= int(candidate) <= 2099:
                return candidate
        except ValueError:
            pass
    # Position 2: 20x? — check if pos 2 is an OCR artifact
    if corrected[0] == "2" and corrected[1] == "0":
        candidate = "20" + ocr_fixes.get(corrected[2], corrected[2]) + corrected[3]
        try:
            if 2000 <= int(candidate) <= 2099:
                return candidate
        except ValueError:
            pass
    return year_str


def _find_year(text):
    """Find year from DATE line or any dd-mm-yyyy / dd/mm/yyyy pattern."""
    for line in text.splitlines():
        if re.search(r"date", line, re.IGNORECASE):
            m = re.search(r"\d{1,2}[-/]\d{1,2}[-/](\d{4})", line)
            if m:
                return _fix_year(m.group(1))
    # Fallback: any date pattern in full text
    m = re.search(r"\b\d{1,2}[-/]\d{1,2}[-/](\d{4})\b", text)
    if m:
        return _fix_year(m.group(1))
    return ""


_AI_PROMPT = (
    "This is a cropped region of a pharmacy invoice printed in English.\n"
    "Extract exactly three values:\n"
    "1. invoice — the digits immediately after the colon on the INVOICE line "
    "(e.g. \"INVOICE :2229258\" → \"2229258\").\n"
    "2. account — the digits AFTER the hyphen on the ACCOUNT line "
    "(e.g. \"ACCOUNT:1-11237883\" → \"11237883\").\n"
    "3. year — the 4-digit year from the DATE line.\n\n"
    "Reply with ONLY valid JSON, nothing else:\n"
    "{\"invoice\": \"...\", \"account\": \"...\", \"year\": \"...\"}"
)


def _parse_ai_json(raw: str) -> dict:
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {}
    try:
        data = json.loads(m.group())
        return {
            "voucher": re.sub(r"\D", "", str(data.get("invoice", ""))),
            "client":  re.sub(r"\D", "", str(data.get("account", ""))),
            "year":    re.sub(r"\D", "", str(data.get("year", ""))),
        }
    except Exception:
        return {}


def _crop_header_b64(img) -> str:
    """Return base-64 JPEG of the invoice header (top-left region)."""
    w, h = img.size
    crop = img.crop((0, int(h * 0.08), int(w * 0.60), int(h * 0.35)))
    buf = io.BytesIO()
    crop.save(buf, format="JPEG", quality=92)
    return base64.b64encode(buf.getvalue()).decode()


def _extract_with_gemini(img) -> dict:
    """Use Google Gemini Flash (free tier) to extract invoice fields."""
    if not GEMINI_OK:
        return {"_error": "google-genai not installed"}
    key = _get_gemini_key()
    if not key:
        return {}
    try:
        from google.genai import types as _gtypes
        client = _genai.Client(api_key=key)
        w, h = img.size
        crop = img.crop((0, int(h * 0.08), int(w * 0.60), int(h * 0.35)))
        buf = io.BytesIO()
        crop.save(buf, format="JPEG", quality=92)
        buf.seek(0)
        part_img  = _gtypes.Part.from_bytes(data=buf.read(),
                                             mime_type="image/jpeg")
        part_text = _gtypes.Part.from_text(text=_AI_PROMPT)
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[_gtypes.Content(role="user",
                                      parts=[part_img, part_text])],
        )
        result = _parse_ai_json(resp.text.strip())
        if result:
            result["reader"] = "Gemini"
        return result
    except Exception as e:
        return {"_error": f"Gemini: {e}"}


def _extract_with_claude(img) -> dict:
    """Use Claude vision (primary) to extract invoice fields."""
    if not ANTHROPIC_OK:
        return {"_error": "anthropic not installed"}
    key = _get_ai_key()
    if not key:
        return {}
    try:
        img_b64 = _crop_header_b64(img)
        client = _anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=128,
            messages=[{"role": "user", "content": [
                {"type": "image",
                 "source": {"type": "base64",
                            "media_type": "image/jpeg",
                            "data": img_b64}},
                {"type": "text", "text": _AI_PROMPT},
            ]}],
        )
        r = _parse_ai_json(msg.content[0].text.strip())
        if r:
            r["reader"] = "Claude"
        return r
    except Exception as e:
        return {"_error": f"Claude: {e}"}


def _extract_with_ai(img) -> dict:
    """Try Claude (primary) then Gemini (fallback) to extract invoice fields.

    Returns a dict with 'voucher', 'client', 'year', 'reader', or {} on failure.
    Errors are stored under '_error' so the caller can surface them.
    """
    # Claude first — paid API, highest accuracy
    result = _extract_with_claude(img)
    if result.get("voucher"):
        return result
    claude_err = result.get("_error", "")

    # Gemini fallback
    result = _extract_with_gemini(img)
    if result.get("voucher"):
        return result
    gemini_err = result.get("_error", "")

    combined_err = " | ".join(filter(None, [claude_err, gemini_err]))
    return {"_error": combined_err or "No AI provider available"}


def ocr_extract_fields(path):
    img = Image.open(path)
    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGB")

    voucher = client = year = ""

    reader  = "Tesseract"
    ai_error = ""

    # ── AI pass: Gemini (free) or Claude vision — no colon artifacts ──────────
    ai = _extract_with_ai(img)
    ai_error = ai.get("_error", "")
    if ai.get("voucher"):
        voucher = ai.get("voucher", "")
        client  = ai.get("client",  "")
        year    = ai.get("year",    "")
        reader  = ai.get("reader",  "AI")
    if voucher and client and year:
        return {"voucher": voucher, "year": year, "client": client,
                "type_label": TYPE_OPTIONS[0], "reader": reader,
                "ai_error": ai_error}

    # ── Pass 1: tight crop (fast, works on standard layout) ──────────────────
    text1 = _ocr(img, 0.12, 0.30)
    voucher = _find_invoice(text1)
    client  = _find_account(text1)
    year    = _find_year(_ocr(img, 0.15, 0.26))

    # ── Pass 1b: image-based invoice extraction when text result is suspect ───
    if not voucher or len(voucher) >= 8 or len(voucher) <= 6:
        img_voucher = _find_invoice_image(img, 0.12, 0.30)
        if img_voucher:
            voucher = img_voucher

    # ── Pass 2: wider crop if anything is still missing ───────────────────────
    if not voucher or not client or not year:
        text_wide = _ocr(img, 0.10, 0.40, right_pct=0.65)
        if not voucher:
            voucher = _find_invoice(text_wide)
        if not client:
            client = _find_account(text_wide)
        if not year:
            year = _find_year(text_wide)

    # ── Pass 2b: wider image-based extraction if still suspect ────────────────
    if not voucher or len(voucher) >= 8 or len(voucher) <= 6:
        img_voucher = _find_invoice_image(img, 0.10, 0.40, right_pct=0.65)
        if img_voucher:
            voucher = img_voucher

    # ── Pass 3: full-page scan as last resort ─────────────────────────────────
    if not voucher or not client or not year:
        text_full = pytesseract.image_to_string(
            img.convert("L"), lang="eng", config="--psm 3 --oem 3")
        if not voucher:
            voucher = _find_invoice(text_full)
        if not client:
            client = _find_account(text_full)
        if not year:
            year = _find_year(text_full)

    return {"voucher": voucher, "year": year, "client": client,
            "type_label": TYPE_OPTIONS[0], "reader": reader,
            "ai_error": ai_error}



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


# ── Check QR stamping ────────────────────────────────────────────────────────
_CHECK_AI_PROMPT = (
    "This is a bank cheque image. Read the MICR line at the very bottom "
    "of the cheque (the special magnetic ink characters printed on the bottom edge).\n"
    "Extract exactly two values:\n"
    "1. bank_id — the 2-digit bank routing / bank code (e.g. '02').\n"
    "2. account — the full customer account number (the long number, e.g. '6901963631300100').\n"
    "The MICR line typically looks like: \"CCCCC D\" BB\" TTTT:ACCOUNT\"\n"
    "where BB is the bank code (2 digits) and ACCOUNT is the long number after the colon.\n\n"
    "Reply with ONLY valid JSON, nothing else:\n"
    "{\"bank_id\": \"...\", \"account\": \"...\"}"
)


def _crop_check_bottom_b64(img) -> str:
    """Return base-64 JPEG of the full cheque (used for AI to find the MICR line)."""
    buf = io.BytesIO()
    rgb = img.convert("RGB")
    rgb.save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()


def _parse_check_ai_json(raw: str) -> dict:
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {}
    try:
        data = json.loads(m.group())
        return {
            "bank_id": re.sub(r"\D", "", str(data.get("bank_id", ""))),
            "account": re.sub(r"\D", "", str(data.get("account", ""))),
        }
    except Exception:
        return {}


def _extract_check_with_claude(img) -> dict:
    if not ANTHROPIC_OK:
        return {"_error": "anthropic not installed"}
    key = _get_ai_key()
    if not key:
        return {}
    try:
        img_b64 = _crop_check_bottom_b64(img)
        client  = _anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=128,
            messages=[{"role": "user", "content": [
                {"type": "image",
                 "source": {"type": "base64",
                            "media_type": "image/jpeg",
                            "data": img_b64}},
                {"type": "text", "text": _CHECK_AI_PROMPT},
            ]}],
        )
        r = _parse_check_ai_json(msg.content[0].text.strip())
        if r:
            r["reader"] = "Claude"
        return r
    except Exception as e:
        return {"_error": f"Claude: {e}"}


def _extract_check_with_gemini(img) -> dict:
    if not GEMINI_OK:
        return {"_error": "google-genai not installed"}
    key = _get_gemini_key()
    if not key:
        return {}
    try:
        from google.genai import types as _gtypes
        client  = _genai.Client(api_key=key)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=90)
        buf.seek(0)
        part_img  = _gtypes.Part.from_bytes(data=buf.read(), mime_type="image/jpeg")
        part_text = _gtypes.Part.from_text(text=_CHECK_AI_PROMPT)
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[_gtypes.Content(role="user",
                                      parts=[part_img, part_text])],
        )
        r = _parse_check_ai_json(resp.text.strip())
        if r:
            r["reader"] = "Gemini"
        return r
    except Exception as e:
        return {"_error": f"Gemini: {e}"}


def _extract_check_with_tesseract(img) -> dict:
    """Fallback: OCR bottom 12% strip and parse MICR-like patterns."""
    w, h = img.size
    strip = img.crop((0, int(h * 0.88), w, h))
    strip = strip.resize((strip.width * 3, strip.height * 3), Image.LANCZOS)
    strip = strip.convert("L")
    strip = ImageEnhance.Contrast(strip).enhance(2.5)
    strip = strip.filter(ImageFilter.SHARPEN)
    text = pytesseract.image_to_string(strip, lang="eng",
                                       config="--psm 7 --oem 3")
    # Remove MICR symbols and keep digits + spaces
    cleaned = re.sub(r'[^\d\s:]', ' ', text)

    bank_id = ""
    account = ""

    # Find the short 2-digit bank code (often surrounded by spaces after a separator)
    m_bank = re.search(r'\b(\d{2})\b', cleaned)
    if m_bank:
        bank_id = m_bank.group(1)

    # Find the longest number as the account
    numbers = re.findall(r'\d+', cleaned)
    if numbers:
        account = max(numbers, key=len)

    return {"bank_id": bank_id, "account": account,
            "reader": "Tesseract", "_error": ""}


def extract_check_fields(path) -> dict:
    """Extract bank_id and account from a cheque image."""
    img = Image.open(path)
    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGB")

    # Try AI providers first
    ai_error = ""
    result = _extract_check_with_claude(img)
    if not (result.get("bank_id") and result.get("account")):
        ai_error = result.get("_error", "")
        result2  = _extract_check_with_gemini(img)
        if result2.get("bank_id") and result2.get("account"):
            result = result2
        else:
            ai_error = " | ".join(filter(None,
                                          [ai_error, result2.get("_error", "")]))
            result = _extract_check_with_tesseract(img)

    result["ai_error"] = ai_error
    return result


def stamp_check_qr(src, dst, bank_id, account):
    """Generate QR with format PDS:C1:B{bank_id}:A{account} and stamp top-right."""
    data   = f"PDS:C1:B{bank_id}:A{account}"
    qr     = qrcode.QRCode(version=None,
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

    # Top-left corner
    x = QR_MARGIN
    y = QR_MARGIN
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


# ── Check Stamper window ──────────────────────────────────────────────────────
class CheckStamperWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Check QR Stamper — Petra Drug Store")
        self.geometry("900x680")
        self.minsize(720, 480)
        self.configure(background=_DARK)

        self._output_folder = tk.StringVar(value="")
        self._paths: dict[str, str] = {}
        self._out_placeholder_active = True

        self._build_ui()

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self._build_header()
        self._build_toolbar()
        self._build_table()
        self._build_statusbar()
        self._build_footer()

    def _build_header(self):
        hdr = tk.Frame(self, bg=_DARK)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(2, weight=1)

        tk.Frame(hdr, bg="#059669", width=4).grid(
            row=0, column=0, rowspan=3, sticky="ns")

        tk.Label(hdr, text="🏦", font=("", 26),
                 bg=_DARK, fg="white").grid(
            row=0, column=1, rowspan=2, padx=(16, 12), pady=10)

        tk.Label(hdr, text="Check QR Stamper",
                 bg=_DARK, fg="#F1F5F9",
                 font=("Helvetica", 14, "bold")).grid(
            row=0, column=2, sticky="w", pady=(12, 2))

        tk.Label(hdr,
                 text="Stamp QR codes onto bank cheques  •  "
                      "Reads MICR line (Bank ID + Account)  •  QR in top-right corner",
                 bg=_DARK, fg="#94A3B8",
                 font=("Helvetica", 10)).grid(
            row=1, column=2, sticky="w", pady=(0, 10))

        tk.Frame(hdr, bg="#059669", height=2).grid(
            row=2, column=0, columnspan=4, sticky="ew")

    def _build_toolbar(self):
        outer = tk.Frame(self, bg=_SURF)
        outer.grid(row=1, column=0, sticky="ew")
        outer.columnconfigure(0, weight=1)

        row1 = tk.Frame(outer, bg=_SURF)
        row1.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 6))

        _chip(row1, "➕  Add Cheques", _ACCL, _ACCENT,
              self._add_images, hover="#BFDBFE").pack(side="left", padx=(0, 4))
        _chip(row1, "📂  Folder", _ACCL, _ACCENT,
              self._add_folder, hover="#BFDBFE").pack(side="left", padx=(0, 10))

        tk.Frame(row1, bg=_BORDER, width=1).pack(side="left", fill="y", padx=(0, 10))

        _chip(row1, "🔍  Auto-read MICR", _ACCENT, _SURF,
              self._auto_read_all, hover=_ACCH, bold=True).pack(side="left", padx=(0, 10))

        tk.Frame(row1, bg=_BORDER, width=1).pack(side="left", fill="y", padx=(0, 10))

        _chip(row1, "✖  Remove", _DANL, _DANGER,
              self._remove_selected, hover="#FECACA").pack(side="left", padx=(0, 4))
        _chip(row1, "🗑  Clear All", _DANL, _DANGER,
              self._clear_all, hover="#FECACA").pack(side="left")

        # Row 2: output folder
        row2 = tk.Frame(outer, bg=_SURF)
        row2.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
        row2.columnconfigure(1, weight=1)

        tk.Label(row2, text="📁  Output Folder:", bg=_SURF, fg=_TXT2,
                 font=("Helvetica", 10, "bold")).grid(row=0, column=0,
                                                       sticky="w", padx=(0, 8))

        self._out_lbl = tk.Label(row2, textvariable=self._output_folder,
                                 bg=_SURF, fg=_ACCENT,
                                 font=("Helvetica", 10), cursor="hand2", anchor="w")
        self._out_lbl.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self._out_lbl.bind("<Button-1>", lambda _e: self._set_output())
        self._output_folder.set("(click Browse to choose output folder)")

        _chip(row2, "Browse…", _BG, _TXT2, self._set_output,
              hover=_BORDER, px=12, py=5).grid(row=0, column=2)

        tk.Frame(outer, bg=_BORDER, height=1).grid(row=2, column=0, sticky="ew")

    def _build_table(self):
        outer = tk.Frame(self, bg=_BG)
        outer.grid(row=2, column=0, sticky="nsew", padx=10, pady=(6, 0))
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        cols     = ("filename", "bank_id", "account", "status", "reader")
        headings = ("  Filename", "  Bank ID (B)", "  Account (A)", "  Status", "Read by")
        widths   = (280, 100, 260, 120, 95)

        self.tree = ttk.Treeview(outer, columns=cols, show="headings",
                                 selectmode="extended")
        for col, heading, width in zip(cols, headings, widths):
            self.tree.heading(col, text=heading, anchor="w")
            self.tree.column(col, width=width, minwidth=60, anchor="w",
                             stretch=(col in ("filename", "account")))
        self.tree.column("status", anchor="center", stretch=False)
        self.tree.column("reader", anchor="center", width=95, stretch=False)

        self.tree.tag_configure("odd",      background=_ROW_O)
        self.tree.tag_configure("even",     background=_ROW_E)
        self.tree.tag_configure("ok",       foreground=_SUCCESS,
                                            font=("Helvetica", 11, "bold"))
        self.tree.tag_configure("partial",  foreground="#D97706")
        self.tree.tag_configure("error",    foreground=_DANGER,
                                            background="#FFF5F5")

        vsb = ttk.Scrollbar(outer, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(outer, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # Empty state overlay
        self._empty = tk.Frame(outer, bg=_SURF)
        self._empty.grid(row=0, column=0, sticky="nsew")
        self._empty.rowconfigure(0, weight=1)
        self._empty.columnconfigure(0, weight=1)
        inner_e = tk.Frame(self._empty, bg=_SURF)
        inner_e.grid(row=0, column=0)
        tk.Label(inner_e, text="🏦", font=("", 48),
                 bg=_SURF, fg=_BORDER).pack(pady=(0, 10))
        tk.Label(inner_e, text="No cheque images loaded yet",
                 bg=_SURF, fg=_TXT2,
                 font=("Helvetica", 15, "bold")).pack()
        tk.Label(inner_e,
                 text="Click  ➕ Add Cheques  or  📂 Folder  to get started,\n"
                      "then  🔍 Auto-read MICR  to extract bank data automatically.",
                 bg=_SURF, fg=_TXT3,
                 font=("Helvetica", 11), justify="center").pack(pady=(6, 0))

    def _build_statusbar(self):
        bar = tk.Frame(self, bg="#F1F5F9")
        bar.grid(row=3, column=0, sticky="ew")
        tk.Frame(bar, bg=_BORDER, height=1).pack(fill="x", side="top")
        inner = tk.Frame(bar, bg="#F1F5F9")
        inner.pack(fill="x", padx=14, pady=9)

        self._stat_var = tk.StringVar(value="Ready  —  no cheques loaded")
        tk.Label(inner, textvariable=self._stat_var,
                 bg="#F1F5F9", fg=_TXT2,
                 font=("Helvetica", 10)).pack(side="left")

        _chip(inner, "⚡  Stamp QR Codes", "#059669", _SURF,
              self._start_processing,
              hover="#047857", bold=True, size=12, px=22, py=9).pack(side="right")

    def _build_footer(self):
        tk.Frame(self, bg="#059669", height=2).grid(row=4, column=0, sticky="ew")
        footer = tk.Frame(self, bg=_DARK)
        footer.grid(row=5, column=0, sticky="ew")
        inner = tk.Frame(footer, bg=_DARK)
        inner.pack(fill="x", padx=16, pady=8)
        tk.Label(inner,
                 text="QR format:  PDS:C1:B{bank_id}:A{account}  •  Stamped top-left",
                 bg=_DARK, fg="#4A6A8A",
                 font=("Helvetica", 9)).pack(side="left")

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _restripe(self):
        for iid in self.tree.get_children():
            cur  = [t for t in self.tree.item(iid, "tags")
                    if t not in ("odd", "even")]
            base = "even" if self.tree.index(iid) % 2 == 0 else "odd"
            self.tree.item(iid, tags=(base, *cur))

    def _refresh_stats(self):
        items = self.tree.get_children()
        n = len(items)
        if n == 0:
            self._stat_var.set("Ready  —  no cheques loaded")
            self._empty.lift()
            return
        self._empty.lower()
        ok = sum(1 for i in items if "ok" in self.tree.item(i, "tags"))
        parts = [f"🏦 {n} cheque{'s' if n != 1 else ''}"]
        if ok:
            parts.append(f"✅ {ok} read")
        out = self._output_folder.get()
        if out and os.path.isdir(out):
            short = out if len(out) <= 44 else "…" + out[-42:]
            parts.append(f"📁 {short}")
        self._stat_var.set("   •   ".join(parts))

    # ── Button handlers ───────────────────────────────────────────────────────
    def _add_images(self):
        paths = filedialog.askopenfilenames(
            title="Select Cheque Images",
            filetypes=[("Images", "*.jpg *.jpeg *.png"), ("All files", "*.*")])
        self._insert_paths(list(paths))

    def _add_folder(self):
        folder = filedialog.askdirectory(title="Select Folder Containing Cheque Images")
        if not folder:
            return
        exts  = {".jpg", ".jpeg", ".png"}
        paths = sorted(str(p) for p in Path(folder).iterdir()
                       if p.is_file() and p.suffix.lower() in exts)
        if not paths:
            messagebox.showinfo("No Images Found",
                                f"No JPG/PNG images found in:\n{folder}")
            return
        self._insert_paths(paths)

    def _insert_paths(self, paths):
        existing  = set(self._paths.values())
        new_paths = [p for p in paths if p not in existing]
        if not new_paths:
            messagebox.showinfo("Already Loaded",
                                "All selected images are already in the table.")
            return
        for path in new_paths:
            iid = self.tree.insert("", "end",
                                   values=(os.path.basename(path),
                                           "", "", "—", ""))
            self._paths[iid] = path
        self._restripe()
        self._refresh_stats()

        if not self._output_folder.get() or \
           not os.path.isdir(self._output_folder.get()):
            first_dir = os.path.dirname(list(self._paths.values())[0])
            out = os.path.join(first_dir, "CheckQR_Output")
            os.makedirs(out, exist_ok=True)
            self._output_folder.set(out)
            self._out_placeholder_active = False

        messagebox.showinfo(
            "Cheques Added",
            f"{len(new_paths)} cheque image(s) loaded.\n\n"
            "Click  🔍 Auto-read MICR  to extract bank data automatically.")

    def _remove_selected(self):
        for iid in self.tree.selection():
            self._paths.pop(iid, None)
            self.tree.delete(iid)
        self._restripe()
        self._refresh_stats()

    def _clear_all(self):
        self.tree.delete(*self.tree.get_children())
        self._paths.clear()
        self._refresh_stats()

    def _set_output(self):
        folder = filedialog.askdirectory(title="Choose Output Folder")
        if folder:
            self._output_folder.set(folder)
            self._out_placeholder_active = False
            self._refresh_stats()

    # ── MICR auto-read ────────────────────────────────────────────────────────
    def _auto_read_all(self):
        items = self.tree.get_children()
        if not items:
            messagebox.showinfo("No Cheques", "Please add cheque images first.")
            return
        dlg = ProgressDialog(self, total=len(items), title="Reading MICR Lines…")

        def worker():
            failed = []
            for done, iid in enumerate(items, 1):
                if dlg.cancelled:
                    break
                path  = self._paths[iid]
                fname = os.path.basename(path)
                try:
                    f      = extract_check_fields(path)
                    bid    = f.get("bank_id", "")
                    acc    = f.get("account", "")
                    reader = f.get("reader", "Tesseract")
                    all_ok = bool(bid and acc)
                    status = "✅ Ready" if all_ok else "⚠️ Partial"
                    etag   = "ok" if all_ok else "partial"

                    def _upd(iid=iid, bid=bid, acc=acc,
                             status=status, etag=etag, reader=reader,
                             fname=fname):
                        base = "even" if self.tree.index(iid) % 2 == 0 else "odd"
                        self.tree.item(iid,
                                       values=(fname, bid, acc, status, reader),
                                       tags=(base, etag))
                    self.after(0, _upd)
                    if not all_ok:
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
                        "MICR Read — Partial Results",
                        f"{n - len(failed)} of {n} cheques read successfully.\n\n"
                        f"Could not fully read {len(failed)} file(s):\n"
                        + "\n".join(failed[:15])
                        + "\n\nDouble-click a cell to fill it manually.")
                else:
                    messagebox.showinfo(
                        "MICR Read Complete ✅",
                        f"All {n} cheques read successfully!\n\n"
                        "Click  ⚡ Stamp QR Codes  to generate.")
            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    # ── Generation ────────────────────────────────────────────────────────────
    def _start_processing(self):
        items = self.tree.get_children()
        if not items:
            messagebox.showinfo("No Cheques", "Please add cheque images first.")
            return
        out = self._output_folder.get()
        if not out or not os.path.isdir(out):
            messagebox.showwarning("Output Folder",
                                   "Please select a valid output folder first.")
            return

        rows, skipped = [], []
        for iid in items:
            vals   = self.tree.item(iid, "values")
            fname  = vals[0] if vals else ""
            bid    = vals[1].strip() if len(vals) > 1 else ""
            acc    = vals[2].strip() if len(vals) > 2 else ""
            if not (bid and acc):
                skipped.append(fname)
                continue
            rows.append((self._paths[iid], bid, acc))

        if not rows:
            messagebox.showwarning(
                "Nothing to Process",
                "No rows have complete data (Bank ID + Account).\n\n"
                "Run  🔍 Auto-read MICR  first, then try again.")
            return

        if skipped:
            proceed = messagebox.askyesno(
                "Some Rows Skipped",
                f"⚠️  {len(skipped)} row(s) have missing data and will be skipped.\n"
                f"✅  {len(rows)} row(s) will be stamped.\n\nProceed?")
            if not proceed:
                return

        dlg = ProgressDialog(self, total=len(rows), title="Stamping QR Codes…")

        def worker():
            errors = []
            for done, (src, bid, acc) in enumerate(rows, 1):
                if dlg.cancelled:
                    break
                fname = os.path.basename(src)
                dst   = os.path.join(out,
                                     Path(fname).stem + "_QR" + Path(fname).suffix)
                try:
                    stamp_check_qr(src, dst, bid, acc)
                except Exception as exc:
                    errors.append(f"{fname}: {exc}")
                self.after(0, dlg.update, done, fname)

            def finish():
                dlg.destroy()
                ok = len(rows) - len(errors)
                if dlg.cancelled:
                    messagebox.showinfo("Cancelled",
                                        f"Stopped after {ok} cheque(s) stamped.")
                elif errors:
                    messagebox.showerror(
                        "Done with Errors",
                        f"{ok} succeeded  •  {len(errors)} failed:\n\n"
                        + "\n".join(errors[:20]))
                else:
                    messagebox.showinfo(
                        "Done ✅",
                        f"Successfully stamped {len(rows)} cheque(s)!\n\n"
                        f"Saved to:\n{out}")
            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()


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
        self._lang: str = _load_config().get("lang", "en")
        self._lw:   dict = {}          # language-switchable widgets
        self._out_placeholder_active = True

        self._setup_styles()
        self._build_ui()
        self._bind_shortcuts()

    # ── Styles ────────────────────────────────────────────────────────────────
    def _setup_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")

        s.configure(".", font=("Helvetica", 11))
        s.configure("TFrame", background=_BG)
        s.configure("TLabel", background=_BG)

        # Treeview
        s.configure("Treeview",
                    background=_SURF, fieldbackground=_SURF,
                    foreground=_TXT1, rowheight=34,
                    font=("Helvetica", 11))
        s.configure("Treeview.Heading",
                    background=_DARK, foreground="#FFFFFF",
                    font=("Helvetica", 11, "bold"),
                    relief="flat", padding=(10, 10))
        s.map("Treeview",
              background=[("selected", _ACCL)],
              foreground=[("selected", _TXT1)])
        s.map("Treeview.Heading",
              background=[("active", _DARK2)])

        # Scrollbars — slim
        s.configure("TScrollbar",
                    troughcolor=_BG, background=_BORDER,
                    relief="flat", width=6)
        s.map("TScrollbar", background=[("active", _TXT3)])

        # Separator & progress
        s.configure("TSeparator", background=_BORDER)
        s.configure("TProgressbar",
                    troughcolor=_BORDER, background=_ACCENT,
                    thickness=6, relief="flat")

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
        self.configure(background=_DARK)

        self._build_header()     # row 0
        self._build_toolbar()    # row 1
        self._build_table()      # row 2
        self._build_statusbar()  # row 3
        self._build_footer()     # row 4+5

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self):
        T = _STRINGS[self._lang]
        hdr = tk.Frame(self, bg=_DARK)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(2, weight=1)

        # Left accent strip
        tk.Frame(hdr, bg=_ACCENT, width=4).grid(
            row=0, column=0, rowspan=3, sticky="ns")

        # Icon
        tk.Label(hdr, text="🏥", font=("", 28),
                 bg=_DARK, fg="white").grid(
            row=0, column=1, rowspan=2, padx=(16, 12), pady=12)

        lbl_title = tk.Label(hdr, text=T["app_title"],
                             bg=_DARK, fg="#F1F5F9",
                             font=("Helvetica", 15, "bold"))
        lbl_title.grid(row=0, column=2, sticky="w", pady=(14, 2))
        self._lw["app_title"] = lbl_title

        lbl_sub = tk.Label(hdr, text=T["app_sub"],
                           bg=_DARK, fg="#94A3B8",
                           font=("Helvetica", 10))
        lbl_sub.grid(row=1, column=2, sticky="w", pady=(0, 12))
        self._lw["app_sub"] = lbl_sub

        # Check Stamper button (opens new window)
        check_btn = _chip(hdr, "🏦  Check Stamper",
                          "#064E3B", "#34D399", self._open_check_stamper,
                          hover="#065F46", size=11, bold=True, px=14, py=6)
        check_btn.grid(row=0, column=3, rowspan=2, padx=(0, 8), pady=8)

        # Language toggle button (top-right of header)
        lang_btn = _chip(hdr, T["lang_switch"],
                         "#1A3255", "#7EB8DC", self._toggle_lang,
                         hover="#1E3D66", size=11, bold=True, px=14, py=6)
        lang_btn.grid(row=0, column=4, rowspan=2, padx=(0, 16), pady=8)
        self._lw["lang_switch"] = lang_btn

        # Bottom rule
        tk.Frame(hdr, bg=_ACCENT, height=2).grid(
            row=2, column=0, columnspan=4, sticky="ew")

    # ── Toolbar ───────────────────────────────────────────────────────────────
    def _build_toolbar(self):
        T = _STRINGS[self._lang]
        outer = tk.Frame(self, bg=_SURF)
        outer.grid(row=1, column=0, sticky="ew")
        outer.columnconfigure(0, weight=1)

        # ── Row 1: action buttons ─────────────────────────────────────────────
        row1 = tk.Frame(outer, bg=_SURF)
        row1.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 6))

        def _add(key, bg, fg, cmd, hover, bold=False, tip_key=None):
            b = _chip(row1, T[key], bg, fg, cmd,
                      hover=hover, bold=bold,
                      tip=T.get(tip_key or ("tip_" + key.replace("btn_", ""))))
            self._lw[key] = b
            return b

        _add("btn_add",    _ACCL, _ACCENT, self._add_images,    "#BFDBFE",
             tip_key="tip_add").pack(side="left", padx=(0, 4))
        _add("btn_folder", _ACCL, _ACCENT, self._add_folder,    "#BFDBFE",
             tip_key="tip_folder").pack(side="left", padx=(0, 10))

        tk.Frame(row1, bg=_BORDER, width=1).pack(side="left", fill="y", padx=(0, 10))

        _add("btn_autoread", _ACCENT, _SURF, self._auto_read_all, _ACCH,
             bold=True, tip_key="tip_autoread").pack(side="left", padx=(0, 4))
        _add("btn_verify",   _ACCENT, _SURF, self._verify_all,    _ACCH,
             bold=True, tip_key="tip_verify").pack(side="left", padx=(0, 10))

        tk.Frame(row1, bg=_BORDER, width=1).pack(side="left", fill="y", padx=(0, 10))

        _add("btn_remove",   _DANL, _DANGER, self._remove_selected,  "#FECACA",
             tip_key="tip_remove").pack(side="left", padx=(0, 4))
        _add("btn_mismatch", _DANL, _DANGER, self._remove_mismatches, "#FECACA",
             tip_key="tip_mismatch").pack(side="left", padx=(0, 4))
        _add("btn_clear",    _DANL, _DANGER, self._clear_all,         "#FECACA",
             tip_key="tip_clear").pack(side="left")

        # AI indicator (right)
        self._ai_btn = _chip(row1, T["ai_key"], _VIOL, _VIOLET,
                             self._show_ai_settings, hover="#DDD6FE",
                             tip=T["tip_ai"])
        self._ai_btn.pack(side="right")
        self._refresh_ai_btn()

        # ── Row 2: output folder ───────────────────────────────────────────────
        row2 = tk.Frame(outer, bg=_SURF)
        row2.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
        row2.columnconfigure(1, weight=1)

        lbl_of = tk.Label(row2, text=T["lbl_outfolder"], bg=_SURF, fg=_TXT2,
                          font=("Helvetica", 10, "bold"))
        lbl_of.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._lw["lbl_outfolder"] = lbl_of

        self._out_lbl = tk.Label(row2, textvariable=self._output_folder,
                                 bg=_SURF, fg=_ACCENT,
                                 font=("Helvetica", 10),
                                 cursor="hand2", anchor="w")
        self._out_lbl.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self._out_lbl.bind("<Button-1>", lambda _e: self._set_output())
        self._output_folder.set(T["out_placeholder"])

        b_browse = _chip(row2, T["btn_browse"], _BG, _TXT2, self._set_output,
                         hover=_BORDER, px=12, py=5, tip=T["tip_browse"])
        b_browse.grid(row=0, column=2)
        self._lw["btn_browse"] = b_browse

        # Bottom border
        tk.Frame(outer, bg=_BORDER, height=1).grid(row=2, column=0, sticky="ew")

    # ── Table ─────────────────────────────────────────────────────────────────
    def _build_table(self):
        outer = tk.Frame(self, bg=_BG)
        outer.grid(row=2, column=0, sticky="nsew", padx=10, pady=(6, 0))
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        cols      = ("filename", "voucher", "client", "year", "type", "match", "reader")
        headings  = ("  Filename", "  Voucher # (INVOICE)",
                     "  Client # (ACCOUNT)", "  Year", "  Type", "OCR Match", "Read by")
        widths    = (250, 145, 155, 70, 200, 100, 95)
        stretches = (True, False, False, False, True, False, False)

        self.tree = EditableTreeview(outer, columns=cols,
                                     show="headings",
                                     selectmode="extended")
        for col, heading, width, stretch in zip(cols, headings, widths, stretches):
            self.tree.heading(col, text=heading, anchor="w")
            self.tree.column(col, width=width, minwidth=60, anchor="w",
                             stretch=stretch)
        self.tree.column("year",   anchor="center", stretch=False)
        self.tree.column("match",  anchor="center", width=100, stretch=False)
        self.tree.column("reader", anchor="center", width=95,  stretch=False)

        # Row + state tags
        self.tree.tag_configure("odd",          background=_ROW_O)
        self.tree.tag_configure("even",         background=_ROW_E)
        self.tree.tag_configure("match_yes",    foreground=_SUCCESS,
                                                font=("Helvetica", 11, "bold"))
        self.tree.tag_configure("match_no",     foreground=_DANGER,
                                                background="#FFF5F5",
                                                font=("Helvetica", 11, "bold"))
        self.tree.tag_configure("match_partial",foreground="#D97706")

        vsb = ttk.Scrollbar(outer, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(outer, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # Right-click context menu
        self._ctx_menu = tk.Menu(self, tearoff=0,
                                 bg=_SURF, fg=_TXT1,
                                 activebackground=_ACCL,
                                 activeforeground=_TXT1,
                                 relief="flat", bd=1)
        self._ctx_menu.add_command(label="🔬  Debug OCR — show raw text",
                                   command=self._debug_ocr_selected)
        self.tree.bind("<Button-3>", self._on_right_click)
        self.tree.bind("<Button-2>", self._on_right_click)

        # Empty state — sits on top of the tree when there are no rows
        self._empty = tk.Frame(outer, bg=_SURF)
        self._empty.grid(row=0, column=0, sticky="nsew")
        self._empty.rowconfigure(0, weight=1)
        self._empty.columnconfigure(0, weight=1)

        inner_e = tk.Frame(self._empty, bg=_SURF)
        inner_e.grid(row=0, column=0)
        T = _STRINGS[self._lang]
        tk.Label(inner_e, text="📂", font=("", 52),
                 bg=_SURF, fg=_BORDER).pack(pady=(0, 10))
        lbl_et = tk.Label(inner_e, text=T["empty_title"],
                          bg=_SURF, fg=_TXT2,
                          font=("Helvetica", 16, "bold"))
        lbl_et.pack()
        self._lw["empty_title"] = lbl_et

        lbl_es = tk.Label(inner_e, text=T["empty_sub"],
                          bg=_SURF, fg=_TXT3,
                          font=("Helvetica", 11), justify="center")
        lbl_es.pack(pady=(6, 0))
        self._lw["empty_sub"] = lbl_es

    # ── Status bar ────────────────────────────────────────────────────────────
    def _build_statusbar(self):
        bar = tk.Frame(self, bg="#F1F5F9")
        bar.grid(row=3, column=0, sticky="ew")
        tk.Frame(bar, bg=_BORDER, height=1).pack(fill="x", side="top")

        inner = tk.Frame(bar, bg="#F1F5F9")
        inner.pack(fill="x", padx=14, pady=9)

        self._stat_var = tk.StringVar(value="Ready  —  no images loaded")
        tk.Label(inner, textvariable=self._stat_var,
                 bg="#F1F5F9", fg=_TXT2,
                 font=("Helvetica", 10)).pack(side="left")

        T = _STRINGS[self._lang]
        gen = _chip(inner, T["btn_generate"],
                    _ACCENT, _SURF, self._start_processing,
                    hover=_ACCH, bold=True, size=12, px=22, py=9,
                    tip=T["tip_generate"])
        gen.pack(side="right")
        self._lw["btn_generate"] = gen

    # ── Footer ────────────────────────────────────────────────────────────────
    def _build_footer(self):
        # Thin accent rule above footer
        tk.Frame(self, bg=_ACCENT, height=2).grid(row=4, column=0, sticky="ew")

        footer = tk.Frame(self, bg=_DARK)
        footer.grid(row=5, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)

        inner = tk.Frame(footer, bg=_DARK)
        inner.pack(fill="x", padx=16, pady=9)

        lbl_tag = tk.Label(inner, text=_STRINGS[self._lang]["footer_tag"],
                           bg=_DARK, fg="#4A6A8A",
                           font=("Helvetica", 9))
        lbl_tag.pack(side="left")
        self._lw["footer_tag"] = lbl_tag

        right = tk.Frame(inner, bg=_DARK)
        right.pack(side="right")

        try:
            raw = base64.b64decode(_LAZURD_LOGO_B64)
            pil_img = Image.open(io.BytesIO(raw)).convert("RGBA")
            r, g, b, a = pil_img.split()
            bg_img = Image.new("RGBA", pil_img.size, (13, 27, 42, 255))
            bg_img.paste(pil_img, mask=a)
            h = 22
            w = int(pil_img.width * h / pil_img.height)
            pil_img = bg_img.resize((w, h), Image.LANCZOS)
            from PIL import ImageTk
            self._lazurd_logo_img = ImageTk.PhotoImage(pil_img)
            tk.Label(right, image=self._lazurd_logo_img,
                     bg=_DARK).pack(side="left", padx=(0, 7))
        except Exception:
            pass

        tk.Label(right, text="Built by  Lazurd IT",
                 bg=_DARK, fg="#F1F5F9",
                 font=("Helvetica", 9, "bold")).pack(side="left")
        tk.Label(right, text="  •  lazurdit.com",
                 bg=_DARK, fg="#4A6A8A",
                 font=("Helvetica", 9)).pack(side="left")


    def _open_check_stamper(self):
        """Open the Check QR Stamper window."""
        win = CheckStamperWindow(self)
        win.focus_set()

    # ── Language switching ────────────────────────────────────────────────────
    def _t(self, key: str) -> str:
        return _STRINGS[self._lang].get(key, _STRINGS["en"].get(key, key))

    def _toggle_lang(self):
        self._lang = "ar" if self._lang == "en" else "en"
        cfg = _load_config()
        cfg["lang"] = self._lang
        _save_config(cfg)
        self._apply_lang()

    def _apply_lang(self):
        T = _STRINGS[self._lang]
        # update plain text widgets
        for key, widget in self._lw.items():
            if key in T:
                widget.configure(text=T[key])
        # update tree column headings
        col_map = [
            ("filename", "col_filename"), ("voucher", "col_voucher"),
            ("client",   "col_client"),   ("year",    "col_year"),
            ("type",     "col_type"),     ("match",   "col_match"),
            ("reader",   "col_reader"),
        ]
        for col, key in col_map:
            self.tree.heading(col, text=T[key])
        # update output folder placeholder if still showing it
        if self._out_placeholder_active:
            self._output_folder.set(T["out_placeholder"])
        # update window title
        self.title(T["app_title"])
        # re-render dynamic texts
        self._refresh_stats()
        self._refresh_ai_btn()

    def _restripe(self):
        for iid in self.tree.get_children():
            cur = [t for t in self.tree.item(iid, "tags")
                   if t not in ("odd", "even")]
            base = "even" if self.tree.index(iid) % 2 == 0 else "odd"
            self.tree.item(iid, tags=(base, *cur))

    def _refresh_stats(self):
        T   = _STRINGS[self._lang]
        items = self.tree.get_children()
        n = len(items)
        if n == 0:
            self._stat_var.set(T["status_ready"])
            self._empty.lift()
            return
        self._empty.lower()
        yes = sum(1 for i in items if "match_yes" in self.tree.item(i, "tags"))
        no  = sum(1 for i in items if "match_no"  in self.tree.item(i, "tags"))
        img_word = T["stat_image"] if n == 1 else T["stat_images"]
        parts = [f"📄 {n} {img_word}"]
        if yes: parts.append(f"✅ {yes} {T['stat_matched']}")
        if no:
            mm = T["stat_mismatch"] if no == 1 else T["stat_mismatches"]
            parts.append(f"❌ {no} {mm}")
        out = self._output_folder.get()
        if out and os.path.isdir(out):
            short = out if len(out) <= 44 else "…" + out[-42:]
            parts.append(f"📁 {short}")
        self._stat_var.set("   •   ".join(parts))

    # ── Button handlers ───────────────────────────────────────────────────────
    def _add_images(self):
        paths = filedialog.askopenfilenames(
            title=self._t("sel_title"),
            filetypes=[("Images", "*.jpg *.jpeg *.png"), ("All files", "*.*")])
        self._insert_paths(list(paths))

    def _add_folder(self):
        folder = filedialog.askdirectory(title=self._t("sel_folder"))
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
                                           "", "", "", TYPE_OPTIONS[0], "—", ""))
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

    def _on_right_click(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self._ctx_menu.post(event.x_root, event.y_root)

    def _debug_ocr_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        path = self._paths.get(sel[0])
        if not path:
            return
        import threading
        def run():
            try:
                from PIL import Image
                img = Image.open(path)
                if img.mode not in ("RGB", "RGBA", "L"):
                    img = img.convert("RGB")
                t1 = _ocr(img, 0.12, 0.30)
                t2 = _ocr(img, 0.10, 0.40, right_pct=0.65)
                result = ocr_extract_fields(path)
                msg = (
                    f"File: {os.path.basename(path)}\n\n"
                    f"── Extracted ──\n"
                    f"  INVOICE : {result['voucher'] or '(not found)'}\n"
                    f"  ACCOUNT : {result['client'] or '(not found)'}\n"
                    f"  YEAR    : {result['year'] or '(not found)'}\n\n"
                    f"── OCR Raw Text (pass 1) ──\n{t1}\n\n"
                    f"── OCR Raw Text (pass 2) ──\n{t2}"
                )
            except Exception as exc:
                msg = f"Error: {exc}"
            self.after(0, lambda: _show_debug(msg))

        def _show_debug(msg):
            win = tk.Toplevel(self)
            win.title("OCR Debug")
            win.geometry("600x500")
            txt = tk.Text(win, wrap="word", font=("Courier", 10), padx=8, pady=8)
            sb  = ttk.Scrollbar(win, command=txt.yview)
            txt.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y")
            txt.pack(fill="both", expand=True)
            txt.insert("1.0", msg)
            txt.config(state="disabled")

        threading.Thread(target=run, daemon=True).start()

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
        folder = filedialog.askdirectory(title=self._t("out_choose"))
        if folder:
            self._output_folder.set(folder)
            self._out_placeholder_active = False
            self._refresh_stats()

    # ── OCR workers ───────────────────────────────────────────────────────────
    def _run_ocr_worker(self, title, process_fn):
        items = self.tree.get_children()
        if not items:
            messagebox.showinfo(self._t("dlg_no_images"), self._t("dlg_no_images_msg"))
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
            messagebox.showinfo(self._t("dlg_no_images"), self._t("dlg_no_images_msg"))
            return
        dlg = ProgressDialog(self, total=len(items), title=self._t("progress_reading"))

        def worker():
            failed = []
            ai_warned = False      # suppress repeated AI error dialogs
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

                    ai_err  = f.get("ai_error", "")
                    reader  = f.get("reader", "Tesseract")

                    def _upd(iid=iid, f=f, vals=vals, mval=mval,
                             etag=etag, reader=reader):
                        base = "even" if self.tree.index(iid) % 2 == 0 else "odd"
                        self.tree.item(iid, values=(
                            vals[0], f["voucher"], f["client"],
                            f["year"], f["type_label"], mval, reader),
                            tags=(base, etag))
                    self.after(0, _upd)

                    if ai_err and not ai_warned:
                        ai_warned = True
                        is_quota = "RESOURCE_EXHAUSTED" in ai_err or "429" in ai_err
                        is_auth  = "authentication" in ai_err.lower() or "401" in ai_err
                        is_missing = "not installed" in ai_err
                        def _warn_ai(err=ai_err, is_q=is_quota,
                                     is_a=is_auth, is_m=is_missing):
                            if is_m:
                                msg = ("AI library not installed.\n\n"
                                       "Run in Command Prompt:\n"
                                       "    pip install anthropic\n\n"
                                       "Then restart the app.\n"
                                       "Fell back to Tesseract OCR for this batch.")
                            elif is_a:
                                msg = ("Claude API key is invalid or expired.\n\n"
                                       "Go to  🔑 AI Key  in the toolbar to update it.\n\n"
                                       "Fell back to Tesseract OCR.")
                            elif is_q:
                                msg = ("Claude API quota reached.\n\n"
                                       "Options:\n"
                                       "  • Check your usage at console.anthropic.com\n"
                                       "  • Add a Gemini key in  🔑 AI Key  as a fallback\n\n"
                                       "Remaining files fell back to Tesseract OCR.")
                            else:
                                msg = (f"AI error: {err}\n\nFell back to Tesseract OCR.")
                            messagebox.showwarning("AI Read Failed", msg)
                        self.after(0, _warn_ai)

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
                    # Build a detailed message showing what was/wasn't found
                    detail_lines = []
                    for entry in failed[:15]:
                        detail_lines.append(entry)
                    msg = (
                        f"{n - len(failed)} of {n} vouchers read successfully.\n\n"
                        f"Could not fully read {len(failed)} file(s):\n"
                        + "\n".join(detail_lines)
                        + ("\n…" if len(failed) > 15 else "")
                        + "\n\nTip: Double-click a cell to fill it manually.\n"
                        "Or use  🔍 Debug OCR  (right-click a row) to see raw text."
                    )
                    messagebox.showwarning("OCR — Partial Results", msg)
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
            messagebox.showinfo(self._t("dlg_no_images"), self._t("dlg_no_images_msg"))
            return
        dlg = ProgressDialog(self, total=len(items), title=self._t("progress_verifying"))

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
                                       values=(*vals[:6], mval, vals[6] if len(vals) > 6 else ""),
                                       tags=(base, etag))
                    self.after(0, _set)
                except Exception as exc:
                    def _err(iid=iid, vals=self.tree.item(iid, "values")):
                        base = "even" if self.tree.index(iid) % 2 == 0 else "odd"
                        self.tree.item(iid,
                                       values=(*vals[:5], "⚠️ Error", vals[6] if len(vals) > 6 else ""),
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
            messagebox.showinfo(self._t("dlg_no_images"), self._t("dlg_no_images_msg"))
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


    # ── AI key helpers ────────────────────────────────────────────────────────
    def _refresh_ai_btn(self):
        if _get_ai_key():
            bg, fg, hov = _SUCC_L, _SUCCESS, "#A7F3D0"
            label = self._t("ai_claude_on")
        elif _get_gemini_key():
            bg, fg, hov = _VIOL, _VIOLET, "#DDD6FE"
            label = self._t("ai_gemini_on")
        else:
            bg, fg, hov = _VIOL, _VIOLET, "#DDD6FE"
            label = self._t("ai_key")
        self._ai_btn.configure(text=label, bg=bg, fg=fg)
        self._ai_btn.bind("<Enter>", lambda _e, w=self._ai_btn, c=hov: w.configure(bg=c))
        self._ai_btn.bind("<Leave>", lambda _e, w=self._ai_btn, c=bg:  w.configure(bg=c))

    def _show_ai_settings(self):
        T   = _STRINGS[self._lang]
        dlg = tk.Toplevel(self)
        dlg.title(T["dlg_ai_title"])
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.configure(bg=_SURF)

        # Top accent strip
        tk.Frame(dlg, bg=_ACCENT, height=3).grid(
            row=0, column=0, columnspan=2, sticky="ew")

        pad = dict(padx=16, pady=5)

        tk.Label(dlg, text=T["dlg_ai_heading"],
                 bg=_SURF, fg=_TXT1,
                 font=("Helvetica", 13, "bold")).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 4))

        tk.Label(dlg, text=T["dlg_ai_desc"],
                 bg=_SURF, fg=_TXT2,
                 font=("Helvetica", 10)).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 12))

        # Claude
        tk.Label(dlg, text=T["dlg_claude_key"],
                 bg=_SURF, fg=_ACCENT,
                 font=("Helvetica", 10, "bold")).grid(
            row=3, column=0, sticky="w", **pad)
        claude_var   = tk.StringVar(value=_get_ai_key())
        claude_entry = ttk.Entry(dlg, textvariable=claude_var, width=52, show="*")
        claude_entry.grid(row=3, column=1, sticky="ew", **pad)

        tk.Label(dlg, text=T["dlg_claude_hint"],
                 bg=_SURF, fg=_ACCENT,
                 font=("Helvetica", 9)).grid(
            row=4, column=1, sticky="w", padx=16, pady=(0, 10))

        # Gemini
        tk.Label(dlg, text=T["dlg_gemini_key"],
                 bg=_SURF, fg=_TXT2,
                 font=("Helvetica", 10)).grid(
            row=5, column=0, sticky="w", **pad)
        gemini_var   = tk.StringVar(value=_get_gemini_key())
        gemini_entry = ttk.Entry(dlg, textvariable=gemini_var, width=52, show="*")
        gemini_entry.grid(row=5, column=1, sticky="ew", **pad)

        tk.Label(dlg, text=T["dlg_gemini_hint"],
                 bg=_SURF, fg=_TXT2,
                 font=("Helvetica", 9)).grid(
            row=6, column=1, sticky="w", padx=16, pady=(0, 8))

        # Show keys
        show_var = tk.BooleanVar(value=False)
        def toggle_show():
            s = "" if show_var.get() else "*"
            gemini_entry.configure(show=s)
            claude_entry.configure(show=s)
        ttk.Checkbutton(dlg, text=T["dlg_show_keys"], variable=show_var,
                        command=toggle_show).grid(
            row=7, column=1, sticky="w", padx=16, pady=(0, 6))

        # Buttons
        btn_frame = tk.Frame(dlg, bg=_SURF)
        btn_frame.grid(row=8, column=0, columnspan=2, sticky="e", padx=16, pady=12)

        def save():
            gk = gemini_var.get().strip()
            ck = claude_var.get().strip()
            cfg = _load_config()
            cfg["gemini_api_key"]    = gk
            cfg["anthropic_api_key"] = ck
            _save_config(cfg)
            if gk: os.environ["GEMINI_API_KEY"]    = gk
            if ck: os.environ["ANTHROPIC_API_KEY"] = ck
            self._refresh_ai_btn()
            dlg.destroy()
            if ck or gk:
                provider = "Claude" if ck else "Gemini"
                messagebox.showinfo(
                    T["dlg_ai_enabled"],
                    f"{provider} vision is now active.\n"
                    "Auto-read will use AI as the primary reader.")

        _chip(btn_frame, T["dlg_save"], _ACCENT, _SURF, save,
              hover=_ACCH, bold=True, px=18, py=7).pack(side="right", padx=(6, 0))
        _chip(btn_frame, T["dlg_cancel"], _BG, _TXT2, dlg.destroy,
              hover=_BORDER, px=16, py=7).pack(side="right")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = VoucherQRApp()
    app.mainloop()

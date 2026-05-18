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
import base64
import io

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
_LAZURD_LOGO_B64 = """iVBORw0KGgoAAAANSUhEUgAAAXkAAAA3CAYAAADpJjqVAAAJUnpUWHRSYXcgcHJvZmlsZSB0eXBlIGV4aWYAAHjapZhZkmytDYTfWYWXAAIhWA5jhHfg5fvTqeq+Pfwv166KrjODUCpTeTqc//z7hn/xkVJaKGqt9lojn9JLl8FOi6/PeH5TLM/v87H+3kvfz4ds74eEU5ltfh22+tqmj/PvBz62abCnXwZq631hfr/Qy3v89mMgeW2yR+T7+z1Qfw+U5XUhvQcYr2XF2pt9XcI8r+1+P/ekgb/gP6V9D/vXsZG9rcyTRU5OOfIrubwCyP4nIQ92lF8OuDHl8uVMey/FEfinhOc/58Nz4Z3gz0/7jdbn3g+0RN85+olWkY/ZfiS5fm7/8XxI+uNC/pxfvs5c2ntPfpyXV/zh23Lef/fudu95rW6USqrre1EfS3z2uG8ylE/dAqHVaPwpQ9jz7XwbVb0ohR1XnHxX6kmA66aSdhrppvNsV1qEWOQEMXZEluTnZMsmXVZ+4cc3XbHc884NFBewZ87KZyzpmbbHFZ7ZGjPvxK2SGCx5KfztN/ztA/d6SafkuRR9ckVcIp5swnDk/JfbQCTdd1L1SfDH9+fHcc0gqJ5lp0gnsfM1xNT0RwnyA3TmRmX74mCy/R6AFDG1EkzKIABqKWuqKZqIpUQiGwANQodMMkEgqcomSCk5V7Bp4lPziKXnVlHhdOA8YgYSmms2sOl5AFYpSv1YadTQ0KxFVauaNu06aq6laq3VqovisGwlmFo1s2bdRsutNG21WWutt9GlZ0RTe+3WW+99DOYcjDx4enDDGFNmnmVqmHXabLPPsSifVZauumy11dfYsvNGP3bdttvue5x0KKVTjp567LTTz7iU2s3hlqu3Xrvt9js+UXvD+uv7F6ilN2ryIOU32idqnDX7GCK5nKhjBmASSgJxcwgoaHHMYkuliCPnmMUusEKFINUx28kRA8FykuhNH9gFeSHqyP1fuAUr33CT/xW54ND9JXK/cfsn1La3ofUg9mKhJzVm2Ec+5p55794rmnO1pjPP1U4kV4LdMflLY8Wxz1wKLuQn7Q2PiiZtkKH4rrf0uMrOZZDieTWfJrOO3LaIhs0yma2OsYetdHQRc7pz3TviaNQDgRYZtveYdM2uuVnOe62h5+ZJoyvOw3CaKlcQaWP2doamRYzq8jsLC+/XVgWlfBGjcgEQkjfSvUbefXLCWd3Dsr5jUbIIIlvtrHFzrSI93jXvkk06t1JYq6e52ibGMhNLOEZlLN1Idy49DCDZF4W+88zbdzoU1rVtNw8GOuv0p6ms094H9H0/nGPuUe7tZU2yH/aiqatSwrHlM7V3u3XNlFCsuF6CBDSyh/aFvu+5VwNKXEzelWroPZ0iLZw7p4Mmxu25ngJ8s/TanEndEgjUsbf1lW45ZVdjYbOoC7iRnrHJ3vVOeyzdk+9a3KPU07JT+m12JSlJa+MU8trmtT5k7nwQdkUxeXiuTDKy9BtvuIPF+7q5gYVHnX2ASz11S+4U0Z3jnhFNB4yoiIQtCm8yEwTaxXf3LSMsJjFCOpTnXh4ZxCxbgBSmd1Z8ZlaXmiylpask+A80Win2Cr9wbDM22ueiBSiX8zCPz6tmzE5SKIviJjV7qP0LpLAfLmenk/SxwvoO6jhU1IQ9q5Y8sQ8ZbwgVWqOSBZlAxbpQc2UV0KqDK5EtXUQmI6+4kIOUJyasYwvAo1EXBOVTtIuG3P2wrLaboYLs+uSh3APVj3cRROZuFMAzLW0Q4WQqtZmzrSzTIhJ4qYGuB1UCzEM/xFagww0tcvTT7eGFPccwC4pqzSiXOlQlTfmqDafFtk/jeWp0V78487F1i0cRRkU60C9S0nKZJmMjzvO553WLUwPq7uQp5mS1fJZCYW4tLBpvejNGy7PPkssU5wBuij5B30ebSl0nXno7SnjxTfC0b6mHikoYOXQn1TwRDWIvYcs5C50A6NVvf8BnWVCe/oQ80ALA8yDv+wy5ZxeKsp+SPcuuYZkqLR0TQY1Uf6RUWENTArg5J8RpF83benvVNjeqRRPRtY/tgUmnkRA4Zm6xvgFqF7+mQEqRjorYy9An9ZmirnMS0k6p0XpKPegNSdaKpGmj4Kh0F4TuqhFSxcJEa3PtmE/VMxvMQctQQR2UJQQTmOmlU2qTcm6ChLCmMVnCtppoOTGcqHBtUmqXZJGl6FlKrKrC9GLI5tYOEyyvg9IDoQvshP+nohXe9lTnCa0l8UYxEXUUlOZHpLwQyWiwExXLhwbWd6Ot66M8tS6W+NKMzMBY/nUrXEMozEgGlQXhqBL4Ma7NyqCeLrr8cn1YXrmIBwz1fvZQh/ygRSjkCBegV6IKURbepiI0RI0TKmaPqaCSsC1IsJdt5woJG4Uo60vjYnxUboZH5LT/XvpNKLKMNcZCHngryFQbwleG0buhAKl3Cas0JDBCj57kXtkk20cRKtqoJ9Rj2Yys47fyUaX38G7tq40T02qTZB/eKoViNV536Yuwh7Klw2eIzgBY3kGTpKqdu16knQgS/gRn1Zw3FctQw4+nXCopSem1rJs24kXOIryD0FADNiPWOsTTgbWpeDVqC28ZWKpQ1vi005YZJPghZqqDBQAMhNjZhenwBtoTtXgs8voDa8fSYAvG0UMWL1qcIQ+o+GUphWxgdjT9OmNoe+wOK5HpU0/LAsWLNaIQN1rLOxJ0hz0TWYEJo+JiSMLRursaLTEJlMGXIWO7L9tHBJ/RTwuaMdy4jwUG2RypvAHuNGR9xD1REBrMaC+zNP3twyol784J7DXljngVXvyQOcort7QXZiY/AyACaEz2ln9IHbPCqEx/4JrMVjbudTWewn8q3fPUFrgWs/kwGG5gMpo/xsZ5cGopzd3G00AIgeV1fEEuaBFZpbBmfRoZlAub/vLnkCMSSORxSvx2fmKasNN4Y/oehbWf4OCW0NvlSOi8i6IxlQn6YzHdqClElhFRXm/uboJ5jLepiUERXnPrxhjCJCj6sR/8gAf3OqthCBse0i2Qv23DY1JXZsX305xTXdXwmNgJhj2Ke6aLoynEWWdgAdTJOizI/3+C5mMfngjauQIIaAPeBMLyur3oSy7TZq/5E25vlCY6Y9CNW6sg0RPyjwTxPP6IVoNvcq/THfjsfgL1oEd3KAMhCZ1FN0Isz1H4PHSP6aYQze5wd88DM9xKyXAElyexkaFrjiDNi3utes5oYbuH/wLtU/thVpPIdwAACjBpQ0NQSUNDIHByb2ZpbGUAAHicnZZ3VFTXFofPvXd6oc0wFClD770NIL03qdJEYZgZYCgDDjM0sSGiAhFFRAQVQYIiBoyGIrEiioWAYMEekCCgxGAUUVF5M7JWdOXlvZeX3x9nfWufvfc9Z+991roAkLz9ubx0WAqANJ6AH+LlSo+MiqZj+wEM8AADzABgsjIzAkI9w4BIPh5u9EyRE/giCIA3d8QrADeNvIPodPD/SZqVwReI0gSJ2ILNyWSJuFDEqdmCDLF9RsTU+BQxwygx80UHFLG8mBMX2fCzzyI7i5mdxmOLWHzmDHYaW8w9It6aJeSIGPEXcVEWl5Mt4lsi1kwVpnFF/FYcm8ZhZgKAIontAg4rScSmIibxw0LcRLwUABwp8SuO/4oFnByB+FJu6Rm5fG5ikoCuy9Kjm9naMujenOxUjkBgFMRkpTD5bLpbeloGk5cLwOKdP0tGXFu6qMjWZrbW1kbmxmZfFeq/bv5NiXu7SK+CP/cMovV9sf2VX3o9AIxZUW12fLHF7wWgYzMA8ve/2DQPAiAp6lv7wFf3oYnnJUkgyLAzMcnOzjbmcljG4oL+of/p8Df01feMxen+KA/dnZPAFKYK6OK6sdJT04V8emYGk8WhG/15iP9x4F+fwzCEk8Dhc3iiiHDRlHF5iaJ289hcATedR+fy/lMT/2HYn7Q41yJRGj4BaqwxkBqgAuTXPoCiEAESc0C0A/3RN398OBC/vAjVicW5/yzo37PCZeIlk5v4Oc4tJIzOEvKzFvfEzxKgAQFIAipQACpAA+gCI2AObIA9cAYewBcEgjAQBVYBFkgCaYAPskE+2AiKQAnYAXaDalALGkATaAEnQAc4DS6Ay+A6uAFugwdgBIyD52AGvAHzEARhITJEgRQgVUgLMoDMIQbkCHlA/lAIFAXFQYkQDxJC+dAmqAQqh6qhOqgJ+h46BV2ArkKD0D1oFJqCfofewwhMgqmwMqwNm8AM2AX2g8PglXAivBrOgwvh7XAVXA8fg9vhC/B1+DY8Aj+HZxGAEBEaooYYIQzEDQlEopEEhI+sQ4qRSqQeaUG6kF7kJjKCTCPvUBgUBUVHGaHsUd6o5SgWajVqHaoUVY06gmpH9aBuokZRM6hPaDJaCW2AtkP7oCPRiehsdBG6Et2IbkNfQt9Gj6PfYDAYGkYHY4PxxkRhkjFrMKWY/ZhWzHnMIGYMM4vFYhWwBlgHbCCWiRVgi7B7scew57BD2HHsWxwRp4ozx3nionE8XAGuEncUdxY3hJvAzeOl8Fp4O3wgno3PxZfhG/Bd+AH8OH6eIE3QITgQwgjJhI2EKkIL4RLhIeEVkUhUJ9oSg4lc4gZiFfE48QpxlPiOJEPSJ7mRYkhC0nbSYdJ50j3SKzKZrE12JkeTBeTt5CbyRfJj8lsJioSxhI8EW2K9RI1Eu8SQxAtJvKSWpIvkKsk8yUrJk5IDktNSeCltKTcpptQ6qRqpU1LDUrPSFGkz6UDpNOlS6aPSV6UnZbAy2jIeMmyZQplDMhdlxigIRYPiRmFRNlEaKJco41QMVYfqQ02mllC/o/ZTZ2RlZC1lw2VzZGtkz8iO0BCaNs2Hlkoro52g3aG9l1OWc5HjyG2Ta5EbkpuTXyLvLM+RL5Zvlb8t/16BruChkKKwU6FD4ZEiSlFfMVgxW/GA4iXF6SXUJfZLWEuKl5xYcl8JVtJXClFao3RIqU9pVllF2Us5Q3mv8kXlaRWairNKskqFylmVKVWKqqMqV7VC9ZzqM7os3YWeSq+i99Bn1JTUvNWEanVq/Wrz6jrqy9UL1FvVH2kQNBgaCRoVGt0aM5qqmgGa+ZrNmve18FoMrSStPVq9WnPaOtoR2lu0O7QndeR1fHTydJp1HuqSdZ10V+vW697Sw+gx9FL09uvd0If1rfST9Gv0BwxgA2sDrsF+g0FDtKGtIc+w3nDYiGTkYpRl1Gw0akwz9jcuMO4wfmGiaRJtstOk1+STqZVpqmmD6QMzGTNfswKzLrPfzfXNWeY15rcsyBaeFustOi1eWhpYciwPWN61olgFWG2x6rb6aG1jzbdusZ6y0bSJs9lnM8ygMoIYpYwrtmhbV9v1tqdt39lZ2wnsTtj9Zm9kn2J/1H5yqc5SztKGpWMO6g5MhzqHEUe6Y5zjQccRJzUnplO90xNnDWe2c6PzhIueS7LLMZcXrqaufNc21zk3O7e1bufdEXcv92L3fg8Zj+Ue1R6PPdU9Ez2bPWe8rLzWeJ33Rnv7ee/0HvZR9mH5NPnM+Nr4rvXt8SP5hfpV+z3x1/fn+3cFwAG+AbsCHi7TWsZb1hEIAn0CdwU+CtIJWh30YzAmOCi4JvhpiFlIfkhvKCU0NvRo6Jsw17CysAfLdZcLl3eHS4bHhDeFz0W4R5RHjESaRK6NvB6lGMWN6ozGRodHN0bPrvBYsXvFeIxVTFHMnZU6K3NWXl2luCp11ZlYyVhm7Mk4dFxE3NG4D8xAZj1zNt4nfl/8DMuNtYf1nO3MrmBPcRw45ZyJBIeE8oTJRIfEXYlTSU5JlUnTXDduNfdlsndybfJcSmDK4ZSF1IjU1jRcWlzaKZ4ML4XXk66SnpM+mGGQUZQxstpu9e7VM3w/fmMmlLkys1NAFf1M9Ql1hZuFo1mOWTVZb7PDs0/mSOfwcvpy9XO35U7keeZ9uwa1hrWmO18tf2P+6FqXtXXroHXx67rXa6wvXD++wWvDkY2EjSkbfyowLSgveL0pYlNXoXLhhsKxzV6bm4skivhFw1vst9RuRW3lbu3fZrFt77ZPxeziayWmJZUlH0pZpde+Mfum6puF7Qnb+8usyw7swOzg7biz02nnkXLp8rzysV0Bu9or6BXFFa93x+6+WmlZWbuHsEe4Z6TKv6pzr+beHXs/VCdV365xrWndp7Rv2765/ez9QwecD7TUKteW1L4/yD14t86rrr1eu77yEOZQ1qGnDeENvd8yvm1qVGwsafx4mHd45EjIkZ4mm6amo0pHy5rhZmHz1LGYYze+c/+us8Wopa6V1lpyHBwXHn/2fdz3d074neg+yTjZ8oPWD/vaKG3F7VB7bvtMR1LHSGdU5+Ap31PdXfZdbT8a/3j4tNrpmjOyZ8rOEs4Wnl04l3du9nzG+ekLiRfGumO7H1yMvHirJ7in/5LfpSuXPS9f7HXpPXfF4crpq3ZXT11jXOu4bn29vc+qr+0nq5/a+q372wdsBjpv2N7oGlw6eHbIaejCTfebl2/53Lp+e9ntwTvL79wdjhkeucu+O3kv9d7L+1n35x9seIh+WPxI6lHlY6XH9T/r/dw6Yj1yZtR9tO9J6JMHY6yx579k/vJhvPAp+WnlhOpE06T55Okpz6kbz1Y8G3+e8Xx+uuhX6V/3vdB98cNvzr/1zUTOjL/kv1z4vfSVwqvDry1fd88GzT5+k/Zmfq74rcLbI+8Y73rfR7yfmM/+gP1Q9VHvY9cnv08PF9IWFv4FA5jz/AdcXJwAAA8DaVRYdFhNTDpjb20uYWRvYmUueG1wAAAAAAA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/Pgo8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJYTVAgQ29yZSA0LjQuMC1FeGl2MiI+CiA8cmRmOlJERiB4bWxuczpyZGY9Imh0dHA6Ly93d3cudzMub3JnLzE5OTkvMDIvMjItcmRmLXN5bnRheC1ucyMiPgogIDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiCiAgICB4bWxuczp4bXBNTT0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL21tLyIKICAgIHhtbG5zOnN0RXZ0PSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VFdmVudCMiCiAgICB4bWxuczpkYz0iaHR0cDovL3B1cmwub3JnL2RjL2VsZW1lbnRzLzEuMS8iCiAgICB4bWxuczpHSU1QPSJodHRwOi8vd3d3LmdpbXAub3JnL3htcC8iCiAgICB4bWxuczpwaG90b3Nob3A9Imh0dHA6Ly9ucy5hZG9iZS5jb20vcGhvdG9zaG9wLzEuMC8iCiAgICB4bWxuczp0aWZmPSJodHRwOi8vbnMuYWRvYmUuY29tL3RpZmYvMS4wLyIKICAgIHhtbG5zOnhtcD0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLyIKICAgeG1wTU06RG9jdW1lbnRJRD0ieG1wLmRpZDpCNzI2QjFFMTNEN0VFNDExOTA1NkFCRERBNUMxNUQ3RiIKICAgeG1wTU06SW5zdGFuY2VJRD0ieG1wLmlpZDowY2RmNzRmZC1kZmY5LTQ3MDYtYjg3Mi02ZGI3NzE4ZTNlNmEiCiAgIHhtcE1NOk9yaWdpbmFsRG9jdW1lbnRJRD0ieG1wLmRpZDpCQTI2QjFFMTNEN0VFNDExOTA1NkFCRERBNUMxNUQ3RiIKICAgZGM6Zm9ybWF0PSJhcHBsaWNhdGlvbi92bmQuYWRvYmUucGhvdG9zaG9wIgogICBHSU1QOkFQST0iMi4wIgogICBHSU1QOlBsYXRmb3JtPSJNYWMgT1MiCiAgIEdJTVA6VGltZVN0YW1wPSIxNjUzMjE3NTMxMjk0Mjc2IgogICBHSU1QOlZlcnNpb249IjIuMTAuMjQiCiAgIHBob3Rvc2hvcDpDb2xvck1vZGU9IjMiCiAgIHBob3Rvc2hvcDpJQ0NQcm9maWxlPSJzUkdCIElFQzYxOTY2LTIuMSIKICAgdGlmZjpPcmllbnRhdGlvbj0iMSIKICAgeG1wOkNyZWF0ZURhdGU9IjIwMTQtMTItMDdUMjE6NDQ6MTgrMDM6MDAiCiAgIHhtcDpDcmVhdG9yVG9vbD0iR0lNUCAyLjEwIgogICB4bXA6TWV0YWRhdGFEYXRlPSIyMDE0LTEyLTA3VDIxOjQ0OjE4KzAzOjAwIgogICB4bXA6TW9kaWZ5RGF0ZT0iMjAxNC0xMi0wN1QyMTo0NDoxOCswMzowMCI+CiAgIDx4bXBNTTpIaXN0b3J5PgogICAgPHJkZjpTZXE+CiAgICAgPHJkZjpsaQogICAgICBzdEV2dDphY3Rpb249ImNyZWF0ZWQiCiAgICAgIHN0RXZ0Omluc3RhbmNlSUQ9InhtcC5paWQ6QkEyNkIxRTEzRDdFRTQxMTkwNTZBQkREQTVDMTVEN0YiCiAgICAgIHN0RXZ0OnNvZnR3YXJlQWdlbnQ9IkFkb2JlIFBob3Rvc2hvcCBDUzYgKFdpbmRvd3MpIgogICAgICBzdEV2dDp3aGVuPSIyMDE0LTEyLTA3VDIxOjQ0OjE4KzAzOjAwIi8+CiAgICAgPHJkZjpsaQogICAgICBzdEV2dDphY3Rpb249InNhdmVkIgogICAgICBzdEV2dDpjaGFuZ2VkPSIvIgogICAgICBzdEV2dDppbnN0YW5jZUlEPSJ4bXAuaWlkOjk4NWIyY2JlLWYxOGItNGFhYy05NTI1LWQ1YzZlM2ZlNmMzNCIKICAgICAgc3RFdnQ6c29mdHdhcmVBZ2VudD0iR2ltcCAyLjEwIChNYWMgT1MpIgogICAgICBzdEV2dDp3aGVuPSIyMDIyLTA1LTIyVDE0OjA1OjMxKzAzOjAwIi8+CiAgICA8L3JkZjpTZXE+CiAgIDwveG1wTU06SGlzdG9yeT4KICA8L3JkZjpEZXNjcmlwdGlvbj4KIDwvcmRmOlJERj4KPC94OnhtcG1ldGE+CiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAKPD94cGFja2V0IGVuZD0idyI/PmpFDAYAAAAGYktHRAD/AP8A/6C9p5MAAAAJcEhZcwAACxMAAAsTAQCanBgAAAAHdElNRQfmBRYLBR9NccNdAAAPIUlEQVR42u2debhWRR3HP/dy2VQQHXczG3O3TE2tBNOw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"""


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
    # Handles OCR artifacts: "INVOICE:", "INVOICE :", "INVOICE;", digit-only lines after label
    m = re.search(r"INVOICE\s*[:\s;.]\s*[:\s]*(\d{4,})", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Fallback: a standalone number ≥5 digits on the same/next line as INVOICE
    m = re.search(r"INVOICE[^\n]*\n?\s*[:\s]*(\d{5,})", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


def _find_account(text):
    m = re.search(r"ACCOUNT\s*[:\s;.]\s*[:\s]*([\d]+[-–—][\d]+)", text, re.IGNORECASE)
    if m:
        raw = re.sub(r"[–—]", "-", m.group(1).strip())
        parts = raw.split("-", 1)
        return parts[1] if len(parts) == 2 else raw
    # Fallback: next line after ACCOUNT keyword
    m = re.search(r"ACCOUNT[^\n]*\n\s*([\d]+[-–—][\d]+)", text, re.IGNORECASE)
    if m:
        raw = re.sub(r"[–—]", "-", m.group(1).strip())
        parts = raw.split("-", 1)
        return parts[1] if len(parts) == 2 else raw
    return ""


def _find_year(text):
    # DATE label followed by dd-mm-yyyy or dd/mm/yyyy
    m = re.search(r"DATE\s*[:\s;=.]+\s*\d{1,2}[-/]\d{1,2}[-/](\d{4})",
                  text, re.IGNORECASE)
    if m:
        return m.group(1)
    # Any date pattern in text
    m = re.search(r"\b\d{1,2}[-/]\d{1,2}[-/](\d{4})\b", text)
    if m:
        return m.group(1)
    return ""


def ocr_extract_fields(path):
    img = Image.open(path)
    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGB")

    voucher = client = year = ""

    # ── Pass 1: tight crop (fast, works on standard layout) ──────────────────
    text1 = _ocr(img, 0.12, 0.30)
    voucher = _find_invoice(text1)
    client  = _find_account(text1)
    year    = _find_year(_ocr(img, 0.15, 0.26))

    # ── Pass 2: wider crop if anything is still missing ───────────────────────
    if not voucher or not client or not year:
        text_wide = _ocr(img, 0.10, 0.40, right_pct=0.65)
        if not voucher:
            voucher = _find_invoice(text_wide)
        if not client:
            client = _find_account(text_wide)
        if not year:
            year = _find_year(text_wide)

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
        self._build_footer()     # row 4

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

    # ── Footer ────────────────────────────────────────────────────────────────
    def _build_footer(self):
        footer = ttk.Frame(self, style="Status.TFrame")
        footer.grid(row=4, column=0, sticky="ew")
        ttk.Separator(footer, orient="horizontal").pack(fill="x", side="top")

        inner = ttk.Frame(footer, style="Status.TFrame", padding=(10, 5))
        inner.pack(fill="x")

        try:
            raw = base64.b64decode(_LAZURD_LOGO_B64)
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
            h = 28
            w = int(img.width * h / img.height)
            img = img.resize((w, h), Image.LANCZOS)
            from PIL import ImageTk
            self._lazurd_logo_img = ImageTk.PhotoImage(img)
            tk.Label(inner, image=self._lazurd_logo_img,
                     bg="#ECEFF4").pack(side="right", padx=(6, 0))
        except Exception:
            pass

        ttk.Label(inner,
                  text="Built by Lazurd IT  •  lazurdit.com",
                  style="Status.TLabel",
                  font=("Helvetica", 9)).pack(side="right")


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

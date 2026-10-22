"""Centralized ttk theme (colors + styles) for the whole application."""
import tkinter as tk
from tkinter import ttk

PRIMARY = "#0056b3"
PRIMARY_HOVER = "#004085"
SUCCESS = "#28a745"
SUCCESS_HOVER = "#218838"
BACKGROUND = "#f8f9fa"
SURFACE = "#ffffff"
TEXT_MAIN = "#212529"
TEXT_MUTED = "#6c757d"

FONT_MAIN = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_MUTED = ("Segoe UI", 9, "italic")
FONT_CONSOLE = ("Consolas", 9)


def apply_theme(root: tk.Tk):
    """Apply the application-wide clam-based theme. Returns the ttk.Style."""
    style = ttk.Style(root)
    style.theme_use("clam")

    root.configure(bg=BACKGROUND)

    style.configure(".", background=BACKGROUND, foreground=TEXT_MAIN, font=FONT_MAIN)

    # Notebook / Tabs
    style.configure("TNotebook", background=BACKGROUND, borderwidth=0)
    style.configure("TNotebook.Tab", background="#e9ecef", foreground=TEXT_MAIN,
                    padding=[16, 8], font=FONT_BOLD)
    style.map("TNotebook.Tab",
              background=[("selected", SURFACE), ("active", "#dee2e6")],
              foreground=[("selected", PRIMARY)])

    # LabelFrame
    style.configure("TLabelframe", background=SURFACE, relief="solid",
                    borderwidth=1, bordercolor="#dee2e6", padding=12)
    style.configure("TLabelframe.Label", background=SURFACE,
                    foreground=PRIMARY, font=FONT_BOLD)

    # Buttons
    style.configure("TButton", font=FONT_BOLD, padding=[12, 6],
                    background=PRIMARY, foreground="white")
    style.map("TButton",
              background=[("disabled", "#e9ecef"), ("active", PRIMARY_HOVER)],
              foreground=[("disabled", "#adb5bd")])

    style.configure("Success.TButton", background=SUCCESS, foreground="white")
    style.map("Success.TButton", background=[("active", SUCCESS_HOVER)])

    # Entries & Comboboxes
    style.configure("TEntry", padding=6)
    style.configure("TCombobox", padding=6)

    # Labels
    style.configure("TLabel", background=SURFACE, foreground=TEXT_MAIN)
    style.configure("Muted.TLabel", background=SURFACE,
                    foreground=TEXT_MUTED, font=FONT_MUTED)

    return style

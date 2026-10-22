"""Reusable UI widgets."""
import tkinter as tk
from tkinter import scrolledtext

from ui.theme import FONT_CONSOLE


class ConsoleWidget(scrolledtext.ScrolledText):
    """Dark terminal-style read-only console with a simple append API."""

    def __init__(self, parent, **kwargs):
        super().__init__(
            parent,
            state="disabled",
            wrap=tk.WORD,
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white",
            font=FONT_CONSOLE,
            relief="flat",
            borderwidth=0,
            **kwargs
        )

    def append(self, text: str):
        self.config(state="normal")
        self.insert(tk.END, text + "\n")
        self.see(tk.END)
        self.config(state="disabled")

    def clear(self):
        self.config(state="normal")
        self.delete('1.0', tk.END)
        self.config(state="disabled")

"""Marshals calls from worker threads onto the Tk main loop safely."""
import threading
from tkinter import messagebox


class UIThreadBridge:
    """Thread-safe bridge between background workers and the Tk UI."""

    def __init__(self, root):
        self._root = root

    def run_on_ui(self, fn, *args, **kwargs):
        """Schedule fn(*args, **kwargs) on the UI thread; non-blocking."""
        self._root.after(0, lambda: fn(*args, **kwargs))

    def log(self, console, text: str):
        """Append a log line to a console widget from any thread."""
        self.run_on_ui(console.append, text)

    def ask_yes_no(self, title: str, message: str, **msgbox_kwargs) -> bool:
        """Show a yes/no dialog on the UI thread, blocking the caller thread."""
        if threading.current_thread() is threading.main_thread():
            return bool(messagebox.askyesno(title, message, **msgbox_kwargs))

        done = threading.Event()
        answer = [False]

        def _ask():
            answer[0] = bool(messagebox.askyesno(title, message, **msgbox_kwargs))
            done.set()

        self._root.after(0, _ask)
        done.wait(timeout=600)
        return answer[0]

    def show_info(self, title, message):
        self.run_on_ui(messagebox.showinfo, title, message)

    def show_warning(self, title, message):
        self.run_on_ui(messagebox.showwarning, title, message)

    def show_error(self, title, message):
        self.run_on_ui(messagebox.showerror, title, message)

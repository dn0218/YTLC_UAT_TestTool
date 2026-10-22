"""Preprod Telecom Operations Toolkit - application entry point.

Run from source:
    python main.py

Build a standalone .exe (see build.bat / README.md):
    pyinstaller --noconfirm build.spec
"""
import sys
import traceback

from ui.main_window import MainWindow


def main():
    try:
        app = MainWindow()
        if app.ctx is not None:
            app.mainloop()
    except Exception:
        traceback.print_exc()
        # Keep the console window open long enough to read the error when
        # running from a console. In a windowed (noconsole) exe there is no
        # stdin, so guard the input() call.
        try:
            input("\nPress Enter to exit...")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()

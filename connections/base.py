"""Base class for all remote connections."""
from abc import ABC


class BaseConnection(ABC):
    """Common contract for connection wrappers.

    Subclasses manage a lazy, reusable connection and expose a close() method.
    """

    def __init__(self):
        self._conn = None

    @property
    def is_connected(self) -> bool:
        return self._conn is not None

    def close(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

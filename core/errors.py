"""Custom exceptions shared across all layers."""


class AppConfigError(Exception):
    """Raised when config_ocs.json is missing or invalid."""


class ConnectionError_(Exception):
    """Base class for connection failures (DB / SSH / API)."""


class DatabaseConnectionError(ConnectionError_):
    """Raised when the Oracle DB connection cannot be established."""


class DatabaseQueryError(ConnectionError_):
    """Raised when a SQL query fails."""


class SSHConnectionError(ConnectionError_):
    """Raised when the SSH session cannot be established."""


class ApiConnectionError(ConnectionError_):
    """Raised when the REST API trigger call fails."""


class BusinessRuleError(Exception):
    """Raised when input data violates a business rule (e.g. inactive account)."""

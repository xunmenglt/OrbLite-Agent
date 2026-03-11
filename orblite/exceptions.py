class ToolError(Exception):
    """Raised when a tool encounters an error."""

    def __init__(self, message):
        self.message = message


class OrbLiteError(Exception):
    """Base exception for all OrbLite errors"""


class TokenLimitExceeded(OrbLiteError):
    """Exception raised when the token limit is exceeded"""
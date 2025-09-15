
"""Custom exceptions for the pyS7 package."""


from typing import Optional


class S7Error(Exception):
    """Base class for all pyS7 specific exceptions."""

    def __init__(self, message: Optional[str] = None) -> None:  # noqa: D401
        """Initialize the exception with an optional *message*."""
        super().__init__(message)


class S7ConnectionError(S7Error):
    """Raised when a connection to a S7 PLC could not be established."""
    pass


class S7CommunicationError(S7Error):
    """Raised when an error occurs during communication with a S7 PLC (reading or writing)."""
    pass


class S7AddressError(S7Error):
    """Raised when a string address cannot be parsed in a S7Tag."""
    pass


class S7ReadResponseError(S7Error):
    """Raised when it is impossible to correctly parse a 'read' response from the peer."""
    pass


class S7WriteResponseError(S7Error):
    """Raised when it is impossible to correctly parse a 'write' response from the peer."""
    pass

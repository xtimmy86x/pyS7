class AddressError(Exception):
    "Raised when a string address cannot be parsed in an Item."
    ...


class ReadResponseError(Exception):
    """Raised when it is impossible to correctly parse a 'read' response from the peer."""
    ...


class WriteResponseError(Exception):
    """Raised when it is impossible to correctly parse a 'write' response from the peer."""
    ...


class ConnectionClosed(Exception):
    """Raised when the connection is closed by the peer."""
    ...

class S7ConnectionError(Exception):
    """Raised when a connection to a S7 PLC could not be established."""

    ...


class S7CommunicationError(Exception):
    """Raised when an error occurs during communication with a S7 PLC (reading or writing)."""

    ...


class S7AddressError(Exception):
    """Raised when a string address cannot be parsed in a S7Tag."""

    ...


class S7ReadResponseError(Exception):
    """Raised when it is impossible to correctly parse a 'read' response from the peer."""

    ...


class S7WriteResponseError(Exception):
    """Raised when it is impossible to correctly parse a 'write' response from the peer."""

    ...

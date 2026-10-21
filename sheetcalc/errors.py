"""Exceptions raised for problems with the sheet itself (not for errors inside cells)."""


class SheetError(ValueError):
    """Base class for bad addresses, bad CSV and unparseable formulas."""


class AddressError(SheetError):
    """The text is not a cell address inside the A1..Z99 grid."""


class ParseError(SheetError):
    """A formula breaks the grammar. Remembers where, so messages can point at it.

    Positions count characters of the expression after the leading "=".
    """

    def __init__(self, message: str, position: int) -> None:
        super().__init__(f"{message} (at position {position})")
        self.message = message
        self.position = position

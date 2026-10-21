"""Cell addresses: columns A..Z, rows 1..99."""

from .errors import AddressError

MAX_COLUMN = 26
MAX_ROW = 99


def parse_address(text: str) -> tuple[int, int] | None:
    """Return (column, row), both 1-based, or None if text is not a cell of the grid.

    Case-insensitive. Leading zeros ("A01") are rejected so every cell has exactly
    one spelling, which keeps dictionary keys and cache entries consistent.
    """
    text = text.upper()
    if not text.isascii() or len(text) < 2 or not "A" <= text[0] <= "Z":
        return None
    digits = text[1:]
    if not digits.isdigit() or digits[0] == "0":
        return None
    row = int(digits)
    if row > MAX_ROW:
        return None
    return ord(text[0]) - ord("A") + 1, row


def column_letter(column: int) -> str:
    """1 -> "A", 26 -> "Z"."""
    return chr(ord("A") + column - 1)


def format_address(column: int, row: int) -> str:
    """Inverse of parse_address: (1, 1) -> "A1"."""
    return f"{column_letter(column)}{row}"


def require_address(text: str) -> str:
    """Canonical (upper-case) form of a valid address, or AddressError."""
    if not isinstance(text, str):
        raise AddressError(f"cell address must be a string, not {type(text).__name__}")
    position = parse_address(text)
    if position is None:
        raise AddressError(f"{text!r} is not a cell address inside A1..Z99")
    return format_address(*position)


def row_major_key(address: str) -> tuple[int, int]:
    """Sort key giving reading order: A1, B1, ... Z1, A2, ..."""
    position = parse_address(address)
    if position is None:
        raise AddressError(f"{address!r} is not a cell address inside A1..Z99")
    column, row = position
    return row, column


def expand_range(start: str, end: str) -> list[str] | None:
    """All addresses of the rectangle between two corners, in reading order.

    The corners may be given in any order (B2:A1 is A1:B2). Returns None when
    either corner is outside the grid, so the caller can report #REF.
    """
    first, second = parse_address(start), parse_address(end)
    if first is None or second is None:
        return None
    (column_a, row_a), (column_b, row_b) = first, second
    return [
        format_address(column, row)
        for row in range(min(row_a, row_b), max(row_a, row_b) + 1)
        for column in range(min(column_a, column_b), max(column_a, column_b) + 1)
    ]

"""Cell values and the text they are shown as."""

from dataclasses import dataclass, field

DIV0 = "#DIV/0"
REF = "#REF"
NAME = "#NAME"
CYCLE = "#CYCLE"
VALUE = "#VALUE"
NUM = "#NUM"
SYNTAX = "#SYNTAX"


@dataclass(frozen=True)
class CellError:
    """An error shown in a cell instead of a result.

    Two errors are equal when their codes are equal; the message is only an
    explanation for humans, so it is left out of the comparison.
    """

    code: str
    message: str = field(default="", compare=False)

    def __str__(self) -> str:
        return self.code


# A blank cell is None. Numbers are always floats, so bool is never confused with a number.
type Value = float | str | bool | CellError | None


def format_value(value: Value) -> str:
    """Text for a value: whole numbers without ".0", others with 10 significant digits.

    Ten digits hide binary float noise, so 0.1 + 0.2 is shown as 0.3.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        if value == int(value) and abs(value) < 1e15:
            return str(int(value))
        return format(value, ".10g")
    return str(value)

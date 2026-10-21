"""Tokenizer: splits formula text into numbers, strings, references, names and symbols."""

import enum
from dataclasses import dataclass

from .errors import ParseError


class Kind(enum.Enum):
    NUMBER = "number"
    STRING = "string"
    CELL = "cell"          # letters followed by digits, e.g. B12 (may still be outside the grid)
    NAME = "name"          # function or unknown name, e.g. SUM
    OPERATOR = "operator"  # + - * / ^ and the comparisons
    LPAREN = "("
    RPAREN = ")"
    COMMA = ","
    COLON = ":"
    END = "end"


@dataclass(frozen=True)
class Token:
    kind: Kind
    text: str  # the lexeme; for STRING the decoded content, for CELL/NAME upper-cased
    position: int


_SYMBOLS = {
    "+": Kind.OPERATOR,
    "-": Kind.OPERATOR,
    "*": Kind.OPERATOR,
    "/": Kind.OPERATOR,
    "^": Kind.OPERATOR,
    "=": Kind.OPERATOR,
    "(": Kind.LPAREN,
    ")": Kind.RPAREN,
    ",": Kind.COMMA,
    ":": Kind.COLON,
}
_TWO_CHARACTER_OPERATORS = ("<=", ">=", "<>")


def tokenize(text: str) -> list[Token]:
    """Split an expression (without the leading "=") into tokens ending with END.

    Raises ParseError for characters that cannot start any token and for
    strings that are never closed.
    """
    tokens: list[Token] = []
    i = 0
    while i < len(text):
        char = text[i]
        start = i
        if char.isspace():
            i += 1
        elif _is_digit(char) or (char == "." and i + 1 < len(text) and _is_digit(text[i + 1])):
            i = _scan_number(text, i)
            tokens.append(Token(Kind.NUMBER, text[start:i], start))
        elif char == '"':
            content, i = _scan_string(text, i)
            tokens.append(Token(Kind.STRING, content, start))
        elif _is_letter(char) or char == "_":
            i = _scan_word(text, i)
            word = text[start:i].upper()
            tokens.append(Token(Kind.CELL if _is_cell_word(word) else Kind.NAME, word, start))
        elif char in "<>":
            operator = text[i : i + 2] if text[i : i + 2] in _TWO_CHARACTER_OPERATORS else char
            i += len(operator)
            tokens.append(Token(Kind.OPERATOR, operator, start))
        elif char in _SYMBOLS:
            i += 1
            tokens.append(Token(_SYMBOLS[char], char, start))
        else:
            raise ParseError(f"unexpected character {char!r}", i)
    tokens.append(Token(Kind.END, "", len(text)))
    return tokens


def _is_digit(char: str) -> bool:
    return "0" <= char <= "9"


def _is_letter(char: str) -> bool:
    return "a" <= char <= "z" or "A" <= char <= "Z"


def _skip_digits(text: str, i: int) -> int:
    while i < len(text) and _is_digit(text[i]):
        i += 1
    return i


def _scan_number(text: str, start: int) -> int:
    """End index of the number starting at `start`: digits, optional fraction, optional exponent.

    An "e" only belongs to the number when digits follow it, so "2e" is the
    number 2 followed by the name E (which the parser then rejects).
    """
    i = _skip_digits(text, start)
    if i < len(text) and text[i] == ".":
        i = _skip_digits(text, i + 1)
    if i < len(text) and text[i] in "eE":
        j = i + 1
        if j < len(text) and text[j] in "+-":
            j += 1
        k = _skip_digits(text, j)
        if k > j:
            i = k
    return i


def _scan_string(text: str, start: int) -> tuple[str, int]:
    """Read a "double quoted" string; two quotes in a row stand for one quote character."""
    chars: list[str] = []
    i = start + 1
    while i < len(text):
        if text[i] == '"':
            if text[i + 1 : i + 2] == '"':
                chars.append('"')
                i += 2
                continue
            return "".join(chars), i + 1
        chars.append(text[i])
        i += 1
    raise ParseError("string is missing its closing quote", start)


def _scan_word(text: str, start: int) -> int:
    i = start
    while i < len(text) and (_is_letter(text[i]) or _is_digit(text[i]) or text[i] == "_"):
        i += 1
    return i


def _is_cell_word(word: str) -> bool:
    """True for letters followed by digits (A1, ZZ7); everything else is a name."""
    letters = word.rstrip("0123456789")
    return bool(letters) and letters != word and letters.isalpha()

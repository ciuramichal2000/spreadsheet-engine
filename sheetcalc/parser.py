"""Recursive-descent parser: formula text -> small immutable syntax tree.

Grammar, from loosest to tightest binding:

    comparison := additive [ ("=" | "<>" | "<" | "<=" | ">" | ">=") additive ]
    additive   := term { ("+" | "-") term }
    term       := unary { ("*" | "/") unary }
    unary      := ("-" | "+") unary | power
    power      := primary [ "^" unary ]
    primary    := NUMBER | STRING | CELL [ ":" CELL ] | NAME "(" [ comparison { "," comparison } ] ")"
                | NAME | "(" comparison ")"

Because `power` sits below `unary` and its exponent is a `unary`, "^" is
right-associative (2^3^2 = 512), "2^-1" works, and "-2^2" is -(2^2) = -4.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass

from .address import expand_range, parse_address
from .errors import ParseError
from .tokenizer import Kind, Token, tokenize

# Deeper nesting is rejected with a ParseError instead of exhausting Python's call stack.
MAX_NESTING = 64
COMPARISON_OPERATORS = ("=", "<>", "<", "<=", ">", ">=")


@dataclass(frozen=True)
class Number:
    value: float


@dataclass(frozen=True)
class Text:
    value: str


@dataclass(frozen=True)
class Ref:
    address: str  # upper-case, but not necessarily inside the grid: the evaluator reports #REF


@dataclass(frozen=True)
class RangeRef:
    start: str
    end: str


@dataclass(frozen=True)
class Name:
    """A bare identifier such as TOTAL. It never has a value, so it evaluates to #NAME."""

    identifier: str


@dataclass(frozen=True)
class Unary:
    op: str
    operand: "Node"


@dataclass(frozen=True)
class Binary:
    """Used for "^" and the comparisons, which do not chain to the left."""

    op: str
    left: "Node"
    right: "Node"


@dataclass(frozen=True)
class Chain:
    """first op1 operand1 op2 operand2 ... for the left-associative + - * /.

    Kept flat instead of as a left-leaning tree so that a formula with thousands
    of terms is evaluated by a loop, not by thousands of nested calls.
    """

    first: "Node"
    steps: tuple[tuple[str, "Node"], ...]


@dataclass(frozen=True)
class Call:
    name: str  # upper-case
    args: tuple["Node", ...]


type Node = Number | Text | Ref | RangeRef | Name | Unary | Binary | Chain | Call


def parse(expression: str) -> Node:
    """Parse an expression written without its leading "=". Raises ParseError."""
    return _Parser(tokenize(expression)).parse()


def references(node: Node) -> list[str]:
    """Addresses of the grid cells a formula reads, ranges expanded.

    First-seen order without duplicates; references outside the grid are left
    out (they evaluate to #REF and depend on nothing).
    """
    found: dict[str, None] = {}
    _collect_references(node, found)
    return list(found)


def _collect_references(node: Node, found: dict[str, None]) -> None:
    match node:
        case Ref(address=address):
            if parse_address(address) is not None:
                found[address] = None
        case RangeRef(start=start, end=end):
            for address in expand_range(start, end) or ():
                found[address] = None
        case Unary(operand=operand):
            _collect_references(operand, found)
        case Binary(left=left, right=right):
            _collect_references(left, found)
            _collect_references(right, found)
        case Chain(first=first, steps=steps):
            _collect_references(first, found)
            for _, operand in steps:
                _collect_references(operand, found)
        case Call(args=args):
            for argument in args:
                _collect_references(argument, found)


def _describe(token: Token) -> str:
    return "end of formula" if token.kind is Kind.END else repr(token.text)


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self._tokens = tokens
        self._index = 0
        self._depth = 0

    def parse(self) -> Node:
        node = self._comparison()
        token = self._peek()
        if token.kind is not Kind.END:
            raise ParseError(f"unexpected {_describe(token)}", token.position)
        return node

    def _peek(self) -> Token:
        return self._tokens[self._index]

    def _advance(self) -> Token:
        """Consume and return the next token; the END token is never consumed."""
        token = self._tokens[self._index]
        if token.kind is not Kind.END:
            self._index += 1
        return token

    def _descend(self) -> None:
        self._depth += 1
        if self._depth > MAX_NESTING:
            raise ParseError(f"formula is nested more than {MAX_NESTING} levels deep", self._peek().position)

    def _peek_operator(self, allowed: tuple[str, ...]) -> Token | None:
        token = self._peek()
        return token if token.kind is Kind.OPERATOR and token.text in allowed else None

    def _comparison(self) -> Node:
        self._descend()
        left = self._additive()
        token = self._peek_operator(COMPARISON_OPERATORS)
        if token is not None:
            self._advance()
            left = Binary(token.text, left, self._additive())
        self._depth -= 1
        return left

    def _additive(self) -> Node:
        return self._chain(("+", "-"), self._term)

    def _term(self) -> Node:
        return self._chain(("*", "/"), self._unary)

    def _chain(self, operators: tuple[str, ...], operand: Callable[[], Node]) -> Node:
        first = operand()
        steps: list[tuple[str, Node]] = []
        while (token := self._peek_operator(operators)) is not None:
            self._advance()
            steps.append((token.text, operand()))
        return Chain(first, tuple(steps)) if steps else first

    def _unary(self) -> Node:
        token = self._peek_operator(("-", "+"))
        if token is None:
            return self._power()
        self._advance()
        self._descend()
        operand = self._unary()
        self._depth -= 1
        return Unary(token.text, operand)

    def _power(self) -> Node:
        base = self._primary()
        if self._peek_operator(("^",)) is None:
            return base
        self._advance()
        self._descend()
        exponent = self._unary()
        self._depth -= 1
        return Binary("^", base, exponent)

    def _primary(self) -> Node:
        token = self._advance()
        match token.kind:
            case Kind.NUMBER:
                value = float(token.text)
                if math.isinf(value):
                    raise ParseError("number is too large", token.position)
                return Number(value)
            case Kind.STRING:
                return Text(token.text)
            case Kind.CELL | Kind.NAME:
                if self._peek().kind is Kind.LPAREN:
                    return self._call(token)
                if token.kind is Kind.NAME:
                    return Name(token.text)
                return self._reference(token)
            case Kind.LPAREN:
                inner = self._comparison()
                closing = self._advance()
                if closing.kind is not Kind.RPAREN:
                    raise ParseError(f"expected ')' but found {_describe(closing)}", closing.position)
                return inner
            case _:
                raise ParseError(f"expected a value but found {_describe(token)}", token.position)

    def _reference(self, first: Token) -> Node:
        if self._peek().kind is not Kind.COLON:
            return Ref(first.text)
        self._advance()
        last = self._advance()
        if last.kind is not Kind.CELL:
            raise ParseError(f"expected a cell after ':' but found {_describe(last)}", last.position)
        return RangeRef(first.text, last.text)

    def _call(self, name: Token) -> Node:
        self._advance()  # the "("
        if self._peek().kind is Kind.RPAREN:
            self._advance()
            return Call(name.text, ())
        args: list[Node] = []
        while True:
            args.append(self._comparison())
            token = self._advance()
            if token.kind is Kind.RPAREN:
                return Call(name.text, tuple(args))
            if token.kind is not Kind.COMMA:
                raise ParseError(f"expected ',' or ')' but found {_describe(token)}", token.position)

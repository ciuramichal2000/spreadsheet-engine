"""Evaluation of parsed formulas.

Errors are ordinary values here: every operator and function returns the first
error it is given, so #DIV/0, #REF, #NAME and #CYCLE flow to the cells that use
them instead of raising Python exceptions.
"""

import math
import operator
from collections.abc import Callable, Sequence

from .address import expand_range, parse_address
from .parser import COMPARISON_OPERATORS, Binary, Call, Chain, Name, Node, Number, RangeRef, Ref, Text, Unary
from .values import DIV0, NAME, NUM, REF, VALUE, CellError, Value

_COMPARATORS = {
    "=": operator.eq,
    "<>": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}
_ARITHMETIC = {"+": operator.add, "-": operator.sub, "*": operator.mul}


def _average(numbers: list[float]) -> Value:
    if not numbers:
        return CellError(DIV0, "AVG of no numbers")
    return _finite(sum(numbers) / len(numbers))


# Aggregates see only the numbers among their arguments.
_AGGREGATES: dict[str, Callable[[list[float]], Value]] = {
    "SUM": lambda numbers: _finite(sum(numbers, 0.0)),
    "AVG": _average,
    "MIN": lambda numbers: min(numbers) if numbers else 0.0,
    "MAX": lambda numbers: max(numbers) if numbers else 0.0,
    "COUNT": lambda numbers: float(len(numbers)),
}


class Evaluator:
    """Evaluates formula trees; `lookup` returns the value of an in-grid cell address.

    The caller guarantees that every cell a formula reads has been calculated
    before the formula is evaluated (the sheet does this in dependency order).
    """

    def __init__(self, lookup: Callable[[str], Value]) -> None:
        self._lookup = lookup

    def evaluate(self, node: Node) -> Value:
        """Value of a whole formula; a result that is a blank cell shows as 0."""
        value = self._eval(node)
        return 0.0 if value is None else value

    def _eval(self, node: Node) -> Value:
        match node:
            case Number(value=value):
                return value
            case Text(value=text):
                return text
            case Ref(address=address):
                if parse_address(address) is None:
                    return CellError(REF, f"{address} is outside the grid A1..Z99")
                return self._lookup(address)
            case RangeRef():
                return CellError(VALUE, "a range can only be used as a function argument")
            case Name(identifier=identifier):
                return CellError(NAME, f"unknown name {identifier}")
            case Unary(op=op, operand=operand):
                return self._unary(op, self._eval(operand))
            case Binary(op=op, left=left, right=right):
                return _binary(op, self._eval(left), self._eval(right))
            case Chain(first=first, steps=steps):
                result = self._eval(first)
                for op, operand in steps:
                    result = _binary(op, result, self._eval(operand))
                return result
            case Call(name=name, args=args):
                return self._call(name, args)

    @staticmethod
    def _unary(op: str, value: Value) -> Value:
        number = _to_number(value)
        if isinstance(number, CellError):
            return number
        return -number if op == "-" else number

    def _call(self, name: str, args: Sequence[Node]) -> Value:
        if name == "IF":
            return self._if(args)
        aggregate = _AGGREGATES.get(name)
        if aggregate is None:
            return CellError(NAME, f"unknown function {name}")
        if not args:
            return CellError(VALUE, f"{name} needs at least one argument")
        numbers = self._collect_numbers(args)
        if isinstance(numbers, CellError):
            return numbers
        return aggregate(numbers)

    def _if(self, args: Sequence[Node]) -> Value:
        """IF evaluates only the branch it picks, so IF(B1=0, 0, A1/B1) never even attempts A1/B1."""
        if len(args) != 3:
            return CellError(VALUE, "IF needs exactly 3 arguments: IF(condition, then, else)")
        condition = self._eval(args[0])
        if isinstance(condition, CellError):
            return condition
        if isinstance(condition, str):
            return CellError(VALUE, "IF condition is text, not a number or comparison")
        # Here the condition is a blank, a bool or a float: blank, FALSE and 0 select the else branch.
        return self._eval(args[1] if condition else args[2])

    def _collect_numbers(self, args: Sequence[Node]) -> list[float] | CellError:
        """Numbers from the arguments in reading order, or the first error met.

        Text, booleans and blank cells are skipped wherever they appear.
        """
        numbers: list[float] = []
        for arg in args:
            values = self._range_values(arg) if isinstance(arg, RangeRef) else [self._eval(arg)]
            for value in values:
                if isinstance(value, CellError):
                    return value
                if isinstance(value, float):
                    numbers.append(value)
        return numbers

    def _range_values(self, arg: RangeRef) -> list[Value]:
        addresses = expand_range(arg.start, arg.end)
        if addresses is None:
            return [CellError(REF, f"range {arg.start}:{arg.end} reaches outside the grid A1..Z99")]
        return [self._lookup(address) for address in addresses]


def _finite(number: float) -> Value:
    """Floats overflow to infinity silently; report that as #NUM instead of showing "inf"."""
    if math.isfinite(number):
        return number
    return CellError(NUM, "result is too large")


def _to_number(value: Value) -> float | CellError:
    if isinstance(value, CellError):
        return value
    if value is None:
        return 0.0
    if isinstance(value, str):
        return CellError(VALUE, f"text {value!r} is not a number")
    return float(value)  # a float, or a bool counted as 1 / 0


def _binary(op: str, left: Value, right: Value) -> Value:
    """Apply a binary operator; the left error wins over the right one."""
    if isinstance(left, CellError):
        return left
    if isinstance(right, CellError):
        return right
    if op in COMPARISON_OPERATORS:
        return _compare(op, left, right)
    a, b = _to_number(left), _to_number(right)
    if isinstance(a, CellError):
        return a
    if isinstance(b, CellError):
        return b
    if op == "/":
        if b == 0.0:
            return CellError(DIV0, "division by zero")
        return _finite(a / b)
    if op == "^":
        return _power(a, b)
    return _finite(_ARITHMETIC[op](a, b))


def _power(base: float, exponent: float) -> Value:
    if base == 0.0 and exponent < 0.0:
        return CellError(DIV0, "zero raised to a negative power")
    try:
        return _finite(math.pow(base, exponent))
    except OverflowError:
        return CellError(NUM, "result is too large")
    except ValueError:  # a negative base with a fractional exponent has no real result
        return CellError(NUM, "no real result for this power")


def _compare(op: str, left: Value, right: Value) -> Value:
    """Compare numbers numerically and text case-insensitively.

    A blank cell takes the type of the other side (0 or ""), booleans count as
    1/0, and text never equals a number; ordering text against a number is #VALUE.
    """
    if left is None:
        left = "" if isinstance(right, str) else 0.0
    if right is None:
        right = "" if isinstance(left, str) else 0.0
    if isinstance(left, str) and isinstance(right, str):
        return _COMPARATORS[op](left.casefold(), right.casefold())
    if isinstance(left, str) or isinstance(right, str):
        if op in ("=", "<>"):
            return op == "<>"
        return CellError(VALUE, "cannot order text against a number")
    return _COMPARATORS[op](float(left), float(right))

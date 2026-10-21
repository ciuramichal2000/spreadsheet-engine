"""The sheet: cell storage, dependency-ordered calculation with caching, CSV loading, printing."""

import csv
import io
import math
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Self

from .address import (
    MAX_COLUMN,
    MAX_ROW,
    column_letter,
    format_address,
    parse_address,
    require_address,
    row_major_key,
)
from .errors import ParseError, SheetError
from .evaluate import Evaluator
from .graph import strongly_connected_components
from .parser import Node, parse, references
from .values import CYCLE, NUM, SYNTAX, CellError, Value, format_value

# ASCII digits only: float() would also accept other scripts' digits and "nan"/"inf".
_NUMBER = re.compile(r"[+-]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][+-]?[0-9]+)?")


@dataclass(frozen=True)
class _Cell:
    """What was typed into a cell, analysed once when it is set.

    A formula cell has `formula` and `dependencies`. Every other cell has a
    `constant`: a number, text, or the error of a formula that failed to parse.
    """

    constant: Value = None
    formula: Node | None = None
    dependencies: tuple[str, ...] = ()


class Sheet:
    """A grid A1..Z99 of numbers, text and formulas.

    Results are cached per cell. Any change clears the cache, so a value is
    never stale, and within one calculation every formula is evaluated once.
    """

    def __init__(self) -> None:
        self._cells: dict[str, _Cell] = {}
        self._cache: dict[str, Value] = {}

    def set(self, address: str, value: str | int | float) -> None:
        """Store a cell. Text starting with "=" is a formula, numeric text is a number.

        Blank or whitespace-only text clears the cell. Raises AddressError for a
        bad address and TypeError / ValueError for values that cannot be stored.
        A formula with a syntax error is accepted and shows #SYNTAX in its cell.
        """
        address = require_address(address)
        cell = _build_cell(value)
        if cell is None:
            self._cells.pop(address, None)
        else:
            self._cells[address] = cell
        self._cache.clear()

    def value(self, address: str) -> Value:
        """Evaluated value of one cell: None when blank, otherwise float, str, bool or CellError."""
        address = require_address(address)
        self._calculate([address])
        return self._lookup(address)

    def evaluate_all(self) -> dict[str, Value]:
        """Values of every non-blank cell, in reading order (A1, B1, ..., A2, ...)."""
        self._calculate(self._cells)
        return {address: self._lookup(address) for address in sorted(self._cells, key=row_major_key)}

    def render(self) -> str:
        """The evaluated grid as text: numbers right-aligned, everything else left-aligned.

        Only the rectangle A1..(last used column, last used row) is shown.
        """
        values = self.evaluate_all()
        if not values:
            return "(empty sheet)"
        shown: dict[tuple[int, int], str] = {}
        right_aligned: set[tuple[int, int]] = set()
        for address, value in values.items():
            column, row = parse_address(address)
            # A quoted CSV cell may hold line breaks; one line per cell keeps the table aligned.
            shown[column, row] = " ".join(format_value(value).splitlines())
            if isinstance(value, float):
                right_aligned.add((column, row))
        last_column = max(column for column, _ in shown)
        last_row = max(row for _, row in shown)
        label_width = len(str(last_row))
        columns = range(1, last_column + 1)
        widths = {
            column: max(
                [1] + [len(shown.get((column, row), "")) for row in range(1, last_row + 1)]
            )
            for column in columns
        }

        def line(label: str, cells: list[str]) -> str:
            return (label.rjust(label_width) + " | " + " | ".join(cells)).rstrip()

        lines = [
            line("", [column_letter(column).ljust(widths[column]) for column in columns]),
            "-" * label_width + "-+-" + "-+-".join("-" * widths[column] for column in columns),
        ]
        for row in range(1, last_row + 1):
            cells = []
            for column in columns:
                text = shown.get((column, row), "")
                aligned = text.rjust(widths[column]) if (column, row) in right_aligned else text.ljust(widths[column])
                cells.append(aligned)
            lines.append(line(str(row), cells))
        return "\n".join(lines)

    @classmethod
    def from_csv(cls, text: str) -> Self:
        """Build a sheet from CSV text: row 1 of the file is row 1 of the grid.

        Cells starting with "=" are formulas (a formula containing commas must be
        quoted, as in any CSV). Blank cells are skipped, so trailing commas and
        empty lines are harmless; a non-blank cell outside A1..Z99 is a SheetError.
        """
        sheet = cls()
        try:
            for row_number, row in enumerate(csv.reader(io.StringIO(text, newline="")), start=1):
                for column_number, cell in enumerate(row, start=1):
                    if not cell.strip():
                        continue
                    if column_number > MAX_COLUMN or row_number > MAX_ROW:
                        raise SheetError(
                            f"CSV row {row_number}, column {column_number} is outside the grid A1..Z99"
                        )
                    sheet.set(format_address(column_number, row_number), cell)
        except csv.Error as error:
            raise SheetError(f"malformed CSV: {error}") from error
        return sheet

    @classmethod
    def load_csv(cls, path: str) -> Self:
        """Read a UTF-8 CSV file (a byte-order mark, as written by Excel, is accepted)."""
        with open(path, encoding="utf-8-sig", newline="") as handle:
            return cls.from_csv(handle.read())

    def _lookup(self, address: str) -> Value:
        cell = self._cells.get(address)
        if cell is None:
            return None
        if cell.formula is None:
            return cell.constant
        return self._cache[address]

    def _needs_calculation(self, address: str) -> bool:
        cell = self._cells.get(address)
        return cell is not None and cell.formula is not None and address not in self._cache

    def _dependencies_to_calculate(self, address: str) -> Iterator[str]:
        return (dep for dep in self._cells[address].dependencies if self._needs_calculation(dep))

    def _calculate(self, addresses: Iterable[str]) -> None:
        """Calculate the given cells and everything they depend on, dependencies first.

        Strongly connected components arrive in dependency order, so by the time
        a formula runs every cell it reads is already in the cache. A component
        that is more than one cell, or a cell reading itself, is a cycle.
        """
        roots = [address for address in addresses if self._needs_calculation(address)]
        for component in strongly_connected_components(roots, self._dependencies_to_calculate):
            first = component[0]
            if len(component) > 1 or first in self._cells[first].dependencies:
                members = ", ".join(sorted(component, key=row_major_key))
                error = CellError(CYCLE, f"circular reference through {members}")
                for address in component:
                    self._cache[address] = error
            else:
                self._cache[first] = self._evaluate_cell(self._cells[first])

    def _evaluate_cell(self, cell: _Cell) -> Value:
        return Evaluator(self._lookup).evaluate(cell.formula)


def _build_cell(value: str | int | float) -> _Cell | None:
    """Analyse what was typed into a cell; None means the cell is blank."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise TypeError(f"cell value must be str, int or float, not {type(value).__name__}")
    if not isinstance(value, str):
        try:
            number = float(value)
        except OverflowError:
            number = math.inf
        if not math.isfinite(number):
            raise ValueError("cell value must be a finite number")
        return _Cell(constant=number)
    if not value.strip():
        return None
    if value.startswith("="):
        try:
            tree = parse(value[1:])
        except ParseError as error:
            return _Cell(constant=CellError(SYNTAX, str(error)))
        return _Cell(formula=tree, dependencies=tuple(references(tree)))
    if _NUMBER.fullmatch(value.strip()):
        number = float(value)
        if not math.isfinite(number):
            return _Cell(constant=CellError(NUM, f"{value.strip()} is too large for a number"))
        return _Cell(constant=number)
    return _Cell(constant=value)

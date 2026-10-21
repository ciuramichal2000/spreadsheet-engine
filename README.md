# sheetcalc

A small spreadsheet engine in pure Python. It holds a grid of cells A1..Z99 with numbers, text and formulas
(anything starting with `=`), evaluates the formulas in dependency order, and can load a CSV file and print the
calculated grid. The formula language is parsed by a hand-written tokenizer and recursive-descent parser; `eval`
is never used.

## Interesting engineering

- **Own parser, correct precedence.** `^` is right-associative and binds tighter than unary minus, so `2^3^2` is
  512 and `-2^2` is -4. Left-associative `+ - * /` are kept as flat chains, so a formula with 20,000 terms
  neither nests deeply nor overflows the stack. Nesting beyond 64 levels is rejected with a `ParseError`.
- **Dependency order without recursion.** Cells are calculated using an iterative Tarjan strongly-connected-components
  search, so a chain of all 2,574 cells in the grid calculates fine, far past Python's recursion limit.
- **Cycles are values, not crashes.** Every cell in a loop (including a cell that reads itself) shows `#CYCLE`, and
  cells that read them inherit it. Unrelated cells are unaffected.
- **Errors are ordinary values.** `#DIV/0`, `#REF`, `#NAME`, `#VALUE`, `#NUM` and `#SYNTAX` propagate through
  operators and functions (the leftmost error wins). A broken formula never raises while calculating.
- **Caching.** Each formula is evaluated at most once per edit; any `set` clears the cache, so a value is never stale.
  `IF` evaluates only the branch it picks.

## Formula language

- Numbers (`12`, `.5`, `1e3`), strings (`"text"`, with `""` for a quote), cell references (`A1`, case-insensitive),
  ranges (`A1:B3`, corners in any order) and parentheses.
- Operators: `+ - * / ^`, unary `-` and `+`, and the comparisons `= <> < <= > >=` (text compares
  case-insensitively; a comparison gives `TRUE` or `FALSE`).
- Functions: `SUM`, `AVG`, `MIN`, `MAX`, `COUNT` (numbers only; text, booleans and blank cells are skipped) and
  `IF(condition, then, else)`.

## Usage

`examples/budget.csv` holds numbers, text and formulas:

```
Item,Price,Qty,Total,Note
Pens,1.5,10,=B2*C2,
Paper,4.25,4,=B3*C3,
Ink,12,2,=B4*C4,"=IF(D4>20,""over 20"",""ok"")"
,,Sum,=SUM(D2:D4),
,,Average,=AVG(D2:D4),
,,Priciest,=MAX(D2:D4),
,,Share of ink,=D4/D5,
```

```
$ python -m sheetcalc examples/budget.csv
  | A     | B     | C            | D            | E
--+-------+-------+--------------+--------------+--------
1 | Item  | Price | Qty          | Total        | Note
2 | Pens  |   1.5 |           10 |           15 |
3 | Paper |  4.25 |            4 |           17 |
4 | Ink   |    12 |            2 |           24 | over 20
5 |       |       | Sum          |           56 |
6 |       |       | Average      |  18.66666667 |
7 |       |       | Priciest     |           24 |
8 |       |       | Share of ink | 0.4285714286 |

$ python -m sheetcalc examples/budget.csv --cell D5
56
```

From Python:

```python
from sheetcalc import Sheet

sheet = Sheet()
sheet.set("A1", 4)
sheet.set("B1", "=A1*A1+1")
sheet.set("C1", "=B1/0")
print(sheet.value("B1"))   # 17.0
print(sheet.value("C1"))   # #DIV/0   (a CellError, not an exception)
```

A bad address raises `AddressError`, a CSV that does not fit the grid raises `SheetError`; on the command line both
are reported as `sheetcalc: ...` with exit status 2.

## Limitations

- Dependencies are found by reading the formula, before anything runs. A reference inside an `IF` branch that is never
  taken still counts, so `=IF(1,5,A1)` in A1 is reported as `#CYCLE`.
- A range can only be used as a function argument; `=A1:B2` alone is `#VALUE`.
- Only the functions listed above exist, there are no absolute references (`$A$1`), and the grid stops at column Z
  and row 99. Numbers are floats, shown with 10 significant digits.
- A CSV cell is a formula only if it starts with `=`; a formula that contains commas must be quoted, as in any CSV.
- Cells are recalculated lazily by `value()` and `render()`; there is no incremental recalculation of only the
  changed cells (an edit clears the whole cache).

## Running the tests

Requires Python 3.12 or newer and pytest.

```
python -m pytest -q
```

Built with AI coding assistance.

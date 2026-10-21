import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from sheetcalc import CellError, Sheet


def make(cells):
    sheet = Sheet()
    for address, value in cells.items():
        sheet.set(address, value)
    return sheet


def calc(formula, cells=None):
    sheet = make(cells or {})
    sheet.set("Z99", formula)
    return sheet.value("Z99")


# Column A: 1, text, blank, 4. Only the two numbers should count.
MIXED = {"A1": 1, "A2": "x", "A4": 4}


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("=SUM(A1:A4)", 5.0),
        ("=AVG(A1:A4)", 2.5),  # (1+4)/2: text and blank are not averaged in
        ("=MIN(A1:A4)", 1.0),
        ("=MAX(A1:A4)", 4.0),
        ("=COUNT(A1:A4)", 2.0),
    ],
)
def test_aggregates_use_only_the_numbers_in_a_range(formula, expected):
    assert calc(formula, MIXED) == expected


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("=SUM(1,2,3)", 6.0),
        ("=MAX(-5,-2)", -2.0),
        ("=MIN(3,A1:A2)", 2.0),
        ("=SUM(A1:A2,10,B1)", 22.0),  # 7 + 2 + 10 + 3
        ("=AVG(1,2)", 1.5),
        ("=sum(a1:a2)", 9.0),
    ],
)
def test_aggregates_accept_literals_cells_and_ranges_together(formula, expected):
    assert calc(formula, {"A1": 7, "A2": 2, "B1": 3}) == expected


def test_range_corners_can_be_written_in_any_order():
    grid = {"A1": 1, "B1": 2, "A2": 3, "B2": 4}
    assert calc("=SUM(A1:B2)", grid) == 10.0
    assert calc("=SUM(B2:A1)", grid) == 10.0
    assert calc("=SUM(B1:A2)", grid) == 10.0
    assert calc("=SUM(A1:A2)", grid) == 4.0  # a single column: 1+3


def test_aggregates_of_nothing():
    assert calc("=SUM(B1:B3)") == 0.0
    assert calc("=COUNT(B1:B3)") == 0.0
    assert calc("=MIN(B1:B3)") == 0.0
    assert calc("=MAX(B1:B3)") == 0.0
    assert calc("=AVG(B1:B3)") == CellError("#DIV/0")


def test_text_and_booleans_are_skipped_wherever_they_appear():
    assert calc('=SUM("5",1)') == 1.0
    assert calc("=SUM(2>1,4)") == 4.0
    assert calc('=COUNT("a",1,A1)') == 1.0


def test_formula_results_inside_a_range_are_used():
    assert calc("=SUM(A1:A2)", {"A1": 5, "A2": "=A1*2"}) == 15.0


def test_first_error_in_reading_order_propagates_even_through_count():
    cells = {"A1": 1, "A2": "=1/0", "A3": "=FOO"}
    assert calc("=SUM(A1:A3)", cells) == CellError("#DIV/0")
    assert calc("=COUNT(A1:A3)", cells) == CellError("#DIV/0")
    assert calc("=SUM(A3:A3,A2:A2)", cells) == CellError("#NAME")


def test_range_reaching_outside_the_grid_is_a_ref_error():
    assert calc("=SUM(A1:A100)") == CellError("#REF")
    assert calc("=SUM(1,A1:AA2)") == CellError("#REF")


def test_aggregate_without_arguments_is_a_value_error():
    assert calc("=SUM()") == CellError("#VALUE")
    assert calc("=COUNT()") == CellError("#VALUE")


def test_sum_that_overflows_is_reported_not_infinity():
    assert calc("=SUM(A1:A2)", {"A1": "1e308", "A2": "1e308"}) == CellError("#NUM")


@pytest.mark.parametrize(
    "column, expected",
    [({"A1": 1, "A2": 2, "A3": 3}, 3.0), ({"A1": 1, "A2": 1, "A3": 1}, 1.0)],
)
def test_functions_nest(column, expected):
    # sum 6 > 5 -> MAX = 3; sum 3 is not > 5 -> MIN = 1
    assert calc("=IF(SUM(A1:A3)>5,MAX(A1:A3),MIN(A1:A3))", column) == expected

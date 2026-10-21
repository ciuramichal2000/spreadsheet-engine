import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from sheetcalc.errors import ParseError
from sheetcalc.parser import (
    MAX_NESTING,
    Binary,
    Call,
    Chain,
    Name,
    Number,
    RangeRef,
    Ref,
    Text,
    Unary,
    parse,
    references,
)


def test_function_call_with_range_and_number_arguments():
    assert parse("SUM(A1:B2, 3)") == Call("SUM", (RangeRef("A1", "B2"), Number(3.0)))


def test_names_and_references_are_case_insensitive():
    assert parse("sum(a1)") == Call("SUM", (Ref("A1"),))


def test_atoms():
    assert parse("TOTAL") == Name("TOTAL")
    assert parse('"hi"') == Text("hi")
    assert parse("1.5") == Number(1.5)


def test_function_name_that_looks_like_a_cell_is_still_a_call():
    assert parse("LOG10(1)") == Call("LOG10", (Number(1.0),))


def test_multiplication_binds_tighter_than_addition():
    assert parse("1+2*3") == Chain(
        Number(1.0), (("+", Chain(Number(2.0), (("*", Number(3.0)),))),)
    )


def test_subtraction_is_left_associative():
    assert parse("1-2-3") == Chain(Number(1.0), (("-", Number(2.0)), ("-", Number(3.0))))


def test_power_is_right_associative():
    assert parse("2^3^2") == Binary("^", Number(2.0), Binary("^", Number(3.0), Number(2.0)))


def test_unary_minus_applies_after_the_power():
    assert parse("-2^2") == Unary("-", Binary("^", Number(2.0), Number(2.0)))


def test_parentheses_override_precedence():
    assert parse("(1+2)*3") == Chain(
        Chain(Number(1.0), (("+", Number(2.0)),)), (("*", Number(3.0)),)
    )


@pytest.mark.parametrize(
    "expression, position, fragment",
    [
        ("1+", 2, "end of formula"),
        ("", 0, "end of formula"),
        ("(1", 2, "')'"),
        ("1 2", 2, "'2'"),
        ("1)", 1, "')'"),
        ("SUM(1,)", 6, "')'"),
        ("SUM(1 2)", 6, "'2'"),
        ("A1:5", 3, "'5'"),
        ("1<2<3", 3, "'<'"),
        ("A1:B2:C3", 5, "':'"),
        ("2 +* 3", 3, "'*'"),
        ("A1=", 3, "end of formula"),
        ("1e999", 0, "too large"),
    ],
)
def test_malformed_formulas_report_what_and_where(expression, position, fragment):
    with pytest.raises(ParseError) as caught:
        parse(expression)
    assert caught.value.position == position
    assert fragment in caught.value.message


def test_nesting_up_to_the_limit_parses_and_one_more_level_does_not():
    allowed = MAX_NESTING - 1  # the outermost expression is level 1
    assert parse("(" * allowed + "1" + ")" * allowed) == Number(1.0)
    too_deep = MAX_NESTING
    with pytest.raises(ParseError, match="nested"):
        parse("(" * too_deep + "1" + ")" * too_deep)


def test_endless_unary_minus_is_rejected_instead_of_overflowing_the_stack():
    with pytest.raises(ParseError, match="nested"):
        parse("-" * 5000 + "1")


def test_endless_power_chain_is_rejected_instead_of_overflowing_the_stack():
    with pytest.raises(ParseError, match="nested"):
        parse("^".join(["2"] * 5000))


def test_very_long_flat_formula_parses_into_one_flat_chain():
    tree = parse("+".join(["1"] * 20000))
    assert isinstance(tree, Chain)
    assert len(tree.steps) == 19999


def test_references_lists_each_cell_once_in_first_seen_order():
    assert references(parse("A1+SUM(B1:B3)*A1")) == ["A1", "B1", "B2", "B3"]


def test_references_expand_a_reversed_range_in_reading_order():
    assert references(parse("SUM(B2:A1)")) == ["A1", "B1", "A2", "B2"]


def test_references_ignore_cells_outside_the_grid():
    assert references(parse("A100+AA1+SUM(A1:A100)+A0")) == []

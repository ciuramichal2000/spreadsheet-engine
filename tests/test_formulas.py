import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from sheetcalc import CellError, Sheet, parse
from sheetcalc.evaluate import Evaluator


def make(cells):
    sheet = Sheet()
    for address, value in cells.items():
        sheet.set(address, value)
    return sheet


def calc(formula, cells=None):
    """Value of a formula placed in Z99, next to the given cells."""
    sheet = make(cells or {})
    sheet.set("Z99", formula)
    return sheet.value("Z99")


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("=2+3*4", 14.0),
        ("=(2+3)*4", 20.0),
        ("=2*3^2", 18.0),  # ^ before *: 2*9, not 6^2
        ("=-2^2", -4.0),  # minus applies after the power
        ("=(-2)^2", 4.0),
        ("=2^3^2", 512.0),  # right-associative: 2^(3^2); left would give 64
        ("=2^-1", 0.5),
        ("=10-4-3", 3.0),  # (10-4)-3; right-associative would give 9
        ("=100/10/5", 2.0),  # (100/10)/5; right-associative would give 50
        ("=8/4/2", 1.0),
        ("=--3", 3.0),
        ("=3-(-2)", 5.0),
        ("=+4", 4.0),
        ("=-(2+3)*2", -10.0),
        ("=1.5*4", 6.0),
        ("=.5+.25", 0.75),
        ("=1e2+1", 101.0),
        ("=2 * ( 3 + 4 )", 14.0),
        ("=2^10", 1024.0),
        ("=(-2)^3", -8.0),
        ("=4^0.5", 2.0),
    ],
)
def test_arithmetic_follows_precedence_and_associativity(formula, expected):
    assert calc(formula) == expected


def test_cell_references_read_other_cells():
    assert calc("=A1*B1", {"A1": "4", "B1": "6"}) == 24.0


def test_references_are_case_insensitive():
    assert calc("=a1+b1", {"A1": 1, "B1": 2}) == 3.0


def test_dependencies_are_calculated_first_whatever_order_cells_were_entered():
    sheet = Sheet()
    sheet.set("C1", "=B1*2")
    sheet.set("B1", "=A1+1")
    sheet.set("A1", 4)
    assert sheet.value("C1") == 10.0  # (4+1)*2
    assert sheet.value("B1") == 5.0


def test_editing_a_cell_updates_every_cell_that_depends_on_it():
    sheet = make({"A1": 4, "B1": "=A1+1", "C1": "=B1*2"})
    assert sheet.value("C1") == 10.0
    sheet.set("A1", 9)
    assert sheet.value("C1") == 20.0  # (9+1)*2, not the cached 10


def test_each_formula_is_evaluated_once_per_edit_and_only_when_needed(monkeypatch):
    calls = []
    original = Sheet._evaluate_cell

    def counting(self, cell):
        calls.append(cell)
        return original(self, cell)

    monkeypatch.setattr(Sheet, "_evaluate_cell", counting)
    sheet = make({"A1": 1, "B1": "=A1+1", "C1": "=A1+2", "D1": "=B1+C1", "E1": "=1+1"})

    assert sheet.value("D1") == 5.0  # (1+1)+(1+2)
    assert len(calls) == 3  # B1, C1, D1 once each; unrelated E1 not touched
    sheet.value("D1")
    sheet.value("B1")
    assert len(calls) == 3  # served from the cache
    assert sheet.evaluate_all()["E1"] == 2.0
    assert len(calls) == 4

    sheet.set("A1", 10)
    assert sheet.value("D1") == 23.0  # (10+1)+(10+2)
    assert len(calls) == 7  # the edit invalidated B1, C1 and D1


def test_a_reference_to_a_blank_cell_counts_as_zero():
    assert calc("=A1+1") == 1.0
    assert calc("=A1") == 0.0


def test_text_cell_that_looks_like_a_number_is_a_number():
    assert calc("=A1+1", {"A1": "12"}) == 13.0


def test_string_literals_with_doubled_quotes():
    assert calc('="abc"') == "abc"
    assert calc('="a""b"') == 'a"b'


# ---- errors -------------------------------------------------------------------------------


def test_division_by_zero():
    assert calc("=1/0") == CellError("#DIV/0")


def test_dividing_by_a_blank_cell_is_division_by_zero():
    assert calc("=A1/B1", {"A1": 5}) == CellError("#DIV/0")


def test_errors_propagate_through_chains_of_dependents():
    sheet = make({"A1": "=1/0", "B1": "=A1+1", "C1": "=B1*2", "D1": "=-C1", "E1": "=7"})
    assert [sheet.value(a) for a in ("A1", "B1", "C1", "D1")] == [CellError("#DIV/0")] * 4
    assert sheet.value("E1") == 7.0  # unrelated cell is unaffected


@pytest.mark.parametrize(
    "formula",
    ["=A100", "=AA1", "=A0", "=1+A100", "=SUM(A1:A100)", "=SUM(Z99:AA100)", "=A01"],
)
def test_references_outside_the_grid_are_ref_errors(formula):
    assert calc(formula) == CellError("#REF")


@pytest.mark.parametrize("formula", ["=FOO", "=FOO(1,2)", "=total+1", "=XYZ(A1:A3)", "=FOO(1/0)"])
def test_unknown_names_and_functions_are_name_errors(formula):
    assert calc(formula) == CellError("#NAME")


def test_leftmost_error_wins():
    assert calc("=1/0+FOO") == CellError("#DIV/0")
    assert calc("=FOO+1/0") == CellError("#NAME")


@pytest.mark.parametrize(
    "formula",
    ['="abc"+1', '=-"x"', "=A1:B2", "=A1:B2+1", '=1*"2"'],
)
def test_text_in_arithmetic_and_bare_ranges_are_value_errors(formula):
    assert calc(formula) == CellError("#VALUE")


def test_text_cell_in_arithmetic_is_a_value_error():
    assert calc("=A1*2", {"A1": "hello"}) == CellError("#VALUE")


@pytest.mark.parametrize("formula", ["=1+", "=", "=)", "=(1", "=1 2", '="abc'])
def test_malformed_formula_shows_syntax_error_instead_of_raising(formula):
    assert calc(formula) == CellError("#SYNTAX")


def test_syntax_error_message_says_where():
    error = calc("=1+")
    assert "end of formula" in error.message
    assert "position 2" in error.message


@pytest.mark.parametrize(
    "formula, code",
    [
        ("=0^-1", "#DIV/0"),
        ("=(-8)^0.5", "#NUM"),  # no real result
        ("=10^400", "#NUM"),
        ("=1e308*10", "#NUM"),
        ("=1e308+1e308", "#NUM"),
        ("=1e999", "#SYNTAX"),
    ],
)
def test_arithmetic_that_leaves_the_real_numbers_is_reported_not_raised(formula, code):
    assert calc(formula) == CellError(code)


# ---- comparison and text ------------------------------------------------------------------


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("=3>2", True),
        ("=2>3", False),
        ("=2>=2", True),
        ("=2<=1", False),
        ("=2<>2", False),
        ("=2<>3", True),
        ("=1=1.0", True),
        ('="a"="A"', True),  # text compares case-insensitively
        ('="apple"<"banana"', True),
        ('="b"<"a"', False),
        ("=1+1=2", True),  # arithmetic binds tighter than comparison
        ("=2*3>5", True),
    ],
)
def test_comparisons_give_booleans(formula, expected):
    assert calc(formula) is expected


def test_booleans_count_as_one_and_zero_in_arithmetic():
    assert calc("=(3>2)+1") == 2.0
    assert calc("=(3>2)*(2>1)") == 1.0
    assert calc("=(3<2)*10") == 0.0


def test_text_never_equals_a_number_and_cannot_be_ordered_against_one():
    assert calc('="a"=1') is False
    assert calc('="a"<>1') is True
    assert calc('="a"<1') == CellError("#VALUE")
    assert calc('=1<"a"') == CellError("#VALUE")


def test_blank_cell_compares_as_zero_against_numbers_and_empty_against_text():
    assert calc("=A1=0") is True
    assert calc('=A1=""') is True
    assert calc("=A1<1") is True
    assert calc('=A1="x"') is False


# ---- IF -----------------------------------------------------------------------------------


def test_if_picks_a_branch_by_the_comparison():
    assert calc('=IF(A1>5,"big","small")', {"A1": 10}) == "big"
    assert calc('=IF(A1>5,"big","small")', {"A1": 3}) == "small"


def test_if_evaluates_only_the_chosen_branch():
    cells = {"A1": 8, "B1": 0}
    assert calc("=IF(B1=0,0,A1/B1)", cells) == 0.0  # the division is never run
    assert calc("=IF(B1=0,0,A1/B1)", {"A1": 8, "B1": 4}) == 2.0
    assert calc("=IF(0,1/0,2)") == 2.0
    assert calc("=IF(1,1/0,2)") == CellError("#DIV/0")


def test_if_reads_only_the_cells_of_the_branch_it_takes():
    # Errors are values here, so laziness shows in which cells get read, not in the result.
    def reads(condition_value):
        seen = []

        def lookup(address):
            seen.append(address)
            return condition_value if address == "A1" else 100.0

        Evaluator(lookup).evaluate(parse("IF(A1>0,B1,C1)"))
        return seen

    assert reads(5.0) == ["A1", "B1"]  # true: the else cell C1 is never read
    assert reads(-5.0) == ["A1", "C1"]  # false: the then cell B1 is never read


def test_if_treats_zero_and_blank_as_false_and_other_numbers_as_true():
    assert calc('=IF(2,"y","n")') == "y"
    assert calc('=IF(-1,"y","n")') == "y"
    assert calc('=IF(0,"y","n")') == "n"
    assert calc('=IF(A1,"y","n")') == "n"


def test_if_with_text_or_error_condition():
    assert calc('=IF("yes",1,2)') == CellError("#VALUE")
    assert calc("=IF(1/0,1,2)") == CellError("#DIV/0")


@pytest.mark.parametrize("formula", ["=IF(1,2)", "=IF(1,2,3,4)", "=IF()"])
def test_if_needs_exactly_three_arguments(formula):
    assert calc(formula) == CellError("#VALUE")


def test_nested_if():
    formula = '=IF(A1<0,"neg",IF(A1=0,"zero","pos"))'
    assert [calc(formula, {"A1": n}) for n in (-1, 0, 5)] == ["neg", "zero", "pos"]


def test_if_returning_a_blank_cell_shows_zero():
    assert calc("=IF(1,B1,2)") == 0.0

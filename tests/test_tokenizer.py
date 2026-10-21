import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from sheetcalc.errors import ParseError
from sheetcalc.tokenizer import tokenize


def pairs(text):
    return [(token.kind.name, token.text) for token in tokenize(text)]


def test_arithmetic_is_split_into_numbers_and_operators():
    assert pairs("1+2*3") == [
        ("NUMBER", "1"),
        ("OPERATOR", "+"),
        ("NUMBER", "2"),
        ("OPERATOR", "*"),
        ("NUMBER", "3"),
        ("END", ""),
    ]


@pytest.mark.parametrize("text", [".5", "1.5e2", "2E-1", "7.", "10", "3e+4"])
def test_each_numeric_form_is_a_single_token(text):
    assert pairs(text) == [("NUMBER", text), ("END", "")]


def test_exponent_marker_without_digits_is_not_part_of_the_number():
    assert pairs("2e") == [("NUMBER", "2"), ("NAME", "E"), ("END", "")]


def test_cell_references_and_names_are_told_apart_and_upper_cased():
    assert pairs("a1 sum b22 x_y A1B AA1") == [
        ("CELL", "A1"),
        ("NAME", "SUM"),
        ("CELL", "B22"),
        ("NAME", "X_Y"),
        ("NAME", "A1B"),
        ("CELL", "AA1"),  # looks like a cell; the evaluator decides it is outside the grid
        ("END", ""),
    ]


def test_range_is_two_cells_around_a_colon():
    assert pairs("A1:B2") == [("CELL", "A1"), ("COLON", ":"), ("CELL", "B2"), ("END", "")]


def test_two_character_comparisons_are_not_split():
    assert [text for kind, text in pairs("<= >= <> < > =") if kind == "OPERATOR"] == [
        "<=",
        ">=",
        "<>",
        "<",
        ">",
        "=",
    ]


def test_doubled_quote_inside_a_string_is_one_quote_character():
    assert pairs('"say ""hi"""') == [("STRING", 'say "hi"'), ("END", "")]


def test_operators_inside_a_string_are_not_tokens():
    assert pairs('"a+b"') == [("STRING", "a+b"), ("END", "")]


def test_whitespace_is_skipped_but_positions_still_count_it():
    tokens = tokenize("  7")
    assert tokens[0].position == 2
    assert tokens[-1].position == 3  # END sits at the end of the text


def test_unterminated_string_points_at_the_opening_quote():
    with pytest.raises(ParseError) as caught:
        tokenize('1+"abc')
    assert caught.value.position == 2
    assert "closing quote" in caught.value.message


@pytest.mark.parametrize("text, position", [("1 $ 2", 2), ("#", 0), ("A1 & B1", 3)])
def test_character_outside_the_language_is_rejected_with_its_position(text, position):
    with pytest.raises(ParseError) as caught:
        tokenize(text)
    assert caught.value.position == position

import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from sheetcalc import AddressError, CellError, Sheet, SheetError, format_value


# ---- storing cells -------------------------------------------------------------------------


def test_numbers_are_stored_as_floats_whatever_type_was_given():
    sheet = Sheet()
    sheet.set("A1", 5)
    sheet.set("A2", 2.5)
    sheet.set("A3", "7")
    values = [sheet.value(a) for a in ("A1", "A2", "A3")]
    assert values == [5.0, 2.5, 7.0]
    assert all(isinstance(v, float) for v in values)


@pytest.mark.parametrize(
    "typed, expected",
    [
        (" 12 ", 12.0),
        ("-3.5", -3.5),
        ("+4", 4.0),
        (".5", 0.5),
        ("1e3", 1000.0),
        ("007", 7.0),
    ],
)
def test_numeric_text_becomes_a_number(typed, expected):
    sheet = Sheet()
    sheet.set("A1", typed)
    assert sheet.value("A1") == expected


@pytest.mark.parametrize("typed", ["nan", "inf", "-inf", "1_000", "12abc", "1.2.3", "-", "٣", "0x10"])
def test_text_that_only_resembles_a_number_stays_text(typed):
    # float() would accept nan, inf, underscores and non-ASCII digits; the sheet must not.
    sheet = Sheet()
    sheet.set("A1", typed)
    assert sheet.value("A1") == typed


def test_a_number_too_large_for_a_float_is_a_num_error_not_infinity():
    sheet = Sheet()
    sheet.set("A1", "1e999")
    assert sheet.value("A1") == CellError("#NUM")


def test_only_text_starting_with_equals_is_a_formula():
    sheet = Sheet()
    sheet.set("A1", " =1+1")
    sheet.set("A2", "1+1")
    assert sheet.value("A1") == " =1+1"
    assert sheet.value("A2") == "1+1"


def test_blank_text_clears_the_cell():
    sheet = Sheet()
    sheet.set("A1", 5)
    sheet.set("A1", "   ")
    assert sheet.value("A1") is None
    assert sheet.evaluate_all() == {}


def test_setting_a_cell_that_others_read_updates_them_when_it_is_cleared():
    sheet = Sheet()
    sheet.set("A1", 5)
    sheet.set("B1", "=A1+1")
    assert sheet.value("B1") == 6.0
    sheet.set("A1", "")
    assert sheet.value("B1") == 1.0


def test_addresses_are_case_insensitive():
    sheet = Sheet()
    sheet.set("b2", 3)
    assert sheet.value("B2") == 3.0
    assert sheet.value("b2") == 3.0


@pytest.mark.parametrize("bad", ["A0", "A100", "AA1", "", "hello", "1A"])
def test_bad_addresses_raise_address_error_on_set_and_value(bad):
    sheet = Sheet()
    with pytest.raises(AddressError):
        sheet.set(bad, 1)
    with pytest.raises(AddressError):
        sheet.value(bad)


@pytest.mark.parametrize(
    "bad, error",
    [(None, TypeError), (True, TypeError), ([1], TypeError), (float("nan"), ValueError),
     (float("inf"), ValueError), (10**400, ValueError)],
)
def test_values_that_cannot_be_stored_are_rejected(bad, error):
    sheet = Sheet()
    with pytest.raises(error):
        sheet.set("A1", bad)
    assert sheet.value("A1") is None  # a rejected value leaves the cell untouched


def test_a_syntax_error_in_one_formula_is_isolated_to_its_cell_and_dependents():
    sheet = Sheet()
    sheet.set("A1", "=1+")
    sheet.set("B1", "=A1+1")
    sheet.set("C1", "=2+2")
    assert sheet.value("A1") == CellError("#SYNTAX")
    assert sheet.value("B1") == CellError("#SYNTAX")
    assert sheet.value("C1") == 4.0


def test_evaluate_all_lists_non_blank_cells_in_reading_order():
    sheet = Sheet()
    sheet.set("B2", 1)
    sheet.set("A2", 2)
    sheet.set("Z1", 3)
    sheet.set("A1", 4)
    assert list(sheet.evaluate_all()) == ["A1", "Z1", "A2", "B2"]


# ---- CSV ----------------------------------------------------------------------------------


def test_csv_cells_starting_with_equals_are_formulas():
    sheet = Sheet.from_csv("2,3,=A1*B1\n10,=C1+A2,\n")
    assert sheet.evaluate_all() == {"A1": 2.0, "B1": 3.0, "C1": 6.0, "A2": 10.0, "B2": 16.0}


def test_csv_formula_with_commas_must_be_quoted_and_works_when_it_is():
    sheet = Sheet.from_csv('1,2,3,"=SUM(A1,B1,C1)"\n')
    assert sheet.value("D1") == 6.0


def test_csv_blank_cells_and_blank_lines_are_skipped():
    sheet = Sheet.from_csv(",,x\n\n,5,\n")
    assert sheet.evaluate_all() == {"C1": "x", "B3": 5.0}


def test_csv_row_and_column_positions_map_to_the_grid():
    sheet = Sheet.from_csv("a\nb\n" + "," * 25 + "last\n")
    assert sheet.value("A1") == "a"
    assert sheet.value("A2") == "b"
    assert sheet.value("Z3") == "last"


def test_csv_quoted_text_keeps_commas_quotes_and_line_breaks():
    sheet = Sheet.from_csv('"a, b","say ""hi""","two\nlines"\n')
    assert sheet.value("A1") == "a, b"
    assert sheet.value("B1") == 'say "hi"'
    assert sheet.value("C1") == "two\nlines"


def test_csv_windows_line_endings_are_accepted():
    assert Sheet.from_csv("1,2\r\n3,4\r\n").evaluate_all() == {"A1": 1.0, "B1": 2.0, "A2": 3.0, "B2": 4.0}


def test_csv_with_the_last_allowed_cell_loads_and_the_next_one_does_not():
    assert Sheet.from_csv("," * 25 + "x").value("Z1") == "x"
    assert Sheet.from_csv("\n" * 98 + "x").value("A99") == "x"
    with pytest.raises(SheetError, match="row 1, column 27"):
        Sheet.from_csv("," * 26 + "x")
    with pytest.raises(SheetError, match="row 100, column 1"):
        Sheet.from_csv("\n" * 99 + "x")


def test_csv_blank_cells_outside_the_grid_are_harmless():
    sheet = Sheet.from_csv("1," + "," * 30 + "\n")  # 32 columns, all but the first blank
    assert sheet.evaluate_all() == {"A1": 1.0}


def test_csv_with_an_oversized_field_is_reported_as_malformed():
    with pytest.raises(SheetError, match="malformed CSV"):
        Sheet.from_csv("a" * 200_000)


def test_load_csv_reads_a_file_and_skips_the_excel_byte_order_mark(tmp_path):
    path = tmp_path / "book.csv"
    path.write_bytes("﻿4,=A1*2\n".encode("utf-8"))
    sheet = Sheet.load_csv(str(path))
    assert sheet.value("A1") == 4.0  # without the BOM handling this would be text
    assert sheet.value("B1") == 8.0


def test_load_csv_keeps_non_ascii_text(tmp_path):
    path = tmp_path / "pl.csv"
    path.write_bytes("zażółć,=A1\n".encode("utf-8"))
    assert Sheet.load_csv(str(path)).value("B1") == "zażółć"


def test_load_csv_of_a_missing_file_raises_os_error(tmp_path):
    with pytest.raises(OSError):
        Sheet.load_csv(str(tmp_path / "nope.csv"))


# ---- rendering ----------------------------------------------------------------------------


def test_render_aligns_numbers_right_and_text_left():
    sheet = Sheet.from_csv("Item,Qty\nPen,=2*3\nInk,10\n")
    assert sheet.render().split("\n") == [
        "  | A    | B",
        "--+------+----",
        "1 | Item | Qty",
        "2 | Pen  |   6",
        "3 | Ink  |  10",
    ]


def test_render_shows_errors_and_booleans_as_text_and_leaves_gaps_blank():
    sheet = Sheet.from_csv(",=1/0\n=2>1,\n")
    assert sheet.render().split("\n") == [
        "  | A    | B",
        "--+------+-------",
        "1 |      | #DIV/0",
        "2 | TRUE |",
    ]


def test_render_shows_a_cycle_in_every_cell_of_the_loop():
    lines = Sheet.from_csv("=B1,=A1\n").render().split("\n")
    assert lines[-1] == "1 | #CYCLE | #CYCLE"


def test_render_keeps_multi_line_text_on_one_line():
    sheet = Sheet.from_csv('"two\nlines",x\n')
    assert sheet.render().split("\n")[-1] == "1 | two lines | x"


def test_render_of_an_empty_sheet():
    assert Sheet().render() == "(empty sheet)"


def test_render_widens_the_row_label_column_for_two_digit_rows():
    sheet = Sheet()
    sheet.set("A10", 1)
    lines = sheet.render().split("\n")
    assert lines[0] == "   | A"
    assert lines[-1] == "10 | 1"
    assert lines[1].startswith("---+-")


# ---- value formatting ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, shown",
    [
        (3.0, "3"),
        (-0.0, "0"),
        (0.1 + 0.2, "0.3"),
        (1 / 3, "0.3333333333"),
        (1234567.891, "1234567.891"),
        (1e15, "1e+15"),
        (123456789012345.0, "123456789012345"),
        (True, "TRUE"),
        (False, "FALSE"),
        (None, ""),
        ("text", "text"),
        (CellError("#REF", "why"), "#REF"),
    ],
)
def test_format_value(value, shown):
    assert format_value(value) == shown


def test_error_equality_ignores_the_explanation_but_not_the_code():
    assert CellError("#REF", "one reason") == CellError("#REF", "another")
    assert CellError("#REF") != CellError("#NAME")

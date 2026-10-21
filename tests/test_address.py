import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from sheetcalc.address import (
    expand_range,
    format_address,
    parse_address,
    require_address,
    row_major_key,
)
from sheetcalc.errors import AddressError


@pytest.mark.parametrize("text, expected", [("A1", (1, 1)), ("z99", (26, 99)), ("C10", (3, 10))])
def test_valid_addresses_give_column_and_row(text, expected):
    assert parse_address(text) == expected


@pytest.mark.parametrize(
    "text",
    ["A0", "A100", "AA1", "1A", "", "A", "A01", "A-1", "A 1", "Ａ" + "1", "A²"],
)
def test_text_outside_the_grid_or_not_an_address_gives_none(text):
    assert parse_address(text) is None


def test_format_address_is_the_inverse_of_parse_address():
    assert format_address(26, 99) == "Z99"
    assert parse_address(format_address(7, 42)) == (7, 42)


def test_require_address_canonicalises_case():
    assert require_address("b7") == "B7"


@pytest.mark.parametrize("bad", ["A0", "AA1", "", "7", None, 5])
def test_require_address_rejects_everything_else(bad):
    with pytest.raises(AddressError):
        require_address(bad)


def test_range_is_listed_in_reading_order():
    assert expand_range("A1", "B2") == ["A1", "B1", "A2", "B2"]


def test_range_corners_may_be_given_in_any_order():
    assert expand_range("B2", "A1") == expand_range("A1", "B2")
    assert expand_range("B1", "A2") == expand_range("A1", "B2")


def test_single_cell_range_has_one_address():
    assert expand_range("C3", "C3") == ["C3"]


def test_whole_grid_range_has_26_times_99_cells():
    assert len(expand_range("A1", "Z99")) == 2574


def test_range_with_a_corner_outside_the_grid_is_none():
    assert expand_range("A1", "A100") is None
    assert expand_range("AA1", "A1") is None


def test_row_major_key_sorts_in_reading_order():
    assert sorted(["B2", "A2", "Z1", "A1"], key=row_major_key) == ["A1", "Z1", "A2", "B2"]

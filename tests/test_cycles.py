import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sheetcalc import CellError, Sheet
from sheetcalc.address import expand_range

CYCLE = CellError("#CYCLE")


def make(cells):
    sheet = Sheet()
    for address, value in cells.items():
        sheet.set(address, value)
    return sheet


def test_two_cells_that_read_each_other_are_both_cycle_errors():
    sheet = make({"A1": "=B1", "B1": "=A1"})
    assert sheet.value("A1") == CYCLE
    assert sheet.value("B1") == CYCLE


def test_a_cell_that_reads_itself_is_a_cycle():
    assert make({"A1": "=A1+1"}).value("A1") == CYCLE


def test_cycle_error_names_the_cells_involved():
    error = make({"B2": "=A1", "A1": "=B2"}).value("A1")
    assert "A1, B2" in error.message


def test_cells_outside_the_cycle_still_get_their_values():
    sheet = make({"A1": "=B1", "B1": "=A1", "C1": 5, "D1": "=C1*2"})
    assert sheet.value("C1") == 5.0
    assert sheet.value("D1") == 10.0


def test_a_cell_that_reads_a_cycle_inherits_the_error():
    # C1 is not part of the loop, but its input is an error, so it shows the same error.
    sheet = make({"A1": "=B1", "B1": "=A1", "C1": "=A1+1", "D1": "=C1*2"})
    assert sheet.value("C1") == CYCLE
    assert sheet.value("D1") == CYCLE


def test_a_cycle_through_a_range_is_found():
    # A1 sums B1:B3, and B3 reads A1; B1 and B2 are plain numbers outside the loop.
    sheet = make({"A1": "=SUM(B1:B3)", "B1": 1, "B2": 2, "B3": "=A1"})
    assert sheet.value("A1") == CYCLE
    assert sheet.value("B3") == CYCLE
    assert sheet.value("B1") == 1.0
    assert sheet.value("B2") == 2.0


def test_a_ring_of_26_cells_is_one_cycle():
    sheet = Sheet()
    columns = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for index, letter in enumerate(columns):
        following = columns[(index + 1) % 26]
        sheet.set(f"{letter}1", f"={following}1")
    assert set(sheet.evaluate_all().values()) == {CYCLE}
    assert len(sheet.evaluate_all()) == 26


def test_two_separate_cycles_are_both_reported():
    sheet = make({"A1": "=B1", "B1": "=A1", "C1": "=D1", "D1": "=C1", "E1": 1})
    assert sheet.evaluate_all() == {
        "A1": CYCLE, "B1": CYCLE, "C1": CYCLE, "D1": CYCLE, "E1": 1.0,
    }


def test_breaking_the_loop_makes_the_cells_calculable_again():
    sheet = make({"A1": "=B1+1", "B1": "=A1"})
    assert sheet.value("A1") == CYCLE
    sheet.set("B1", 10)
    assert sheet.value("A1") == 11.0
    assert sheet.value("B1") == 10.0


def test_closing_a_loop_on_a_calculated_sheet_turns_the_cells_into_cycle_errors():
    sheet = make({"A1": 1, "B1": "=A1+1"})
    assert sheet.value("B1") == 2.0
    sheet.set("A1", "=B1")  # now A1 reads B1 and B1 reads A1
    assert sheet.value("B1") == CYCLE
    assert sheet.value("A1") == CYCLE


def test_dependencies_are_static_so_an_untaken_branch_still_counts():
    # IF would never read A1 here, but the engine finds references before running anything.
    assert make({"A1": "=IF(1,5,A1)"}).value("A1") == CYCLE


def test_a_cycle_does_not_hide_other_errors_in_the_sheet():
    sheet = make({"A1": "=B1", "B1": "=A1", "C1": "=1/0", "D1": "=FOO"})
    assert sheet.value("C1") == CellError("#DIV/0")
    assert sheet.value("D1") == CellError("#NAME")


def test_chain_across_the_whole_grid_is_calculated_without_recursion():
    # 2574 cells, each one reading the one before it: far deeper than Python's recursion limit.
    addresses = expand_range("A1", "Z99")
    sheet = Sheet()
    for previous, address in reversed(list(zip(addresses, addresses[1:]))):
        sheet.set(address, f"={previous}+1")  # entered last-to-first on purpose
    sheet.set("A1", 1)
    assert sheet.value("Z99") == 2574.0


def test_chain_across_the_whole_grid_that_ends_in_a_loop_is_all_cycle_errors():
    addresses = expand_range("A1", "Z99")
    sheet = Sheet()
    for previous, address in zip(addresses, addresses[1:]):
        sheet.set(address, f"={previous}+1")
    sheet.set("A1", "=Z99")  # closes the loop
    assert sheet.value("Z99") == CYCLE
    assert set(sheet.evaluate_all().values()) == {CYCLE}

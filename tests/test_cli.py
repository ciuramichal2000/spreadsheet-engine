import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import io
import subprocess

from sheetcalc.__main__ import main

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")


def run(args):
    out, err = io.StringIO(), io.StringIO()
    status = main(args, stdout=out, stderr=err)
    return status, out.getvalue(), err.getvalue()


def write(tmp_path, content, name="sheet.csv"):
    path = tmp_path / name
    path.write_bytes(content)
    return str(path)


def test_prints_the_evaluated_grid(tmp_path):
    path = write(tmp_path, b"Item,Qty\nPen,=2*3\n")
    status, out, err = run([path])
    assert status == 0
    assert err == ""
    assert out.split("\n") == [
        "  | A    | B",
        "--+------+----",
        "1 | Item | Qty",
        "2 | Pen  |   6",
        "",
    ]


def test_cell_option_prints_one_value(tmp_path):
    path = write(tmp_path, b"4,=A1*A1\n")
    assert run([path, "--cell", "B1"]) == (0, "16\n", "")
    assert run([path, "--cell", "b1"]) == (0, "16\n", "")


def test_cell_option_prints_error_codes_and_blanks(tmp_path):
    path = write(tmp_path, b"=1/0\n")
    assert run([path, "--cell", "A1"]) == (0, "#DIV/0\n", "")
    assert run([path, "--cell", "C3"]) == (0, "\n", "")


def test_missing_file_is_a_clean_failure_not_a_traceback(tmp_path):
    status, out, err = run([str(tmp_path / "missing.csv")])
    assert status == 2
    assert out == ""
    assert err.startswith("sheetcalc: ")


def test_cell_outside_the_grid_is_a_clean_failure(tmp_path):
    path = write(tmp_path, b"1\n")
    status, out, err = run([path, "--cell", "AA1"])
    assert status == 2
    assert out == ""
    assert "AA1" in err


def test_csv_that_does_not_fit_the_grid_is_a_clean_failure(tmp_path):
    path = write(tmp_path, b"\n" * 99 + b"x\n")
    status, out, err = run([path])
    assert status == 2
    assert "row 100" in err


def test_file_that_is_not_utf8_is_a_clean_failure(tmp_path):
    path = write(tmp_path, b"caf\xe9,1\n")  # latin-1 bytes
    status, out, err = run([path])
    assert status == 2
    assert err.startswith("sheetcalc: ")


def test_shipped_example_gives_the_numbers_worked_out_by_hand():
    path = os.path.join(PROJECT_ROOT, "examples", "budget.csv")
    cells = {cell: run([path, "--cell", cell])[1].strip() for cell in ("D2", "D3", "D4", "E4", "D5", "D6", "D7", "D8")}
    assert cells == {
        "D2": "15",  # 1.5 * 10
        "D3": "17",  # 4.25 * 4
        "D4": "24",  # 12 * 2
        "E4": "over 20",  # 24 > 20
        "D5": "56",  # 15 + 17 + 24
        "D6": "18.66666667",  # 56 / 3
        "D7": "24",
        "D8": "0.4285714286",  # 24 / 56 = 3 / 7
    }


def test_module_entry_point_runs_end_to_end(tmp_path):
    path = write(tmp_path, b"2,3,=SUM(A1:B1)*2\n")
    result = subprocess.run(
        [sys.executable, "-m", "sheetcalc", path, "--cell", "C1"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "10"
    assert result.stderr == ""

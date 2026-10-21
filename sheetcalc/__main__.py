"""Command line: print an evaluated CSV sheet, or the value of one cell."""

import argparse
import sys
from collections.abc import Sequence
from typing import TextIO

from .errors import SheetError
from .sheet import Sheet
from .values import format_value


def main(
    argv: Sequence[str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the CLI; returns the exit status (0 ok, 2 for an unreadable file or bad cell)."""
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    parser = argparse.ArgumentParser(
        prog="sheetcalc",
        description="Evaluate a CSV file whose cells starting with '=' are formulas.",
    )
    parser.add_argument("csv_file", help="path of a UTF-8 CSV file (grid A1..Z99)")
    parser.add_argument("--cell", metavar="ADDRESS", help="print only the value of this cell, e.g. B4")
    args = parser.parse_args(argv)

    try:
        sheet = Sheet.load_csv(args.csv_file)
        if args.cell is None:
            print(sheet.render(), file=out)
        else:
            print(format_value(sheet.value(args.cell)), file=out)
    except (OSError, SheetError, UnicodeDecodeError) as error:
        print(f"sheetcalc: {error}", file=err)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

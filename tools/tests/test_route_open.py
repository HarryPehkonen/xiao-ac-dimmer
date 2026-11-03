#!/usr/bin/env python3
"""Regression: opening a pad near the board edge must not run off the grid.

`_open()` walks a pad's opening disc and its escape spoke in cell coordinates
and asks the grid about every cell it lands on.  `Grid.unblock()` and
`Grid.block()` both ignore a cell that is not on the grid, but `Grid.is_blocked()`
did not: it indexed the bytearray with whatever cell it was handed.  A pad
within `cr` cells of an edge therefore made the walk read past the end of the
grid -- an `IndexError` out of the router, where the contract is the router's own
`no path <ref>.<pad> -> <ref>.<pad> [diagnosis]`.

Found end to end at 150 x 51 mm (a board shorter than its parts span);
reproduced here without a board, which is where the guard belongs.

Red before the fix: every test below either raises IndexError or reads a wrong
(off-grid) cell.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pcbnew

import route as R

# pcbnew objects are C++-owned and a pad is freed when its footprint is: bind
# every board/footprint/pad to a name here so the garbage collector cannot take
# one out from under a test.
_KEEP = []


def _pad(ref, num, x_mm, y_mm, size_mm=1.6):
    """A through-hole pad on its own footprint, built headless.

    `_open()` only needs the pad's position and size, so a bare footprint on a
    throwaway board is enough -- no library, no project, no file on disk.
    """
    board = pcbnew.BOARD()
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference(ref)
    pad = pcbnew.PAD(fp)
    pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    pad.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(size_mm), pcbnew.FromMM(size_mm)))
    pad.SetDrillSize(pcbnew.VECTOR2I(pcbnew.FromMM(0.8), pcbnew.FromMM(0.8)))
    pad.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm)))
    pad.SetNumber(num)
    fp.Add(pad)
    _KEEP.append((board, fp, pad))
    return pad


class TestOffGridCells(unittest.TestCase):
    """A cell that is not on the grid is not a cell this router may use.

    Off the grid, `is_blocked` must answer -- treat the cell as blocked, the way
    `inside()` refuses it -- and never index the bytearray out of range.
    """

    def setUp(self):
        self.grid = R.Grid()

    def test_past_the_last_row_is_blocked(self):
        self.assertTrue(self.grid.is_blocked(0, self.grid.ny, 0))

    def test_above_the_first_row_is_blocked(self):
        self.assertTrue(self.grid.is_blocked(0, -1, 0))

    def test_left_of_the_first_column_is_blocked(self):
        self.assertTrue(self.grid.is_blocked(-1, 0, 0))

    def test_past_the_last_column_is_blocked(self):
        self.assertTrue(self.grid.is_blocked(self.grid.nx, 0, 1))


class TestOpenAtTheEdge(unittest.TestCase):
    """`_open()` on a pad inside `cr` cells of the board edge.

    On the shipped 150 x 57 mm grid, a pad half a millimetre from the bottom
    edge is exactly the case that crashed: the disc and the escape spoke reach
    past the last row.
    """

    def setUp(self):
        self.grid = R.Grid()
        self.y = R.H - 0.5                      # within cr of the bottom edge
        self.pad = _pad("J1", "1", 10.0, self.y)
        self.mate = _pad("J1", "2", 12.54, self.y)   # gives the pad a spoke
        self.all_pads = [(self.pad, ("J1", "1")), (self.mate, ("J1", "2"))]

    def _open(self, pad=None):
        R._open(self.grid, pad or self.pad, {("J1", "1")}, self.all_pads,
                (R.Grid(), R.Grid()))

    def test_pad_at_the_bottom_edge_does_not_raise(self):
        self._open()

    def test_pad_in_the_bottom_corner_does_not_raise(self):
        corner = _pad("J2", "1", 0.5, self.y)
        mate = _pad("J2", "2", 2.54, self.y)
        R._open(self.grid, corner, {("J2", "1")},
                [(corner, ("J2", "1")), (mate, ("J2", "2"))],
                (R.Grid(), R.Grid()))

    def test_pad_at_the_bottom_edge_still_opens_on_the_grid(self):
        """The guard skips only what is off the grid: a pad that is on it is
        still opened, so the fix cannot quietly stop opening real pads."""
        self.grid.block(20, R._c(self.y), 0)     # block the pad's own cell, L0
        self.grid.block(20, R._c(self.y), 1)
        self._open()
        self.assertFalse(self.grid.is_blocked(20, R._c(self.y), 0))
        self.assertFalse(self.grid.is_blocked(20, R._c(self.y), 1))


if __name__ == "__main__":
    unittest.main()

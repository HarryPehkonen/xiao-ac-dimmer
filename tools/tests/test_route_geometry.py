#!/usr/bin/env python3
"""Pure-function tests for the grid router.

These run without a board: geometry and path-merging are plain arithmetic, so
they are cheap and they pin down the rules the routed board depends on.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import route as R


class TestGridRoundTrip(unittest.TestCase):
    """_c/_mm must be exact inverses on the 0.5 mm grid."""

    def test_round_trip_on_grid(self):
        for mm in (0.0, 0.5, 1.0, 2.5, 7.5, 23.0, 75.5, 130.0):
            self.assertEqual(R._mm(R._c(mm)), mm)

    def test_cell_indices(self):
        self.assertEqual(R._c(0.0), 0)
        self.assertEqual(R._c(0.5), 1)
        self.assertEqual(R._c(1.0), 2)
        self.assertEqual(R._c(2.5), 5)
        self.assertEqual(R._mm(1), 0.5)
        self.assertEqual(R._mm(2), 1.0)

    def test_grid_is_half_mm(self):
        self.assertEqual(R.GRID, 0.5)


class TestToSegments(unittest.TestCase):
    """_to_segments merges runs; it must never invent or drop geometry."""

    def test_collinear_run_merges(self):
        path = [(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)]
        self.assertEqual(R._to_segments(path), [((0, 0, 0), (3, 0, 0))])

    def test_corner_makes_two_segments(self):
        path = [(0, 0, 0), (1, 0, 0), (2, 0, 0), (2, 1, 0), (2, 2, 0)]
        self.assertEqual(
            R._to_segments(path),
            [((0, 0, 0), (2, 0, 0)), ((2, 0, 0), (2, 2, 0))])

    def test_two_corners_make_three_segments(self):
        path = [(0, 0, 0), (2, 0, 0), (2, 2, 0), (4, 2, 0)]
        segs = R._to_segments(path)
        self.assertEqual(
            segs,
            [((0, 0, 0), (2, 0, 0)), ((2, 0, 0), (2, 2, 0)),
             ((2, 2, 0), (4, 2, 0))])

    def test_layer_change_splits(self):
        path = [(0, 0, 0), (2, 0, 0), (2, 0, 1), (2, 2, 1)]
        self.assertEqual(
            R._to_segments(path),
            [((0, 0, 0), (2, 0, 0)), ((2, 0, 1), (2, 2, 1))])

    def test_layer_change_without_run_does_not_emit_zero_length(self):
        path = [(0, 0, 0), (1, 0, 0), (1, 0, 1), (1, 1, 1)]
        segs = R._to_segments(path)
        self.assertEqual(
            segs,
            [((0, 0, 0), (1, 0, 0)), ((1, 0, 1), (1, 1, 1))])
        for a, b in segs:
            self.assertNotEqual(a, b)

    def test_never_emits_zero_length(self):
        # a path that turns at every step and changes layer mid-way
        path = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1),
                (0, 0, 1)]
        for a, b in R._to_segments(path):
            self.assertNotEqual(a, b)

    def test_every_grid_step_is_covered(self):
        path = [(0, 0, 0), (1, 0, 0), (2, 0, 0), (2, 1, 0), (2, 1, 1),
                (3, 1, 1)]
        segs = R._to_segments(path)
        covered = set()
        for a, b in segs:
            self.assertEqual(a[2], b[2])
            ax, ay, _ = a
            bx, by, _ = b
            steps = max(abs(bx - ax), abs(by - ay))
            for i in range(steps):
                covered.add((ax + (bx - ax) * i // steps,
                             ay + (by - ay) * i // steps, a[2]))
        self.assertIn((0, 0, 0), covered)
        self.assertIn((1, 0, 0), covered)
        self.assertIn((2, 0, 0), covered)

    def test_single_step(self):
        self.assertEqual(R._to_segments([(0, 0, 0), (1, 0, 0)]),
                         [((0, 0, 0), (1, 0, 0))])


class TestEscapeSpoke(unittest.TestCase):
    """The escape spoke runs perpendicular to the nearest neighbour."""

    def _dot_with(self, dirs, vx, vy):
        return [round(dx * vx + dy * vy, 6) for dx, dy in dirs]

    def test_neighbour_above_runs_horizontally(self):
        dirs = R._escape_dirs(10.0, 10.0, [(10.0, 7.46)])   # neighbour at -y
        self.assertTrue(dirs)
        for d in self._dot_with(dirs, 0.0, 1.0):            # along the neighbour
            self.assertAlmostEqual(d, 0.0, places=6)
        for dx, dy in dirs:                                 # perpendicular
            self.assertAlmostEqual(abs(dx), 1.0, places=6)
            self.assertAlmostEqual(dy, 0.0, places=6)

    def test_neighbour_below_runs_horizontally(self):
        dirs = R._escape_dirs(10.0, 10.0, [(10.0, 12.54)])
        self.assertTrue(dirs)
        for d in self._dot_with(dirs, 0.0, 1.0):
            self.assertAlmostEqual(d, 0.0, places=6)
        for dx, dy in dirs:
            self.assertAlmostEqual(abs(dx), 1.0, places=6)
            self.assertAlmostEqual(dy, 0.0, places=6)

    def test_neighbour_left_runs_vertically(self):
        dirs = R._escape_dirs(10.0, 10.0, [(7.46, 10.0)])
        self.assertTrue(dirs)
        for d in self._dot_with(dirs, 1.0, 0.0):
            self.assertAlmostEqual(d, 0.0, places=6)
        for dx, dy in dirs:
            self.assertAlmostEqual(dx, 0.0, places=6)
            self.assertAlmostEqual(abs(dy), 1.0, places=6)

    def test_neighbour_right_runs_vertically(self):
        dirs = R._escape_dirs(10.0, 10.0, [(12.54, 10.0)])
        self.assertTrue(dirs)
        for d in self._dot_with(dirs, 1.0, 0.0):
            self.assertAlmostEqual(d, 0.0, places=6)
        for dx, dy in dirs:
            self.assertAlmostEqual(dx, 0.0, places=6)
            self.assertAlmostEqual(abs(dy), 1.0, places=6)

    def test_two_opposite_directions(self):
        dirs = R._escape_dirs(10.0, 10.0, [(10.0, 7.46)])
        self.assertEqual(len(dirs), 2)
        self.assertAlmostEqual(dirs[0][0], -dirs[1][0], places=6)
        self.assertAlmostEqual(dirs[0][1], -dirs[1][1], places=6)

    def test_no_neighbour_no_spoke(self):
        self.assertEqual(R._escape_dirs(10.0, 10.0, []), [])
        self.assertEqual(R._escape_dirs(10.0, 10.0, [(30.0, 30.0)]), [])

    def test_nearest_neighbour_wins(self):
        dirs = R._escape_dirs(10.0, 10.0, [(10.0, 6.0), (12.0, 10.0)])
        # nearest is the one at (12, 10): to the right, so vertical spoke
        for dx, dy in dirs:
            self.assertAlmostEqual(dx, 0.0, places=6)
            self.assertAlmostEqual(abs(dy), 1.0, places=6)


if __name__ == "__main__":
    unittest.main()

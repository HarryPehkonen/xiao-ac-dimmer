#!/usr/bin/env python3
"""The gate's teeth: sixteen ways to break this board's rules, each of which
`check_board.py` must report.

`check_board.py` gates three things DRC has no rule for -- every footprint id
names its library, the four M3 mounting holes are where and what the design says
with an empty copper keepout, and the XIAO socket pair is the shape that accepts
the module.  The first two were gated by a pass of their own; the socket gate is
new, and this file is where it is seen to fail.

Why the socket needs its own tests: every mutation below leaves a board that
ERC, DRC, the netlist checker and the router are all perfectly happy with.  That
is the whole point -- the board this file replaces was 16/16 routed, DRC-clean
and could not hold its MCU.

The board is loaded from disk and mutated in memory: nothing is written.  The
honest board must report nothing, so no test can pass by the gate complaining
about everything.  The last tests are the router's own: the ordering that this
board needs, and the retry that finds it.

Mutating rather than deleting is deliberate.  In this KiCad binding,
`FOOTPRINT.Remove(pad)` and `BOARD.Remove(<drawing or group>)` free the object
out from under the swig wrapper: the test appears to pass and a *later* test
dies with a segmentation fault, which reads as a gate bug rather than a test
bug.  Every case below renames, moves, renumbers or adds instead.  (Measured
2026-11-03, KiCad 9.0.2 + /usr/bin/python3 3.13.5.)
"""
import contextlib
import io
import os
import sys

import pcbnew
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import check_board
import gen_pcb
import gen_sch
import route


@pytest.fixture
def board():
    """A fresh copy of the committed board, per test."""
    b = pcbnew.LoadBoard(gen_pcb.BOARD)
    assert b is not None, f"cannot load {gen_pcb.BOARD}"
    return b


def _failures(board):
    return check_board.geometry(board) + check_board.xiao_socket(board)


def _fp(board, ref):
    for fp in board.GetFootprints():
        if fp.GetReference() == ref:
            return fp
    raise AssertionError(f"the committed board has no {ref}")


def _pad(fp, number):
    for p in fp.Pads():
        if p.GetNumber() == number:
            return p
    raise AssertionError(f"{fp.GetReference()} has no pad {number}")


def _says(failures, text):
    hits = [f for f in failures if text in f]
    assert hits, f"nothing said '{text}':\n  " + "\n  ".join(failures)
    return hits[0]


def _move_x(fp, dx):
    p = fp.GetPosition()
    fp.SetPosition(pcbnew.VECTOR2I(p.x + pcbnew.FromMM(dx), p.y))


# ----------------------------------------------------------- the honest board
def test_honest_board_reports_no_geometry_problem(board):
    """The other half of every sabotage test: the gate must be quiet here."""
    assert _failures(board) == []


def test_the_honest_socket_is_a_module_apart(board):
    """The numbers the gate exists for, read off the committed board."""
    j1, j2 = _fp(board, "J1"), _fp(board, "J2")
    x1 = pcbnew.ToMM(_pad(j1, "1").GetPosition().x)
    x2 = pcbnew.ToMM(_pad(j2, "1").GetPosition().x)
    assert abs((x2 - x1) - gen_pcb.XIAO["row_sep"]) < 0.01
    # pin 1 of both rows at the same end: the end the module's USB-C is at
    y1 = pcbnew.ToMM(_pad(j1, "1").GetPosition().y)
    y2 = pcbnew.ToMM(_pad(j2, "1").GetPosition().y)
    assert abs(y1 - y2) < 0.01
    for fp in (j1, j2):
        assert fp.IsLocked()
    assert check_board.xiao_socket(board) == []


# ----------------------------------------------------------------- sabotage --
def test_rows_too_close_fails(board):
    """The defect this task exists for: 6.1 mm of socket for a 15.24 mm module."""
    _move_x(_fp(board, "J2"), -9.14)                 # back to the old spacing
    _says(_failures(board), "mm apart, a XIAO needs 15.24 mm")


def test_a_pin_that_is_not_in_the_row_fails(board):
    """A row with a hole that is not one of the module's 7 pins.

    Not simulated by deleting a pad: `FOOTPRINT.Remove(pad)` frees the pad out
    from under the swig wrapper and the interpreter dies later, in a different
    test, looking like a gate bug.  Renumbering is the same defect to the gate
    and leaves the binding alive.
    """
    _pad(_fp(board, "J1"), "4").SetNumber("8")
    _says(_failures(board), "a XIAO row is 1..7")


def test_an_extra_pin_fails(board):
    fp = _fp(board, "J1")
    src = _pad(fp, "1")
    p = pcbnew.PAD(fp)
    p.SetNumber("8")
    p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    p.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(1.7), pcbnew.FromMM(1.7)))
    p.SetDrillSize(pcbnew.VECTOR2I(pcbnew.FromMM(1.0), pcbnew.FromMM(1.0)))
    q = src.GetPosition()
    p.SetPosition(pcbnew.VECTOR2I(q.x, q.y + pcbnew.FromMM(7 * 2.54)))
    fp.Add(p)
    _says(_failures(board), "a XIAO row is 7 (7 + 7 = the module's 14)")


def test_a_reversed_row_fails(board):
    """A row in the other way round fires the wrong pin and nothing else sees it."""
    fp = _fp(board, "J1")
    fp.SetOrientationDegrees(180)       # the footprint's origin is its pad 1
    _says(_failures(board), "the row is in the other way round")


def test_a_row_in_the_other_way_round_by_number_fails(board):
    """The same defect without moving anything: pad 1 and pad 7 swapped."""
    fp = _fp(board, "J1")
    for a, b in (("1", "7"), ("2", "6"), ("3", "5")):
        pa, pb = _pad(fp, a), _pad(fp, b)
        na, nb = pa.GetNumber(), pb.GetNumber()
        pa.SetNumber(nb)
        pb.SetNumber(na)
    failures = _failures(board)
    _says(failures, "the row is in the other way round")
    _says(failures, "one row is reversed relative to the other")


def test_a_part_inside_the_module_envelope_fails(board):
    src = "/usr/share/kicad/footprints/Resistor_SMD.pretty"
    fp = pcbnew.FootprintLoad(src, "R_0805_2012Metric")
    assert fp is not None
    x0, y0, x1, y1 = gen_pcb.xiao_envelope()
    fp.SetReference("R9")
    fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM((x0 + x1) / 2),
                                   pcbnew.FromMM((y0 + y1) / 2)))
    board.Add(fp)
    _says(_failures(board), "R9 reaches to")


def test_a_wrong_pitch_fails(board):
    pad = _pad(_fp(board, "J1"), "5")
    p = pad.GetPosition()
    pad.SetPosition(pcbnew.VECTOR2I(p.x, p.y + pcbnew.FromMM(0.7)))
    _says(_failures(board), "between pads, the module's pitch is 2.54 mm")


def test_a_hole_too_small_for_the_module_pin_fails(board):
    pad = _pad(_fp(board, "J2"), "3")
    pad.SetDrillSize(pcbnew.VECTOR2I(pcbnew.FromMM(0.6), pcbnew.FromMM(0.6)))
    _says(_failures(board), "mm hole, spec is 1 mm")


def test_a_row_out_of_the_group_fails(board):
    """The pair has to stay one object, or a packer can drift it apart again."""
    group = next(g for g in board.Groups()
                 if g.GetName() == gen_pcb.XIAO_GROUP)
    group.RemoveItem(_fp(board, "J2"))
    _says(_failures(board), "holds ['J1'], the socket rows are ['J1', 'J2']")


def test_a_missing_group_fails(board):
    """Renamed rather than deleted: removing a board-owned group is unsafe.

    To the gate a group under another name is a socket pair that is no longer
    one object, which is the defect.
    """
    group = next(g for g in board.Groups()
                 if g.GetName() == gen_pcb.XIAO_GROUP)
    group.SetName("J1_J2_loose")
    _says(_failures(board), "0 group(s) with that name")


def test_an_unlocked_row_fails(board):
    _fp(board, "J2").SetLocked(False)
    _says(_failures(board), "not locked")


def test_swapped_rows_fail(board):
    """D0..D6 is the module's left column; putting it on the right is a mix-up."""
    x1 = _fp(board, "J1").GetPosition().x
    x2 = _fp(board, "J2").GetPosition().x
    for fp, x in ((_fp(board, "J1"), x2), (_fp(board, "J2"), x1)):
        p = fp.GetPosition()
        fp.SetPosition(pcbnew.VECTOR2I(x, p.y))
    _says(_failures(board), "is the module's left column")


def test_a_missing_envelope_fails(board):
    """The keepout marker is what a reviewer looks for; parked off-layer = gone."""
    rect = next(d for d in board.GetDrawings()
                if d.GetLayer() == pcbnew.F_CrtYd)
    rect.SetLayer(pcbnew.F_Fab)         # not deleted: removing a board-owned
    _says(_failures(board), "0 rectangle(s) on F.CrtYd")   # item is unsafe here


def test_a_moved_envelope_fails(board):
    rect = next(d for d in board.GetDrawings()
                if d.GetLayer() == pcbnew.F_CrtYd)
    rect.Move(pcbnew.VECTOR2I(pcbnew.FromMM(2), pcbnew.FromMM(2)))
    _says(_failures(board), "the F.CrtYd rectangle is")


def test_the_trigger_on_the_wrong_pin_fails(board):
    """The row can be geometrically perfect and wired the other way round."""
    a = _pad(_fp(board, "J1"), "2")          # GATE_DRV (D1, GPIO3)
    b = _pad(_fp(board, "J1"), "3")          # ZCD_OUT (D2, GPIO4)
    na, nb = a.GetNetname(), b.GetNetname()
    assert na == "GATE_DRV" and nb == "ZCD_OUT", (na, nb)
    net_gate = board.GetNetsByName()["GATE_DRV"]
    net_zcd = board.GetNetsByName()["ZCD_OUT"]
    a.SetNet(net_zcd)
    b.SetNet(net_gate)
    failures = _failures(board)
    _says(failures, "the intent for this pin is 'GATE_DRV'")
    _says(failures, "the intent for this pin is 'ZCD_OUT'")


def test_a_socket_that_is_not_a_socket_fails(board):
    """A pad with no hole cannot take the module's pin."""
    pad = _pad(_fp(board, "J1"), "6")
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    _says(_failures(board), "not a through-hole pad")


# -------------------------------------------------------------- the router --
@pytest.fixture
def unrouted(tmp_path_factory):
    """An *unrouted* board on disk, and the intended nets, fresh per test.

    route() assumes the board it is handed has no copper on it -- it seeds its
    occupancy grids from the pads, not from existing tracks -- so every test
    that routes loads its own copy rather than reusing one.
    """
    import shutil

    tmp = tmp_path_factory.mktemp("gate")
    for ext in (".kicad_dru", ".kicad_pro"):
        src = os.path.join(ROOT, gen_pcb.PROJECT + ext)
        if os.path.exists(src):
            shutil.copy(src, str(tmp / (gen_pcb.PROJECT + ext)))
    had, was = hasattr(gen_pcb, "BOARD"), getattr(gen_pcb, "BOARD", None)
    had_rules = gen_pcb.write_rules
    gen_pcb.BOARD = str(tmp / (gen_pcb.PROJECT + ".kicad_pcb"))
    gen_pcb.write_rules = lambda: None
    real_route = route.route
    route.route = lambda *a, **k: {"routed": 0, "failed": {}, "attempts": 0}
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            gen_pcb.build()
    finally:
        route.route = real_route          # back before the test runs, or the
    try:                                  # test would call the stub
        yield gen_pcb.BOARD, gen_pcb.schematic_nets()
    finally:
        gen_pcb.write_rules = had_rules
        if had:
            gen_pcb.BOARD = was
        else:
            del gen_pcb.BOARD


def _route(path, nets, attempts):
    """Route a fresh copy of the board at `path`.  Returns (report, board)."""
    board = pcbnew.LoadBoard(path)
    by_name = board.GetNetsByName()
    netitems = {name: by_name[name] for name in nets}
    report = route.route(board, netitems, nets, verbose=False,
                         attempts=attempts)
    return report, board


def test_the_ordering_this_board_needs_is_the_second_one(unrouted):
    """The retry, seen to be needed.

    One pass puts GND ahead of ZCD_OUT (they tie on the free-cell key, and the
    span tie-break hands it to GND) and ZCD_OUT's corridor is then walled in:
    the board this task fixes needed two orderings.  Both halves are asserted,
    so neither "the router always needs two" nor "the router never retries" can
    pass unnoticed.
    """
    path, nets = unrouted
    one, _board = _route(path, nets, 1)
    assert one["routed"] == len(nets) - 1, one
    assert list(one["failed"]) == ["ZCD_OUT"]
    assert one["failed"]["ZCD_OUT"].startswith("no path R5.2 -> U1.5")

    two, _board = _route(path, nets, route.ATTEMPTS)
    assert two["routed"] == len(nets), two
    assert two["failed"] == {}
    assert two["attempts"] == 2


def test_the_retry_promotes_only_the_nets_that_failed():
    """The retry is a reordering, not a scramble: the losers move to the front."""
    order = ["A", "B", "C", "D"]
    assert route._promote(order, {"C"}) == ["C", "A", "B", "D"]
    assert route._promote(order, {"A", "D"}) == ["A", "D", "B", "C"]
    assert route._promote(order, {}) == order
    assert route.ATTEMPTS >= 2


def test_a_rerouted_board_is_still_clean(unrouted):
    """The board the router produces must also pass DRC.

    The retry throws copper away and lays it again; this is the check that a
    second ordering does not leave a board DRC would reject.
    """
    import subprocess

    path, nets = unrouted
    report, board = _route(path, nets, route.ATTEMPTS)
    assert report["failed"] == {}
    assert report["attempts"] == 2, "this board is only clean on the second order"
    pcbnew.SaveBoard(path, board)
    rpt = path + ".drc.rpt"
    proc = subprocess.run(["kicad-cli", "pcb", "drc", "--exit-code-violations",
                           "-o", rpt, path], capture_output=True, text=True)
    text = open(rpt, encoding="utf-8").read() if os.path.exists(rpt) else ""
    assert proc.returncode == 0, (text or proc.stdout + proc.stderr)[-2000:]

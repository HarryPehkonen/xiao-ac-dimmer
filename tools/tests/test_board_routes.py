#!/usr/bin/env python3
"""Whole-board gate: every net must route, and the routed board must pass DRC.

This is the acceptance test for the board.  The board is generated into a
temporary directory (with the project's .kicad_dru copied alongside it so the
3 mm isolation barrier is part of the check) and never written into the tree.

Red before the fix: 14 of 16 nets route, DRC reports 3 unconnected_items.
"""
import contextlib
import io
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)

PROJECT = "xiao-ac-dimmer"
EXPECTED_NETS = 16


@pytest.fixture(scope="module")
def routed_board(tmp_path_factory):
    """Build the board from source into a temp dir.  Returns (path, stdout)."""
    tmp = tmp_path_factory.mktemp("board")
    for ext in (".kicad_dru", ".kicad_pro"):
        src = os.path.join(ROOT, PROJECT + ext)
        if os.path.exists(src):
            shutil.copy(src, str(tmp / (PROJECT + ext)))

    import gen_pcb
    gen_pcb.BOARD = str(tmp / (PROJECT + ".kicad_pcb"))
    gen_pcb.write_rules = lambda: None      # never touch the tree's .kicad_dru

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        gen_pcb.build()
    return str(tmp / (PROJECT + ".kicad_pcb")), buf.getvalue()


def test_router_reports_every_net_routed(routed_board):
    _board, out = routed_board
    m = re.search(r"routed (\d+)/(\d+) nets", out)
    assert m, f"router said nothing about how much it routed:\n{out}"
    assert m.group(1) == m.group(2) == str(EXPECTED_NETS), out


def test_generated_board_passes_drc(routed_board):
    board, _out = routed_board
    report = board + ".drc.rpt"
    r = subprocess.run(["kicad-cli", "pcb", "drc", "--exit-code-violations",
                        "-o", report, board], capture_output=True, text=True)
    text = open(report, encoding="utf-8").read() if os.path.exists(report) else ""
    assert r.returncode == 0, (text or r.stdout + r.stderr)[-3000:]

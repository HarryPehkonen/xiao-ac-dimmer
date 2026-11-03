"""Seen to fail: the netlist must carry the module's pin names.

`J1`/`J2` used to be generic `Conn_01x07` sockets, so the exported netlist said
`Pin_2` and the only place that said "J1.2 is D1, the triac trigger" was a
comment.  They now have a symbol whose pins are named from Seeed's own module
pinout, and `check_netlist.py` asserts the names reach the netlist -- an
assertion nobody should trust until it has been seen to fail.

Each case below edits the *committed* schematic into a temp copy and requires
the gate to report it.  The first one is the point of the whole change: a pin
renamed in the schematic is invisible to ERC and to the netlist's connectivity
(no net moves), so without this check the schematic could go back to lying
about which pin is which and every gate would still pass.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import check_netlist
import gen_sch

SCH = os.path.join(gen_sch.ROOT, gen_sch.PROJECT + ".kicad_sch")


def row_block(text, sym):
    """The lib_symbols block of one socket-row symbol, as (head, block, tail)."""
    start = text.index(f'(symbol "{gen_sch.SYMLIB}:{sym}"')
    ends = [i for i in (text.find(marker, start + 1)
                        for marker in ("\n(symbol", "\n\t(symbol"))
            if i != -1]
    end = min(ends)
    return text[:start], text[start:end], text[end:]


def sabotage(tmp_path, name, edits):
    """The committed schematic with `edits` applied, as a temp copy."""
    text = open(SCH, encoding="utf-8").read()
    for old, new in edits:
        assert old in text, f"{old!r} is not in the schematic any more"
        text = text.replace(old, new, 1)
    path = os.path.join(str(tmp_path), name + ".kicad_sch")
    open(path, "w").write(text)
    return path


def gate(path):
    return check_netlist.run(sch=path)


def test_a_renamed_pin_fails_the_gate(tmp_path):
    """Rename J1's D1 (the trigger) to D2: no net moves, the name lies."""
    path = sabotage(tmp_path, "renamed", [('(name "D1"', '(name "D2"')])
    bad, lines = gate(path)
    assert bad == 1, lines
    assert "PIN NAME    J1.2: the netlist says 'D2', the module's pin is 'D1'" \
        in lines


def test_a_generic_row_fails_the_gate(tmp_path):
    """Put the generic names back: what the card replaced, seen to fail."""
    edits = [(f'(name "{name}"', f'(name "Pin_{i + 1}"')
             for i, name in enumerate(gen_sch.XIAO_ROWS[0]["names"])]
    path = sabotage(tmp_path, "generic", edits)
    bad, lines = gate(path)
    assert bad == len(gen_sch.XIAO_ROWS[0]["names"]), lines
    assert all("PIN NAME" in line for line in lines[:-1])


def test_a_renumbered_row_fails_the_gate(tmp_path):
    """Swap pins 1 and 2 of the right row: the numbers must not move silently.

    check_board.py asserts the board's pads against gen_sch.PARTS, so the
    physical side of a renumbering is already covered; this is the
    schematic/netlist side of the same rule.  Both pins are wired (+5V_XIAO and
    GND), so the nets move as well as the names -- both checks fire.
    """
    head, block, tail = row_block(open(SCH, encoding="utf-8").read(),
                                  "XIAO_ESP32C3_Right")
    block = block.replace('(number "1"', "\x00").replace('(number "2"',
                                                         '(number "1"')
    block = block.replace("\x00", '(number "2"')
    path = os.path.join(str(tmp_path), "renumbered.kicad_sch")
    open(path, "w").write(head + block + tail)
    bad, lines = gate(path)
    assert bad > 0, lines
    assert "PIN NAME    J2.1: the netlist says 'GND', the module's pin is " \
        "'VBUS'" in lines, lines
    assert any(line.startswith("MISMATCH") and "+5V_XIAO" in line
               for line in lines), lines


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

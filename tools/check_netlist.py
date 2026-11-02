#!/usr/bin/env python3
"""Gate: the exported netlist must equal the intended netlist.

Exports a kicadsexpr netlist with kicad-cli and compares it against
gen_sch.nets():

  * every intended net exists with exactly the intended pins,
  * no net exists that the intent does not name (no accidental shorts),
  * the only single-pin "unconnected-..." nets are the pins deliberately
    left open.

Local label names come back prefixed with the sheet path ("/L_IN"), hence the
normalisation.  Power-symbol pins (refs starting with '#') are ignored.

    python3 tools/check_netlist.py        # exit 0 = netlist matches intent
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kicadlib as kl
import gen_sch

SCH = os.path.join(gen_sch.ROOT, gen_sch.PROJECT + ".kicad_sch")


def export(path):
    subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format",
                    "kicadsexpr", "-o", path, SCH], check=True,
                   capture_output=True)
    return open(path, encoding="utf-8").read()


def parse_nets(text):
    tree = kl.parse(text)[0]
    nets, open_pins = {}, set()
    for net in kl.kids(kl.kid(tree, "nets"), "net"):
        name = kl.unquote(kl.kid(net, "name")[1]).lstrip("/")
        nodes = {(kl.unquote(kl.kid(n, "ref")[1]),
                  kl.unquote(kl.kid(n, "pin")[1]))
                 for n in kl.kids(net, "node")
                 if not kl.unquote(kl.kid(n, "ref")[1]).startswith("#")}
        if name.startswith("unconnected-"):
            open_pins |= nodes
        else:
            nets[name] = nodes
    return nets, open_pins


def expected_open():
    """Pins deliberately left open: declared nc, 'NO' entries, and every pin
    the library marks as a no-connect type."""
    out = set()
    for part in gen_sch.PARTS:
        lib = part["lib"]
        wired = {p for p, n in part["pins"].items() if n != "NO"}
        out |= {(part["ref"], p) for p in gen_sch.nc_pins(part)}
        for g in kl.pins_geo(kl.flatten(lib)[0]):
            if g["etype"] == "no_connect":
                out.add((part["ref"], g["num"]))
    return out


def main():
    with tempfile.TemporaryDirectory() as td:
        got, open_pins = parse_nets(export(os.path.join(td, "net.net")))
    want = {net: {(r, p) for r, p in members if not r.startswith("FLG")}
            for net, members in gen_sch.nets().items()}

    bad = 0
    for net in sorted(set(want) | set(got)):
        w, g = want.get(net), got.get(net)
        if w is None:
            print(f"EXTRA NET   {net}: {sorted(g)}")
            bad += 1
        elif g is None:
            print(f"MISSING NET {net}: expected {sorted(w)}")
            bad += 1
        elif w != g:
            print(f"MISMATCH    {net}: missing {sorted(w - g)} "
                  f"extra {sorted(g - w)}")
            bad += 1
    exp_open = expected_open()
    if exp_open != open_pins:
        print(f"UNCONNECTED: expected {sorted(exp_open - open_pins)} "
              f"surprising {sorted(open_pins - exp_open)}")
        bad += 1
    print(f"{len(want)} intended nets, {len(got)} exported, "
          f"{len(exp_open)} deliberately open pins, {bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

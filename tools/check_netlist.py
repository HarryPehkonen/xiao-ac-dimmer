#!/usr/bin/env python3
"""Gate: the exported netlist must equal the intended netlist.

Exports a kicadsexpr netlist with kicad-cli and compares it against
gen_sch.nets():

  * every intended net exists with exactly the intended pins,
  * no net exists that the intent does not name (no accidental shorts),
  * the only single-pin "unconnected-..." nets are the pins deliberately
    left open,
  * every pin of the two XIAO socket rows carries the *module's* pin name
    (gen_sch.XIAO_ROWS: D0..D6 on J1, VBUS..D7 on J2).  That is what makes the
    schematic self-documenting rather than commented: the netlist says J1.2 is
    D1/GPIO3, the trigger, and this asserts it.  A generic 1x07 symbol -- what
    these rows used to be -- exports "Pin_2" and fails here.

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


def export(path, sch=SCH):
    subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format",
                    "kicadsexpr", "-o", path, sch], check=True,
                   capture_output=True)
    return open(path, encoding="utf-8").read()


def parse_nets(text):
    """({net: {(ref, pin)}}, {(ref, pin)} open, {(ref, pin): pin name})."""
    tree = kl.parse(text)[0]
    nets, open_pins, funcs = {}, set(), {}
    for net in kl.kids(kl.kid(tree, "nets"), "net"):
        name = kl.unquote(kl.kid(net, "name")[1]).lstrip("/")
        nodes = set()
        for n in kl.kids(net, "node"):
            ref = kl.unquote(kl.kid(n, "ref")[1])
            pin = kl.unquote(kl.kid(n, "pin")[1])
            fn = kl.kid(n, "pinfunction")
            if fn is not None:
                funcs[(ref, pin)] = kl.unquote(fn[1])
            if not ref.startswith("#"):
                nodes.add((ref, pin))
        if name.startswith("unconnected-"):
            open_pins |= nodes
        else:
            nets[name] = nodes
    return nets, open_pins, funcs


def expected_open():
    """Pins deliberately left open: declared nc, 'NO' entries, and every pin
    the library marks as a no-connect type."""
    out = set()
    for part in gen_sch.PARTS:
        lib = part["lib"]
        out |= {(part["ref"], p) for p in gen_sch.nc_pins(part)}
        for g in kl.pins_geo(kl.flatten(lib)[0]):
            if g["etype"] == "no_connect":
                out.add((part["ref"], g["num"]))
    return out


def run(sch=SCH):
    """(problem count, report lines) for the schematic at sch."""
    with tempfile.TemporaryDirectory() as td:
        got, open_pins, funcs = parse_nets(export(os.path.join(td, "net.net"),
                                                  sch))
    want = {net: {(r, p) for r, p in members if not r.startswith("FLG")}
            for net, members in gen_sch.nets().items()}

    bad, lines = 0, []
    for net in sorted(set(want) | set(got)):
        w, g = want.get(net), got.get(net)
        if w is None:
            lines.append(f"EXTRA NET   {net}: {sorted(g)}")
            bad += 1
        elif g is None:
            lines.append(f"MISSING NET {net}: expected {sorted(w)}")
            bad += 1
        elif w != g:
            lines.append(f"MISMATCH    {net}: missing {sorted(w - g)} "
                         f"extra {sorted(g - w)}")
            bad += 1
    exp_open = expected_open()
    if exp_open != open_pins:
        lines.append(f"UNCONNECTED: expected {sorted(exp_open - open_pins)} "
                     f"surprising {sorted(open_pins - exp_open)}")
        bad += 1

    # The socket rows' pin names, as the schematic's symbols give them out.
    names = gen_sch.xiao_pin_names()
    for ref_pin in sorted(names):
        got_name = funcs.get(ref_pin)
        if got_name != names[ref_pin]:
            lines.append(f"PIN NAME    {ref_pin[0]}.{ref_pin[1]}: the netlist "
                         f"says '{got_name}', the module's pin is "
                         f"'{names[ref_pin]}'")
            bad += 1
    rows = {row["ref"] for row in gen_sch.XIAO_ROWS}
    exported = {k for k in funcs if k[0] in rows}
    if exported and exported != set(names):
        lines.append(f"PIN SET     the socket rows export {sorted(exported)}, "
                     f"the module's 14 pins are {sorted(names)}")
        bad += 1

    lines.append(f"{len(want)} intended nets, {len(got)} exported, "
                 f"{len(exp_open)} deliberately open pins, "
                 f"{len(names)} socket pin names checked, {bad} problem(s)")
    return bad, lines


def main():
    bad, lines = run()
    for line in lines:
        print(line)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

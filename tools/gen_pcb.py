#!/usr/bin/env python3
"""Generate the PCB for the XIAO AC dimmer board (headless, via pcbnew).

Nets come from the *schematic* (kicad-cli netlist export), so the board can
never disagree with the design about connectivity.  Placement and routing are
explicit tables here, the same way the schematic is generated.

    python3 tools/gen_pcb.py            # write xiao-ac-dimmer.kicad_pcb
    python3 tools/gen_pcb.py --dump     # print pad coordinates per net
"""
import os
import subprocess
import sys
import tempfile

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_sch
import kicadlib as kl

ROOT = gen_sch.ROOT
PROJECT = gen_sch.PROJECT
BOARD = os.path.join(ROOT, PROJECT + ".kicad_pcb")
SCH = os.path.join(ROOT, PROJECT + ".kicad_sch")
MM = pcbnew.FromMM


def mm(v):
    return round(float(v), 3)


# ---------------------------------------------------------------- placement --
# Board is 130 x 90 mm in three vertical zones.  Mains lives on the left;
# PS1, U2 and U1 straddle the middle zone because their own creepage is the
# barrier; logic sits on the right.  Parts are *packed* inside their zone
# (row by row, no overlaps by construction) rather than hand-placed, so the
# same script keeps working when the part list changes.
GROUPS = [
    # mains: cord in -> fuse -> protection -> snubber -> cord out, then the
    # triac last so its gate ends up beside the gate resistor's own zone
    ((4, 6, 50, 90), [("J3", 0), ("F1", 0), ("MOV1", 0), ("RS1", 0),
                      ("CS1", 0), ("J4", 0), ("Q1", 0)]),
    # the mains-side resistors, in their own strip against the barrier: R4 is
    # the triac gate resistor (U2 pin 4 -> Q1 gate), R1/R2 are the zero-cross
    # legs into U1 pins 1/2.  Packing them in with the mains parts is what
    # walled the gate cluster in.
    ((52, 6, 58, 90), [("R4", 90), ("R1", 90), ("R2", 90)]),
    # parts that straddle the barrier, U2 first so its logic pins face the
    # logic-side cluster and its mains pins face the resistor strip
    ((62, 6, 96, 90), [("U2", 180), ("U1", 180), ("PS1", 0)]),
    # logic-side resistors and the 5 V rail, right of the barrier
    ((100, 6, 126, 90), [("R3", 90), ("R5", 0), ("D5", 0), ("C1", 0),
                         ("C2", 0)]),
    ((130, 6, 147, 90), [("J1", 0), ("J2", 0)]),
]
MARGIN = 2.5          # mm between packed parts
BOARD_W, BOARD_H = 150.0, 95.0


def place_all(fps):
    """Pack each group's parts into rows inside its zone.  Returns
    {ref: (x, y, rot)} for reporting."""
    out = {}
    for (x0, y0, x1, y1), parts in GROUPS:
        cx, cy, rowh = x0, y0, 0.0
        for ref, rot in parts:
            fp = fps[ref]
            fp.SetOrientationDegrees(rot)
            bb = fp.GetBoundingBox(False, False)
            pos = fp.GetPosition()
            w = pcbnew.ToMM(bb.GetWidth())
            h = pcbnew.ToMM(bb.GetHeight())
            if cx + w > x1 and cx > x0:
                cx, cy, rowh = x0, cy + rowh + MARGIN, 0.0
            fp.SetPosition(pcbnew.VECTOR2I(
                MM(cx - (pcbnew.ToMM(bb.GetX()) - pcbnew.ToMM(pos.x))),
                MM(cy - (pcbnew.ToMM(bb.GetY()) - pcbnew.ToMM(pos.y)))))
            out[ref] = (round(cx, 2), round(cy, 2), rot)
            cx += w + MARGIN
            rowh = max(rowh, h)
    return out


# Nets routed on the bottom layer; everything else uses the top.
BOTTOM = {"N_AC", "L_IN", "L_FUSED", "LOAD_L", "SNUB_MID"}

EDGE = [(0, 0), (BOARD_W, 0), (BOARD_W, BOARD_H), (0, BOARD_H), (0, 0)]


def schematic_nets():
    """{net: [(ref, pad)]} straight from the verified schematic."""
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "net.net")
        subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format",
                        "kicadsexpr", "-o", out, SCH], check=True,
                       capture_output=True)
        text = open(out, encoding="utf-8").read()
    tree = kl.parse(text)[0]
    nets = {}
    for net in kl.kids(kl.kid(tree, "nets"), "net"):
        name = kl.unquote(kl.kid(net, "name")[1]).lstrip("/")
        if name.startswith("unconnected-"):
            continue
        nets[name] = [(kl.unquote(kl.kid(n, "ref")[1]),
                       kl.unquote(kl.kid(n, "pin")[1]))
                      for n in kl.kids(net, "node")
                      if not kl.unquote(kl.kid(n, "ref")[1]).startswith("#")]
    return nets


def deoverlap_fields(fps, step=0.75, tries=40):
    """Nudge visible silk text so no two reference/value fields overlap.

    AutoPlaceFields() puts each part's reference somewhere near the part but
    knows nothing about the neighbour it lands on, which is how J4's reference
    ended up on MOV1's.  Walk the fields in reference order and slide each one
    down until its bounding box is clear, giving up after a bounded number of
    tries so a genuinely crowded area still terminates.
    """
    placed = []
    for ref in sorted(fps):
        fp = fps[ref]
        fields = [f for f in (fp.Reference(), fp.Value())
                  if f.IsVisible()
                  and f.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)]
        for f in fields:
            bb = f.GetBoundingBox()
            n = 0
            while any(bb.Intersects(pb) for _r, pb in placed) and n < tries:
                f.Move(pcbnew.VECTOR2I(0, pcbnew.FromMM(step)))
                bb = f.GetBoundingBox()
                n += 1
            placed.append((ref, bb))


def build():
    board = pcbnew.BOARD()
    board.SetFileName(BOARD)

    # --- nets, taken from the schematic -----------------------------------
    netitems = {}
    for name in schematic_nets():
        item = pcbnew.NETINFO_ITEM(board, name)
        board.Add(item)
        netitems[name] = item

    # --- footprints --------------------------------------------------------
    by_ref, fps = {}, {}
    for part in gen_sch.PARTS:
        if not part["fp"]:
            continue
        lib, name = part["fp"].split(":")
        src = os.path.join("/usr/share/kicad/footprints", lib + ".pretty")
        fp = pcbnew.FootprintLoad(src, name)
        if fp is None:
            raise SystemExit(f"cannot load footprint {part['fp']}")
        fp.SetReference(part["ref"])
        fp.SetValue(part["val"])
        fps[part["ref"]] = fp
    placed = place_all(fps)
    for ref, fp in fps.items():
        try:
            fp.AutoPlaceFields()          # keeps reference text off the
        except AttributeError:            # neighbouring part's silk
            pass
    deoverlap_fields(fps)                 # ...and this catches what it misses
    for ref, fp in fps.items():
        board.Add(fp)
        by_ref[ref] = fp
    if "--dump" in sys.argv or "-v" in sys.argv:
        for ref, (x, y, rot) in sorted(placed.items()):
            print(f"  {ref:<5} at ({x:>6}, {y:>6}) rot {rot}")

    # --- assign pads to their nets -----------------------------------------
    for net, members in schematic_nets().items():
        for ref, pad in members:
            fp = by_ref.get(ref)
            if fp is None:
                continue
            for p in fp.Pads():
                if p.GetNumber() == pad:
                    p.SetNet(netitems[net])

    # --- board outline -----------------------------------------------------
    for (x0, y0), (x1, y1) in zip(EDGE, EDGE[1:]):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pcbnew.VECTOR2I(MM(x0), MM(y0)))
        seg.SetEnd(pcbnew.VECTOR2I(MM(x1), MM(y1)))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(MM(0.15))
        board.Add(seg)

    if "--no-route" not in sys.argv:
        import route as router
        router.route(board, netitems, schematic_nets())
    write_rules()
    pcbnew.SaveBoard(BOARD, board)
    return board


M = ("L_IN|L_FUSED|N_AC|LOAD_L|SNUB_MID|ZCD_A|ZCD_B|MOC_MT2|TRIAC_G")
RULES = f'''(version 1)
(rule "mains isolation barrier (mains vs logic, 3 mm)"
\t(constraint clearance (min 3mm))
\t(condition "(A.NetName =~ '^/?({M})$' && !(B.NetName =~ '^/?({M})$')) || (B.NetName =~ '^/?({M})$' && !(A.NetName =~ '^/?({M})$'))"))
(rule "mains track width"
\t(constraint track_width (min 1mm))
\t(condition "A.NetName =~ '^/?({M})$'"))
'''


def write_rules():
    """Custom DRC rules: the isolation barrier as machine-checked geometry."""
    path = os.path.join(ROOT, PROJECT + ".kicad_dru")
    open(path, "w").write(RULES)
    print(f"wrote {os.path.basename(path)} (3 mm mains clearance rule)")


def dump():
    board = pcbnew.LoadBoard(BOARD)
    print(f"{'net':<10} {'ref.pad':<10} x      y")
    for net in sorted(schematic_nets()):
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetname().lstrip("/") == net:
                    p = pad.GetPosition()
                    print(f"{net:<10} {fp.GetReference() + '.' + pad.GetNumber():<10} "
                          f"{mm(pcbnew.ToMM(p.x)):<6} {mm(pcbnew.ToMM(p.y))}")


if __name__ == "__main__":
    if "--dump" in sys.argv:
        dump()
    else:
        build()
        print(f"wrote {BOARD}")
        fp_count = len(list(pcbnew.LoadBoard(BOARD).GetFootprints()))
        print(f"  {fp_count} footprints, {len(schematic_nets())} nets, "
              f"board outline 130 x 90 mm")

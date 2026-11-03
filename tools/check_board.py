#!/usr/bin/env python3
"""Gate: the saved board passes DRC and honours the rules DRC cannot state.

    python3 tools/check_board.py        # exit 0 = clean

Two halves:

1. `kicad-cli pcb drc` on the committed board -- shorts, clearance, the 3 mm
   mains barrier rule, hole-to-hole, silk overlap.
2. Plain geometry on the same board, for what DRC has no rule for: every
   footprint id must name its library, the four M3 mounting holes must be
   where and what the design says with the copper keepout actually empty, and
   the XIAO socket pair must be the shape that accepts the module -- 14 holes,
   two rows of 7, 2.54 mm pitch, the module's own 15.24 mm row separation, pin
   1 at the right end, and the module's body clear of everything else.

The second half exists because of the socket: every footprint on that board was
individually valid, the netlist was right, 16/16 nets routed and DRC was clean
-- and the module could not physically seat, because nothing compared the *pair*
to the module it has to accept.  Mating-interface geometry is invisible to ERC
and DRC; assertion is the only defence.

The board is read from disk, not regenerated, so this gates what would be
fabricated.
"""
import os
import re
import subprocess
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_pcb
import gen_sch

BOARD = gen_pcb.BOARD
POS_TOL = 0.01                  # mm, when checking a hole against its place


def drc():
    """Run kicad-cli DRC on the board.  Returns 0 when clean."""
    report = "/tmp/drc.rpt"
    r = subprocess.run(["kicad-cli", "pcb", "drc", "--exit-code-violations",
                        "-o", report, BOARD], capture_output=True, text=True)
    text = open(report, encoding="utf-8").read() if os.path.exists(report) else ""

    kinds = {}
    for kind, sev in re.findall(
            r"^\[([a-z_]+)\]:[^\n]*\n[^\n]*;\s*(error|warning)\s*$", text, re.M):
        kinds[(kind, sev)] = kinds.get((kind, sev), 0) + 1
    errs = sum(n for (k, s), n in kinds.items() if s == "error")
    warns = sum(n for (k, s), n in kinds.items() if s == "warning")

    for (kind, sev), n in sorted(kinds.items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {sev:<8} {kind:<28} {n}")
    print(f"{errs} error(s), {warns} warning(s)")

    # show the first few distinct complaints so a failure is actionable
    if r.returncode != 0:
        seen = set()
        for block in re.split(r"\n(?=\[)", text):
            m = re.match(r"\[([a-z_]+)\]:", block)
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                print("  --- example ---")
                print("  " + block.strip().replace("\n", "\n  ")[:400])
                if len(seen) >= 3:
                    break
    return 1 if r.returncode != 0 else 0


# -------------------------------------------------------------- geometry ----
def _to_mm(v):
    return pcbnew.ToMM(v)


def _is_mount(fp):
    return str(fp.GetFPID().GetLibItemName()).startswith("MountingHole")


def _outline_mm(board):
    """The board outline as (x0, y0, x1, y1) in mm.

    Built from the edge segments' own endpoints: GetBoardEdgesBoundingBox()
    inflates by half the outline line width, which is what made every hole
    measure 0.075 mm further from its edge than it is.
    """
    xs, ys = [], []
    for d in board.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts:
            continue
        for v in (d.GetStart(), d.GetEnd()):
            xs.append(_to_mm(v.x))
            ys.append(_to_mm(v.y))
    if not xs:
        raise SystemExit("no board outline on the board")
    return min(xs), min(ys), max(xs), max(ys)


def _edge_distance_mm(outline, x, y):
    """Distance from (x, y) to the nearest point of the board outline."""
    x0, y0, x1, y1 = outline
    return min(x - x0, x1 - x, y - y0, y1 - y)


def _copper_clearance_mm(board, hx, hy):
    """Closest copper edge to the hole centre, in mm.

    Pads, tracks and vias, each via KiCad's own effective shape, so a rotated
    pad is measured rather than guessed at.  The mounting footprints' own
    non-plated pads *are* the holes and are skipped.  This board carries no
    copper zones; a zone added later would not be seen here.
    """
    pt = pcbnew.VECTOR2I(pcbnew.FromMM(hx), pcbnew.FromMM(hy))
    worst = None
    for track in board.GetTracks():
        d = _to_mm(track.GetEffectiveShape(pcbnew.F_Cu).Distance(pt))
        worst = d if worst is None else min(worst, d)
    for fp in board.GetFootprints():
        if _is_mount(fp):
            continue
        for pad in fp.Pads():
            d = _to_mm(pad.GetEffectiveShape(pcbnew.F_Cu).Distance(pt))
            worst = d if worst is None else min(worst, d)
    return worst


def geometry(board):
    """Board rules DRC has no rule for.  Returns a list of failures."""
    bad = []

    # --- every footprint id names its library -----------------------------
    # gen_pcb.py loads footprints by name and the geometry is embedded in the
    # board, so fab is unaffected by a missing nickname.  But with the link
    # dropped, "update footprint from library" silently never works -- and that
    # is the whole workflow for swapping a part.
    fps = list(board.GetFootprints())
    for fp in fps:
        fpid = fp.GetFPID()
        if not str(fpid.GetLibNickname()):
            bad.append(f"{fp.GetReference()}: footprint id "
                       f"'{str(fpid.GetLibItemName())}' carries no library "
                       f"nickname, so 'update footprint from library' cannot "
                       f"work")

    # --- the mounting holes are what the design says ----------------------
    want = gen_pcb.MOUNT_KEEPOUT / 2.0          # copper-free radius, mm
    outline = _outline_mm(board)
    by_ref = {fp.GetReference(): fp for fp in fps}
    found = [fp for fp in fps if _is_mount(fp)]
    if len(found) != len(gen_pcb.MOUNTING):
        bad.append(f"{len(found)} mounting hole footprint(s) on the board, "
                   f"{len(gen_pcb.MOUNTING)} in gen_pcb.MOUNTING")

    for ref, wx, wy in gen_pcb.MOUNTING:
        fp = by_ref.get(ref)
        if fp is None:
            bad.append(f"{ref}: no footprint with the reference the mounting "
                       f"table names")
            continue
        p = fp.GetPosition()
        x, y = _to_mm(p.x), _to_mm(p.y)
        if abs(x - wx) > POS_TOL or abs(y - wy) > POS_TOL:
            bad.append(f"{ref}: at ({x:g}, {y:g}) mm, table says "
                       f"({wx:g}, {wy:g})")
        edge = _edge_distance_mm(outline, x, y)
        if abs(edge - gen_pcb.MOUNT_INSET) > POS_TOL:
            bad.append(f"{ref}: {edge:.2f} mm from the nearest board edge, "
                       f"spec is {gen_pcb.MOUNT_INSET:g} mm inset")

        pads = list(fp.Pads())
        if len(pads) != 1:
            bad.append(f"{ref}: {len(pads)} pads, a mounting hole is one "
                       f"non-plated hole")
        for pad in pads:
            if pad.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
                bad.append(f"{ref}: pad is not non-plated (NPTH), so it has "
                           f"an annular ring under the screw head")
            drill = _to_mm(pad.GetDrillSize().x)
            if abs(drill - gen_pcb.MOUNT_DRILL) > POS_TOL:
                bad.append(f"{ref}: {drill:g} mm drill, spec is "
                           f"{gen_pcb.MOUNT_DRILL:g} mm")
            if pad.GetNetCode() != 0 or str(pad.GetNetname()):
                bad.append(f"{ref}: pad is on net '{str(pad.GetNetname())}', "
                           f"a mounting hole must be isolated")

        clear = _copper_clearance_mm(board, x, y)
        if clear is None:
            bad.append(f"{ref}: no copper on the board at all?")
        elif clear < want:
            bad.append(f"{ref}: copper comes within {clear:.3f} mm of the hole "
                       f"centre, the {gen_pcb.MOUNT_KEEPOUT:g} mm keepout "
                       f"allows {want:g} mm")

    if not bad:
        print(f"  {len(fps)} footprint id(s) carry a library nickname; "
              f"{len(found)} mounting hole(s) {gen_pcb.MOUNT_DRILL:g} mm "
              f"NPTH, isolated, {gen_pcb.MOUNT_KEEPOUT:g} mm keepout clear")
    return bad


# -------------------------------------------------------- the module socket --
def _extent_mm(fp):
    """(x0, y0, x1, y1) mm of a footprint: its courtyard, or its body."""
    cy = fp.GetCourtyard(pcbnew.F_CrtYd)
    box = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False, False)
    x0, y0 = _to_mm(box.GetX()), _to_mm(box.GetY())
    return (x0, y0, x0 + _to_mm(box.GetWidth()), y0 + _to_mm(box.GetHeight()))


def xiao_socket(board):
    """The socket pair must accept the module.  Returns a list of failures.

    This is the half of the board no checker can see.  Every footprint here can
    be individually valid -- the right pin count, the right pitch, a clean
    netlist, ERC and DRC both quiet -- and the pair still not hold a XIAO.  That
    is what happened: the two rows sat 6.1 mm apart for a module that needs
    15.24 mm, and nothing in the pipeline compared the pair to the module it has
    to accept.  So the pair is measured here, against the module's own geometry
    in gen_pcb.XIAO, and against the schematic's pin assignment -- which is what
    makes "pad 2 is the trigger" true rather than a comment.

    Called by geometry(); returns [] on the honest board.
    """
    bad = []
    spec = gen_pcb.XIAO
    fps = list(board.GetFootprints())
    by_ref = {fp.GetReference(): fp for fp in fps}

    rows = []
    for ref in spec["rows"]:
        fp = by_ref.get(ref)
        if fp is None:
            bad.append(f"{ref}: no footprint with the reference the XIAO "
                       f"table names")
        rows.append(fp)
    if any(fp is None for fp in rows):
        return bad

    # --- one object, not two loose headers --------------------------------
    groups = [g for g in board.Groups() if g.GetName() == gen_pcb.XIAO_GROUP]
    if len(groups) != 1:
        bad.append(f"{gen_pcb.XIAO_GROUP}: {len(groups)} group(s) with that "
                   f"name on the board, 1 expected -- the two rows are one "
                   f"part, not two headers a packer can move apart")
    else:
        members = sorted(i.GetReference() for i in groups[0].GetItems()
                         if isinstance(i, pcbnew.FOOTPRINT))
        if members != sorted(spec["rows"]):
            bad.append(f"{gen_pcb.XIAO_GROUP}: holds {members}, the socket "
                       f"rows are {sorted(spec['rows'])}")

    # --- the 14 holes, two straight rows ----------------------------------
    cols, pad1_y = {}, {}
    for ref, fp in zip(spec["rows"], rows):
        if not fp.IsLocked():
            bad.append(f"{ref}: not locked.  The two rows are one placement; "
                       f"anything free to move them can drift the module apart")
        pads = list(fp.Pads())
        if len(pads) != spec["per_row"]:
            bad.append(f"{ref}: {len(pads)} pad(s), a XIAO row is "
                       f"{spec['per_row']} (7 + 7 = the module's 14)")
            continue
        want_nums = sorted(str(i + 1) for i in range(spec["per_row"]))
        nums = sorted(p.GetNumber() for p in pads)
        if nums != want_nums:
            bad.append(f"{ref}: pads numbered {nums}, a XIAO row is "
                       f"{want_nums[0]}..{want_nums[-1]}")
        for pad in pads:
            if pad.GetAttribute() != pcbnew.PAD_ATTRIB_PTH:
                bad.append(f"{ref}.{pad.GetNumber()}: not a through-hole pad; "
                           f"the module's pins need a hole to go in")
            drill = _to_mm(pad.GetDrillSize().x)
            if abs(drill - spec["hole"]) > POS_TOL:
                bad.append(f"{ref}.{pad.GetNumber()}: {drill:g} mm hole, spec "
                           f"is {spec['hole']:g} mm (the module's own pins are "
                           f"drilled {spec['pin_drill']:g} mm)")

        pts = sorted((round(_to_mm(p.GetPosition().y), 4),
                      round(_to_mm(p.GetPosition().x), 4), p.GetNumber())
                     for p in pads)
        xs = sorted({p[1] for p in pts})
        if len(xs) != 1:
            bad.append(f"{ref}: pads at x = {xs} mm: a XIAO row is one "
                       f"straight column along y")
            continue
        cols[ref] = xs[0]
        ys = [p[0] for p in pts]
        spans = sorted({round(b - a, 4) for a, b in zip(ys, ys[1:])})
        off = [s for s in spans if abs(s - spec["pitch"]) > POS_TOL]
        if off:
            bad.append(f"{ref}: {off} mm between pads, the module's pitch is "
                       f"{spec['pitch']:g} mm")
        if abs((ys[-1] - ys[0]) - (spec["per_row"] - 1) * spec["pitch"]) > POS_TOL:
            bad.append(f"{ref}: the row spans {ys[-1] - ys[0]:g} mm, "
                       f"{spec['per_row']} pads at {spec['pitch']:g} mm span "
                       f"{(spec['per_row'] - 1) * spec['pitch']:g} mm")
        # pin 1 is the end the module's USB-C connector is at.  Both rows have
        # their pin 1 at that end (D0 and 5V/VBUS are the two pins nearest the
        # USB-C connector), so pad 1 at the *far* end is a row in the other way
        # round -- the board would fire the wrong pin and nothing else would
        # notice.
        pad1 = next((p for p in pads if p.GetNumber() == "1"), None)
        if pad1 is not None:
            y1 = _to_mm(pad1.GetPosition().y)
            pad1_y[ref] = y1
            if abs(y1 - ys[0]) > POS_TOL:
                bad.append(f"{ref}: pad 1 is at y={y1:g}, the row's near end is "
                           f"y={ys[0]:g} -- the row is in the other way round "
                           f"(pad 1 goes at the USB-C end)")

    # --- the pair's separation, and which side each row is on -------------
    if len(cols) == 2:
        left, right = spec["rows"]
        sep = abs(cols[right] - cols[left])
        if abs(sep - spec["row_sep"]) > POS_TOL:
            bad.append(f"{left}/{right}: the two rows are {sep:g} mm apart, a "
                       f"XIAO needs {spec['row_sep']:g} mm (Seeed's own "
                       f"footprint: pads at y = +/-7.620 mm).  Pitch and pin "
                       f"count can both be right and the module still not seat")
        if cols[left] > cols[right]:
            bad.append(f"{left}: at x={cols[left]:g}, right of {right} at "
                       f"x={cols[right]:g} -- {left} is the module's left "
                       f"column (D0..D6) with the USB-C end up, {right} the "
                       f"right one (5V, GND, 3V3, D10, D9, D8, D7)")
    if len(pad1_y) == 2:
        dy = abs(pad1_y[spec["rows"][0]] - pad1_y[spec["rows"][1]])
        if dy > POS_TOL:
            bad.append(f"pin 1 of the two rows is {dy:g} mm apart along the "
                       f"module: one row is reversed relative to the other")

    # --- the module envelope ----------------------------------------------
    want = gen_pcb.xiao_envelope()
    rects = [d for d in board.GetDrawings()
             if d.GetLayer() == pcbnew.F_CrtYd
             and d.GetShape() == pcbnew.SHAPE_T_RECT]
    if len(rects) != 1:
        bad.append(f"module envelope: {len(rects)} rectangle(s) on F.CrtYd, 1 "
                   f"expected (the XIAO body has to have somewhere to sit)")
    else:
        a, b = rects[0].GetStart(), rects[0].GetEnd()
        got = (min(_to_mm(a.x), _to_mm(b.x)), min(_to_mm(a.y), _to_mm(b.y)),
               max(_to_mm(a.x), _to_mm(b.x)), max(_to_mm(a.y), _to_mm(b.y)))
        if max(abs(g - w) for g, w in zip(got, want)) > POS_TOL:
            bad.append(f"module envelope: the F.CrtYd rectangle is "
                       f"({got[0]:g}, {got[1]:g})-({got[2]:g}, {got[3]:g}) mm, "
                       f"the module body is "
                       f"({want[0]:g}, {want[1]:g})-({want[2]:g}, {want[3]:g}) mm")

    ex0, ey0, ex1, ey1 = want
    for fp in fps:
        if fp.GetReference() in spec["rows"]:
            continue
        x0, y0, x1, y1 = _extent_mm(fp)
        if x0 < ex1 and x1 > ex0 and y0 < ey1 and y1 > ey0:
            bad.append(f"module envelope: {fp.GetReference()} reaches to "
                       f"({x0:g}, {y0:g})-({x1:g}, {y1:g}) mm, inside the "
                       f"({ex0:g}, {ey0:g})-({ex1:g}, {ey1:g}) mm the module "
                       f"body occupies")

    # --- the pin assignment the geometry has to agree with -----------------
    # A row could be the right length, correctly pitched and 15.24 mm from its
    # neighbour, and still be wired the other way round.  The schematic names
    # the nets per pin, so this is where "pad 2 is D1, the triac trigger" stops
    # being a comment and becomes a check.
    for ref, fp in zip(spec["rows"], rows):
        part = next(p for p in gen_sch.PARTS if p["ref"] == ref)
        for pad in fp.Pads():
            want_net = part["pins"].get(pad.GetNumber(), "")
            got_net = pad.GetNetname().lstrip("/")
            if got_net != want_net:
                bad.append(f"{ref}.{pad.GetNumber()}: on net '{got_net}', the "
                           f"intent for this pin is '{want_net}'")
    if not bad:
        sep = abs(cols[spec["rows"][1]] - cols[spec["rows"][0]]) if len(cols) == 2 else 0
        print(f"  XIAO socket {gen_pcb.XIAO_GROUP}: {len(spec['rows'])} rows of "
              f"{spec['per_row']} holes, {spec['pitch']:g} mm pitch, "
              f"{sep:g} mm apart, pin 1 at the USB-C end, "
              f"envelope {ex1 - ex0:g} x {ey1 - ey0:g} mm clear")
    return bad


def main():
    board = pcbnew.LoadBoard(BOARD)
    problems = geometry(board) + xiao_socket(board)
    rc = drc()
    if problems:
        print(f"{len(problems)} board problem(s) DRC cannot see:")
        for p in problems:
            print(f"  FAIL  {p}")
    return 1 if (problems or rc) else 0


if __name__ == "__main__":
    sys.exit(main())

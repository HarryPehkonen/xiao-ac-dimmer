#!/usr/bin/env python3
"""Gate: the saved board passes DRC and honours the rules DRC cannot state.

    python3 tools/check_board.py        # exit 0 = clean

Two halves:

1. `kicad-cli pcb drc` on the committed board -- shorts, clearance, the 3 mm
   mains barrier rule, hole-to-hole, silk overlap.
2. Plain geometry on the same board, for what DRC has no rule for: every
   footprint id must name its library, and the four M3 mounting holes must be
   where and what the design says, with the copper keepout actually empty.

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


def main():
    board = pcbnew.LoadBoard(BOARD)
    problems = geometry(board)
    rc = drc()
    if problems:
        print(f"{len(problems)} board problem(s) DRC cannot see:")
        for p in problems:
            print(f"  FAIL  {p}")
    return 1 if (problems or rc) else 0


if __name__ == "__main__":
    sys.exit(main())

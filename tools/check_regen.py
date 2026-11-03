#!/usr/bin/env python3
"""Gate: the committed board is the one the generator produces.

    python3 tools/check_regen.py        # exit 0 = the board matches

The schematic has this gate (`ci.sh` hashes it together with
`symbols/xiao-ac.kicad_sym`, regenerates, compares hashes).  The board could
not use the same trick, and DRC alone does not close the hole: a hand-edited
`xiao-ac-dimmer.kicad_pcb` (a track moved, a pad renumbered, the mains barrier
quietly narrowed by a tenth of a millimetre) can be perfectly DRC-clean.

The board file is *not* byte-reproducible, so this cannot be a hash compare:

  - pcbnew stamps a fresh UUID on every footprint, pad, track and text it
    creates, and
  - KiCad writes those items back in its own order.

What *is* reproducible is the board itself: placement and every copper item.
Measured across runs and against the committed board: 24/24 footprints (the 20
parts and the 4 mounting holes) and 502/502 tracks+vias identical.  So this
gate regenerates the board in a throwaway copy of the tools and compares that
digest.

Scope, stated honestly: this catches the board disagreeing with the generator.
It says nothing about whether the design is right, and nothing about safety.
"""
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_pcb

HOME = gen_pcb.ROOT
PY = "/usr/bin/python3"         # pcbnew lives in the system interpreter


def digest(path):
    """Everything about the board a person would have to have edited."""
    import pcbnew

    board = pcbnew.LoadBoard(path)
    if board is None:
        raise SystemExit(f"cannot load {path}")
    fps = []
    for fp in board.GetFootprints():
        p = fp.GetPosition()
        fps.append((fp.GetReference(), fp.GetValue(),
                    round(pcbnew.ToMM(p.x), 3), round(pcbnew.ToMM(p.y), 3),
                    round(fp.GetOrientationDegrees(), 3), fp.GetLayer()))
    copper = []
    for t in board.GetTracks():
        a, e = t.GetStart(), t.GetEnd()
        w = 0.0 if t.GetClass() == "PCB_VIA" else pcbnew.ToMM(t.GetWidth())
        copper.append((t.GetNetname().lstrip("/"), t.GetClass(), t.GetLayer(),
                       round(pcbnew.ToMM(a.x), 3), round(pcbnew.ToMM(a.y), 3),
                       round(pcbnew.ToMM(e.x), 3), round(pcbnew.ToMM(e.y), 3),
                       round(w, 3)))
    return sorted(fps), sorted(copper)


def main():
    committed = os.path.join(HOME, gen_pcb.PROJECT + ".kicad_pcb")
    if not os.path.exists(committed):
        raise SystemExit(f"FAIL: no {os.path.basename(committed)} to check")
    want = digest(committed)

    tmp = tempfile.mkdtemp(prefix="dimmer-regen-")
    try:
        shutil.copytree(os.path.join(HOME, "tools"), os.path.join(tmp, "tools"))
        for tool in ("gen_sch.py", "gen_pcb.py"):
            r = subprocess.run([PY, os.path.join("tools", tool)],
                               cwd=tmp, capture_output=True, text=True)
            if r.returncode != 0:
                print(r.stdout[-2000:])
                print(r.stderr[-2000:])
                raise SystemExit(f"FAIL: {tool} exited {r.returncode}")
        got = digest(os.path.join(tmp, gen_pcb.PROJECT + ".kicad_pcb"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for label, a, b in (("footprints", want[0], got[0]),
                        ("copper", want[1], got[1])):
        if a == b:
            print(f"  {label}: {len(a)} identical")
            continue
        print(f"FAIL: {label} differ -- the committed board is not what the "
              f"generator produces")
        only_committed = [i for i in a if i not in b]
        only_generator = [i for i in b if i not in a]
        for i in only_committed[:5]:
            print(f"  only in the committed board: {i}")
        for i in only_generator[:5]:
            print(f"  only in the generated board: {i}")
        print("  regenerate with /usr/bin/python3 tools/gen_pcb.py, review the "
              "diff, and commit the board -- do not hand-edit it")
        return 1
    print("OK: committed board == generated board")
    return 0


if __name__ == "__main__":
    sys.exit(main())

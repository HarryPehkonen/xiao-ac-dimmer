# PCB status — partial, and honest about it

The board is **generated**, not drawn: `tools/gen_pcb.py` places the parts,
`tools/route.py` routes them, `tools/check_board.py` gates the result.
Nets are taken from the schematic netlist export, so the board cannot disagree
with the schematic about connectivity.

## What works

- 20 footprints placed by zone packer (mains / barrier / logic) on a
  150 × 95 mm outline. No courtyard overlaps.
- 16 nets assigned from `kicad-cli sch export netlist`.
- `xiao-ac-dimmer.kicad_dru` carries the isolation barrier as a machine-checked
  rule: **3 mm clearance between mains nets and everything else**, 1 mm minimum
  mains track width.
- DRC: **no shorts, no clearance violations** where copper exists — the 3 mm
  barrier rule is satisfied. Mains tracks are 1.5 mm wide on both layers.

## What does not work yet

- **3 of 16 nets are unrouted**: `TRIAC_G` (Q1 gate → R4), `MOC_MT2`
  (R4 → U2 pin 4), `MOC_A` (R3 → U2 pin 1). All three sit in the cluster
  between the barrier and the mains zone, where the 3 mm barrier keepout closes
  the available channel. DRC reports 3 `unconnected_items` errors.
- 4 `hole_to_hole` warnings from vias landing near pads.
- 2 `silk_overlap` warnings no longer appear after `AutoPlaceFields()`, but the
  check still runs.

**This board is not fab-ready and must not be ordered.** `check_board.py` is
deliberately NOT part of `tools/ci.sh` while it fails — wiring a failing gate
into CI teaches you to ignore CI.

## Next steps, in order

1. Move R4 and R3 out of the packed mains/logic rows so that cluster has room,
   or route those three connections from explicit coordinates.
2. Add a via-to-pad keepout in the router (vias currently only avoid pads by a
   2-cell margin at the path ends).
3. Then, and only then: gerbers + drill export, a gerber-viewer eyeball, and
   the DFM check with the fab's rules.

## Safety status (unchanged, and not affected by any of the above)

DRC clean would still not be a safety certificate. The barrier is geometry the
tool checks; the parts, the creepage standard, the enclosure, the GFCI test and
the 500 V insulation test are what make it survivable. See DESIGN.md.

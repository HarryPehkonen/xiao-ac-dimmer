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

- **2 of 16 nets are unrouted**: `LOAD_L` (J4 → Q1 pin 2) and `ZCD_OUT`
  (R5 → U1 pin 5). Both targets are pads inside a 2.54 mm pin column, where the
  pad's own neighbours veto most of its opening (measured: 19–22 of 49 cells)
  and the survivors do not reach open space on either layer. DRC reports 3
  `unconnected_items` errors. `TRIAC_G`, `MOC_MT2` and `MOC_A` failed here too
  and now route.
- 2 `hole_to_hole` warnings from vias landing near pads; 1 `silk_overlap`
  warning that `AutoPlaceFields()` did not clear.
- Routing quality: segments merged into single runs (**410**, down from 2,161 —
  one track per 0.5 mm grid step was pure bloat). No shorts, no clearance
  violations.
- The router's clearance floor is **measured, not guessed**: at 0.25 mm margin
  DRC reported 12 shorts against `no-net` pads (a diagonal run passes ~0.4 mm
  closer to a pad than the cell-centre model predicts); 0.5 mm gave none; 0.4 mm
  is the floor that still lets dense pin columns route.

**This board is not fab-ready and must not be ordered.** `check_board.py` is
deliberately NOT part of `tools/ci.sh` while it fails — wiring a failing gate
into CI teaches you to ignore CI.

## Next steps, in order

1. Get `LOAD_L` and `ZCD_OUT` home. Both are pads buried in a pin column, so the
   options are: widen those pads' openings (open a short channel along the pin
   row, not just perpendicular to it), or route those two from explicit
   coordinates. Placement is no longer the constraint — the pads are reachable,
   the opening is what fails.
2. Clear the 2 `hole_to_hole` and 1 `silk_overlap` warnings.
3. Then, and only then: gerbers + drill export, a gerber-viewer eyeball, and the
   DFM check with the fab's rules. Wire `check_board.py` into `tools/ci.sh` on
   the same commit that makes it pass.

## Safety status (unchanged, and not affected by any of the above)

DRC clean would still not be a safety certificate. The barrier is geometry the
tool checks; the parts, the creepage standard, the enclosure, the GFCI test and
the 500 V insulation test are what make it survivable. See DESIGN.md.

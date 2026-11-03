# PCB status

The board is **generated**, not drawn: `tools/gen_pcb.py` places the parts,
`tools/route.py` routes them, `tools/check_board.py` gates the result.
Nets are taken from the schematic netlist export, so the board cannot disagree
with the schematic about connectivity.

## What works

- 20 footprints placed by zone packer (mains / barrier / logic) on a
  150 × 95 mm outline. No courtyard overlaps.
- 16 nets assigned from `kicad-cli sch export netlist`, and **16/16 routed**
  (489 track segments, 15 vias).
- `xiao-ac-dimmer.kicad_dru` carries the isolation barrier as a machine-checked
  rule: **3 mm clearance between mains nets and everything else**, 1 mm minimum
  mains track width.
- DRC: **0 errors, 0 warnings** — no shorts, no clearance violations, no
  `hole_to_hole`, no silk overlaps. The 3 mm barrier rule is satisfied. Mains
  tracks are 1.5 mm wide on both layers.
- `check_board.py` is wired into `tools/ci.sh`, so a board that stops routing
  or gains a violation fails the same gate as a stale schematic.

## How the last two nets were closed

`LOAD_L` (J4.1 → Q1.2) and `ZCD_OUT` (R5.2 → U1.5) both land on pads buried in
a 2.54 mm pin column. The pads' own neighbours veto most of each opening
(measured 22 and 19 of 49 cells), and by the time those two nets were reached
earlier routes had walled the survivors in on the layers that mattered.
Two changes, neither touching a clearance constant:

1. **Route the most constrained pad first.** `route()` used to order nets by
   length, which let a long net seal the very pad it had to reach. The order is
   now by the static free-cell count of each net's tightest pad
   (`_free_score`), descending, so a pad with almost no room is claimed before
   the copper that would close it exists.
2. **De-overlap the silkscreen fields.** `AutoPlaceFields()` left J4's
   reference sitting on MOV1's, the last DRC warning. `deoverlap_fields()` in
   `gen_pcb.py` slides any visible reference/value field down until its
   bounding box is clear.

The router's per-pad escape spoke was also extracted into the pure function
`_escape_dirs()` (perpendicular to the nearest neighbour) so its geometry is
unit-tested.

## Routing quality

- Segments merged into single runs (`_to_segments`), not one track per 0.5 mm
  grid step: 489 segments instead of 2,161 — no file bloat, fast DRC, a board
  that can be read.
- The router's clearance floor is **measured, not guessed**: at 0.25 mm margin
  DRC reported 12 shorts against `no-net` pads (a diagonal run passes ~0.4 mm
  closer to a pad than the cell-centre model predicts); 0.5 mm gave none; 0.4 mm
  is the floor that still lets dense pin columns route.

## Next steps

1. Gerbers + drill export, a gerber-viewer eyeball, and the DFM check with the
   fab's rules.
2. Schematic parity (`kicad-cli pcb drc --schematic-parity`) in the board gate,
   so a board/schematic drift is caught, not just netlist drift.

## Safety status (unchanged, and not affected by any of the above)

DRC clean is still not a safety certificate. The barrier is geometry the tool
checks; the parts, the creepage standard, the enclosure, the GFCI test and the
500 V insulation test are what make it survivable. See DESIGN.md.

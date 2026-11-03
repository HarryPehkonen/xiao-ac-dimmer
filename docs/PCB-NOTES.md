# PCB status

The board is **generated**, not drawn: `tools/gen_pcb.py` places the parts,
`tools/route.py` routes them, `tools/check_board.py` gates the result.
Nets are taken from the schematic netlist export, so the board cannot disagree
with the schematic about connectivity.

## What works

- 24 footprints on a 150 × 95 mm outline: 20 parts placed by the zone packer
  (mains / barrier / logic) plus the 4 M3 mounting holes. No courtyard overlaps.
- 16 nets assigned from `kicad-cli sch export netlist`, and **16/16 routed**
  (491 track segments, 15 vias).
- `xiao-ac-dimmer.kicad_dru` carries the isolation barrier as a machine-checked
  rule: **3 mm clearance between mains nets and everything else**, 1 mm minimum
  mains track width.
- DRC: **0 errors, 0 warnings** — no shorts, no clearance violations, no
  `hole_to_hole`, no silk overlaps. The 3 mm barrier rule is satisfied. Mains
  tracks are 1.5 mm wide on both layers.
- Every footprint id carries its **library nickname** (`Resistor_THT:R_Axial_…`,
  not `R_Axial_…`), so "update footprint from library" works — the workflow any
  part swap needs. `FootprintLoad()` was dropping it on placement.
- `check_board.py` is wired into `tools/ci.sh`, so a board that stops routing,
  gains a violation, loses a footprint's library link, or loses a mounting
  hole's copper keepout fails the same gate as a stale schematic.

## Mounting holes

Four M3 clearance holes, one per corner, 5 mm inset from both edges:
`MountingHole:MountingHole_3.2mm_M3`, a non-plated 3.2 mm hole with no pad and
no net. Each owns a **6 mm-diameter copper-free disc** — no track, via or pad
edge within 3 mm of the hole centre — because an M3 screw head sits over it.
They carry `exclude_from_bom` / `exclude_from_pos_files`.

Two things fell out of adding them:

1. **A keepout has to be inflated by the copper that will pass it.** Blocking
   3 mm of cell centres is not enough: the router blocks *cell centres*, so a
   1.5 mm mains track laid on the last free cell still puts its edge 0.75 mm
   inside the disc. Measured before the fix: `LOAD_L` came within 2.86 mm of H1.
   `MOUNT_BLOCK_R` is the spec radius plus half the widest track plus the
   half-cell diagonal.
2. **The corner courtyards forced placement in.** Each hole's courtyard reaches
   3.45 mm back from its centre, so the packing strips now start 9 mm from the
   top edge and stop 9 mm from the bottom instead of hugging the outline. Not
   one net lost its path: still 16/16, still 0 errors and 0 warnings.

## How the last two nets were closed

`LOAD_L` (J4.1 → Q1.2) and `ZCD_OUT` (R5.2 → U1.5) both land on pads buried in
a 2.54 mm pin column. The pads' own neighbours veto most of each opening
(measured 22 and 19 of 49 cells), and by the time those two nets were reached
earlier routes had walled the survivors in on the layers that mattered.
Two changes, neither touching a clearance constant:

1. **Order the nets by free space, most room first.** `route()` used to order
   nets by length, which is what let a late net find its pad already walled in.
   The key is the static free-cell count of each net's tightest pad
   (`_free_score`), **descending** — and that sign is measured, not reasoned:
   flipping it to claim the tightest pad first (the ordering the name suggests,
   and what this note claimed) leaves **14/16 nets with 6 DRC errors** —
   `MOC_A` and `ZCD_OUT` lose their paths and four shorts appear.
2. **De-overlap the silkscreen fields.** `AutoPlaceFields()` left J4's
   reference sitting on MOV1's, the last DRC warning. `deoverlap_fields()` in
   `gen_pcb.py` slides any visible reference/value field down until its
   bounding box is clear.

The router's per-pad escape spoke was also extracted into the pure function
`_escape_dirs()` (perpendicular to the nearest neighbour) so its geometry is
unit-tested.

## Routing quality

- Segments merged into single runs (`_to_segments`), not one track per 0.5 mm
  grid step: 491 segments instead of 2,161 — no file bloat, fast DRC, a board
  that can be read.
- The router's clearance floor is **measured, not guessed**: at 0.25 mm margin
  DRC reported 12 shorts against `no-net` pads (a diagonal run passes ~0.4 mm
  closer to a pad than the cell-centre model predicts); 0.5 mm gave none; 0.4 mm
  is the floor that still lets dense pin columns route.

## Why the board has no "matches the generator" hash check

The schematic has one (`tools/ci.sh` hashes it, regenerates, compares hashes).
The board cannot, and that is not a defect in the gate: KiCad gives every item a
fresh UUID on each run and writes footprints in an order derived from those
UUIDs, so two runs of the same generator never produce the same bytes. Two runs
were compared structurally instead — 24 footprints, 506 track/via items and the
outline, each as a set — and they are identical, so the **geometry** is
reproducible even though the file is not. `tools/tests/test_board_routes.py` is
the board's equivalent: it regenerates into a temp directory (keeping the
`.kicad_dru` beside it, so the 3 mm barrier is part of the check) and runs DRC
on the result.

## Next steps

1. Gerbers + drill export, a gerber-viewer eyeball, and the DFM check with the
   fab's rules.
2. Schematic parity (`kicad-cli pcb drc --schematic-parity`) in the board gate,
   so a board/schematic drift is caught, not just netlist drift.

## Safety status (unchanged, and not affected by any of the above)

DRC clean is still not a safety certificate. The barrier is geometry the tool
checks; the parts, the creepage standard, the enclosure, the GFCI test and the
500 V insulation test are what make it survivable. See DESIGN.md.

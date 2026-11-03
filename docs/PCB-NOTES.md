# PCB status

The board is **generated**, not drawn: `tools/gen_pcb.py` places the parts,
`tools/route.py` routes them, `tools/check_board.py` gates the result.
Nets are taken from the schematic netlist export, so the board cannot disagree
with the schematic about connectivity.

## What works

- 24 footprints on a 150 × 57 mm outline: **18 parts placed by the zone packer**
  (mains / barrier / logic), the **XIAO socket block** (J1 + J2, one locked
  group — see "The XIAO socket" below), and the 4 M3 mounting holes. No
  courtyard overlaps. The outline is sized to the packed parts (they span
  41.9 mm; the old 95 mm board was 40% dead space along one edge) — see
  "Board size" below.
- 16 nets assigned from `kicad-cli sch export netlist`, and **16/16 routed**
  (487 track segments, 15 vias).
- `xiao-ac-dimmer.kicad_dru` carries the isolation barrier as a machine-checked
  rule: **3 mm clearance between mains nets and everything else**, 1 mm minimum
  mains track width.
- DRC: **0 errors, 0 warnings** — no shorts, no clearance violations, no
  `hole_to_hole`, no silk overlaps. The 3 mm barrier rule is satisfied. Mains
  tracks are 1.5 mm wide on both layers.
- Every footprint id carries its **library nickname** (`Resistor_THT:R_Axial_…`,
  not `R_Axial_…`), so "update footprint from library" works — the workflow any
  part swap needs. `FootprintLoad()` was dropping it on placement.
- `check_board.py` is wired into `tools/ci.sh` **together with its own tests**
  (`pytest tools/tests`), so a board that stops routing, gains a violation,
  loses a footprint's library link, loses a mounting hole's copper keepout, or
  stops being able to accept its XIAO fails the same gate as a stale schematic.
  The socket rules are the ones ERC and DRC cannot express — see "The XIAO
  socket".

## The XIAO socket (and the class of bug it exposed)

Harri caught this from a render, not from a tool: `J1`/`J2` were two *independent*
generic 1×7 sockets 6.1 mm apart on a 150 × 57 mm board. Pitch ✓, 7 + 7 = 14
pins ✓, 16/16 nets routed, ERC clean, DRC clean — **and the module cannot
physically seat**, because a XIAO needs the two rows **15.24 mm** apart.

Nothing in the pipeline was wrong. Every footprint was individually valid and
the nets were correct; **the mating interface only exists in the pair**, and no
ERC or DRC rule looks at a pair. A generic 1×7 socket has no idea it is half of
a module socket. Assertion against the mating part's own numbers is the only
defence, which is why `check_board.py` now measures the pair.

**The number, and where it comes from.** Not from the issue: from the mating
part's own KiCad footprint — `OPL_Kicad_Library`,
`Seeed Studio XIAO Series Library/XIAO-ESP32-C3-DIP.kicad_mod`
(github.com/Seeed-Studio/OPL_Kicad_Library). Its two rows put their pads at
**y = ±7.620 mm → 15.24 mm** apart, 7 pads per row on 2.54 mm, module body
**17.8 mm** across the rows and 21.0 mm along them. That agrees with the wiki's
21 × 17.5 mm drawing to the tenth of a millimetre, so 15.24 mm is the number the
gate asserts; `XIAO["row_sep"]` carries it with the source in a comment.

What the fix changes in `tools/gen_pcb.py`:

- **`XIAO`** is the module's geometry in one table: `row1_x`, `pin1_y`, `pitch`,
  `per_row`, `row_sep`, `width`, and the module's overhang at each end
  (`usb_overhang` 2.921 mm, `tail` 2.794 mm), the socket's own drill (`hole`
  1.0 mm) and the drill Seeed uses for the module's pins (`pin_drill` 0.889 mm).
- **`place_xiao()`** places *both* rows from that one entry and locks them. It
  moves each row's **pad 1** onto the wanted point rather than setting the
  footprint's position, which would silently assume the footprint's origin is
  its pad 1 — true for KiCad's `PinSocket_1x07` today, and exactly the kind of
  assumption this change exists to stop making.
- The two rows are **one `XIAO_SOCKET` PCB_GROUP**: one part, 14 holes, one
  placement. The packer never sees them (they are excluded from the strips), so
  it cannot choose their separation again.
- **`xiao_envelope()`** is the 17.8 × 20.955 mm area the module body occupies
  over the sockets, drawn on **F.CrtYd**. It is a keepout in both directions:
  the gate fails if any other footprint reaches into it, and the packer refuses
  to place a part there.

**Which physical side is which.** Both rows' pad 1 is at the **USB-C end**
(y = 13 mm, towards the top edge), because the module's pin 1 is at its USB-C
end. Looking at the board from the top with the USB-C connector up: **J1
(x = 130 mm) is the module's left column, D0…D6** top to bottom, nearest the
mains section, and **J2 (x = 145.24 mm) is its right column — 5V, GND, 3V3,
D10, D9, D8, D7** (Seeed's front pinout diagram). The schematic says the same
thing in the symbol itself now, not only in a `val` field — see "The socket
symbol" below. The two pins that matter are on J1: **pad 2 = D1/GPIO3 =
`GATE_DRV`** (the triac trigger) and **pad 3 = D2/GPIO4 = `ZCD_OUT`**
(zero-cross). Both would have gone to the wrong pin / the wrong end had a row
been reversed, which is now a gate failure.

**It cost board area, and the board did not have to grow.** The socket block
takes 19 mm of the right-hand strip (x 128.72 → 146.52, 3.48 mm from the
outline) instead of the 7.5 mm two loose sockets used. The card expected the
150 mm board to have to grow; repacking the four strips absorbed it instead —
but this is a **new routing**, not the old one carried over: 487 track segments
instead of 491, so 16/16 nets and 0 errors / 0 warnings are re-measured claims
(see "How the last two nets were closed" for the retry that was needed).

## The socket symbol (the same defect, one layer up)

`J1`/`J2` were generic `Conn_01x07` symbols as well, so the *schematic* said
`Pin_2` where the board meant `D1`, and the only thing joining the two was a
comment — the same shape of defect as the rows 6.1 mm apart: every tool
passed, and a reviewer had to take the pinout on trust. ERC cannot see it
either; a renamed pin moves no net.

Each row now has its own symbol whose 7 pins carry the module's own names:
`D0..D6` on J1, `VBUS, GND, 3V3_OUT, D10, D9/BOOT, D8, D7` on J2, pin 1 at the
USB-C end on both. The exported netlist carries them
(`(node (ref "J1") (pin "2") (pinfunction "D1") ...)`), and
`tools/check_netlist.py` asserts all 14 against `gen_sch.XIAO_ROWS`.
`tools/tests/test_pin_names.py` breaks that three ways and requires the report:
a pin renamed (nothing else in the pipeline notices), the rows put back to
`Pin_1..Pin_7`, and a row renumbered (both this check and the net membership
check fire). Each case calls the netlist gate on a *doctored copy* of the
schematic on purpose: `ci.sh`'s first check regenerates the committed file, so
a hand-edit there is caught as staleness before the netlist gate sees it.

**Where the symbol lives.** `symbols/xiao-ac.kicad_sym`, written by
`gen_sch.py` from `XIAO_ROWS` and read back through `kicadlib` exactly like a
stock library — so the file and the copy the schematic caches in `lib_symbols`
are the one definition. `sym-lib-table` points at it through `${KIPRJMOD}`,
`tools/ci.sh` hashes it together with the schematic (a stale copy fails the
gate), and ERC's "library symbol issues" check compares cache against library
as a second line of defence.

**Why not Seeed's own symbol?** They publish one for the C3 in
`OPL_Kicad_Library`, and it is the *SMD* variant: 22 pins — the 14 side pins
plus 8 castellated pads (`EN`, `VBAT`, `MTDI/MTDO/MTMS/MTCK`) — numbered 1..14
continuously across the two columns, ascending from the far end on the second
one. This board carries the module's *DIP* socket: 14 holes, two `1x07`
footprints each numbered 1..7 with pin 1 at the USB-C end. Their symbol would
put eight pins in the netlist with no hole to go into and renumber both rows;
and their DIP symbols (RP2350, nRF54LM20A) number the columns the same 1..14
way, so there is no per-row-numbered 14-pin symbol to borrow. The **names** are
theirs; the symbol is this project's.

The mapping, for anyone who has to convert between the two numberings. The
module's own numbers are Seeed's: the D0..D6 column is 1..7 from the USB-C end,
the other column is 14..8 from that end — which is what both their DIP and SMD
footprints for the C3 do, checked pad by pad against each other:

| socket | module pin | name |
| --- | --- | --- |
| J1.1 | 1 | D0 |
| J1.2 | 2 | D1 (GPIO3) — `GATE_DRV`, the triac trigger |
| J1.3 | 3 | D2 (GPIO4) — `ZCD_OUT`, the zero-cross input |
| J1.4 .. J1.7 | 4..7 | D3, D4, D5, D6 |
| J2.1 | 14 | VBUS (the 5 V feed) |
| J2.2 | 13 | GND |
| J2.3 | 12 | 3V3_OUT |
| J2.4 | 11 | D10 |
| J2.5 | 10 | D9/BOOT |
| J2.6 | 9 | D8 |
| J2.7 | 8 | D7 |

The symbol is drawn to the module's geometry where that is meaningful: 2.54 mm
pin pitch (Seeed's symbol spreads the same 7 pins over 3.81 mm to buy label
room) and a body as long as the module — 20.955 mm, i.e. 2.921 mm past pin 1
and 2.794 mm past pin 7, the overhangs `gen_pcb.XIAO` measures the courtyard
with — with the pin-1 end marked `USB-C end` at the top of both. It is 10.16 mm
*across*, which is not the module's 17.8 mm: the symbol is one row of holes,
not the module, and the description property says so.

**The board did not change.** Regenerated and compared item by item against the
committed board: 24 footprints, 500 copper items, 5 drawings, one group —
identical apart from J1/J2's value field, which now names the module
(`XIAO-ESP32C3 left D0..D6`). 16/16 nets routed, DRC 0 errors / 0 warnings,
ERC 0 violations.

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
   3.45 mm back from its centre, so the packing strips start 9 mm from the top
   edge instead of hugging the outline. Not one net lost its path: still 16/16,
   still 0 errors and 0 warnings.

## Board size

**150 × 57 mm = 85.5 cm²**, down from **150 × 95 mm = 142.5 cm²**. (The
150.2 × 95.2 mm / 142.9 cm² in the original report is the same board measured
including the outline's own 0.15 mm line width, which is what a viewer draws;
the segment endpoints give 150 × 95 mm.)

The 20 parts span 41.9 mm vertically (y 9 → 50.9 mm) and 135.7 mm horizontally,
so the 95 mm board was carrying a **54.3 mm band of empty board along the bottom
edge** — the outline had been raised from 90 mm to 95 mm *while the router was
failing*, and it stayed after the router was fixed. Nothing flagged it, because
the outline is an input to the pipeline, not a result of it.

The height is now sized around the packed parts (`BOARD_H` in `tools/gen_pcb.py`
carries the reasoning):

- **Width stays 150 mm.** The parts span 135.7 mm, already ~10% over.
- **Height 57 mm.** 9 mm above the first row (the top mounting holes' courtyard
  needs it), 41.9 mm of parts, 6.1 mm below the last row — **15% spare on the
  bottom side**, inside the 10-20% tolerance, rather than the 130% it was.
- **The floor is 52 mm.** Shrinking removes the router's spare corridors, so the
  smaller board is a *new* routing claim, not an inherited one: 52, 53, 54, 55,
  56, 57 and 58 mm were each regenerated end-to-end and each reported 16/16 nets
  routed with 0 DRC errors and 0 warnings. 52 mm is still the lowest *clean*
  height. 51 mm now routes 16/16 as well, but DRC reports 2
  `copper_edge_clearance` errors there (`N_AC` passing 0.25 mm from the outline),
  so the copper would have to move before the board could go lower; from 50 mm
  down the router reports its own failure — `no path PS1.2 -> R2.1 [cells=49
  pad-veto=0 copper-veto L0=20/L1=20 free L0=29/L1=29]` at 50 mm, 15/16 nets
  from 50 to 44 mm and 14/16 at 43 mm and below.
- 51 mm *used to* raise `IndexError: bytearray index out of range` from
  `_open()` instead of reporting anything — a pad's escape spoke walking off the
  bottom of the grid. That was a router robustness bug, not a design limit:
  `Grid.is_blocked()` indexed the bytearray with any cell it was handed, and now
  refuses an off-grid cell the way `unblock()`, `block()` and `inside()` already
  did. `tools/tests/test_route_open.py` pins it (a pad within `cr` of an edge, no
  exception). The fix moves no copper: regenerate this board and it is item for
  item the committed one.
- **Nothing had to be rerouted.** At 57 mm the router lays the *same* 506 copper
  items as at 95 mm — compared item by item (net, layer, width, both endpoints):
  identical. Only the outline and the two lower mounting holes moved. So the
  smaller board is not a routing gamble that happened to pass; it carries the
  routing that was already gated.
- **Unchanged at the new height:** the mounting holes (5 mm inset, 3.2 mm NPTH,
  isolated, 6 mm copper-free disc) and their keepouts — `check_board.py` measures
  them on the finished board, not on the design table — and the packing strips,
  which are bounded in x only and simply run as deep as the parts do.

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

The ordering key was not enough on its own once the XIAO socket block moved the
parts (see "The XIAO socket"). `GND` and `ZCD_OUT` come out **equal** on the
free-cell key, so the tie-break decides which of them wins the corridor; the
span tie-break (`min` pad-to-pad hop, now the last key) then walls `ZCD_OUT`
out: one pass finishes **15/16** with `no path R5.2 -> U1.5`.

So `route()` now makes up to `ATTEMPTS` (4) passes and, after a pass with
failures, **promotes the nets that failed to the front of the next ordering**
(`_promote()`), keeping the relative order inside each group so a retry is
deterministic. Measured on this board: pass 1 = 15/16, pass 2 = 16/16, and the
result prints which ordering it took (`routed 16/16 nets (order 2)`), so a
board that needs the retry says so instead of hiding it. `route()` also reports
`attempts` for the tests. The copper of a failed pass is thrown away rather than
left on the board, and the retry re-lays it — which
`tools/tests/test_board_gate.py :: test_a_rerouted_board_is_still_clean` then
puts through DRC, because "the first ordering failed" is not something DRC
would have noticed.

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

One pipeline side effect to know about: **`pcbnew.SaveBoard()` rewrites the
`.kicad_pro`** when the board is written back into its own project directory —
KiCad expands the repo's 27-line minimal project into its full default project
file (~285 lines, `3dviewports`, `design_settings` and all). Measured
2026-11-03 with KiCad 9: `LoadBoard` + `SaveBoard` in a *temp* directory leaves
the project alone; saving into the directory that holds the project rewrites it.
Nothing in it changes this board (DRC and `check_board.py` are clean with either
version), so regenerating and then reverting the project file keeps the diff
readable: `git checkout -- xiao-ac-dimmer.kicad_pro`.

The schematic has a hash check (`tools/ci.sh` hashes it together with
`symbols/xiao-ac.kicad_sym`, regenerates, compares hashes).
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

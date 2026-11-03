# xiao-ac-dimmer

One-channel inline AC dimmer for a Seeed Studio XIAO ESP32C3 (or any XIAO on the
same 14-pad footprint). Mains cord in one end, lamp socket out the other, and the
triac dims whatever is plugged in between them. Plug-in bench/room scale — not
house wiring.

**Status: generated schematic and PCB, both machine-checked. The board is
150 × 57 mm (85.5 cm²), 16/16 nets routed, DRC clean — 0 errors, 0 warnings.**

## The schematic is generated

`xiao-ac-dimmer.kicad_sch` is written by `tools/gen_sch.py`. The circuit lives
there as a table of parts and nets; the generator draws each symbol, a stub wire
per pin and a label naming that pin's net. Open the result in KiCad 9 to review
it like any other schematic.

That indirection is deliberate: a hand-drawn schematic cannot be verified, and
a generated one can (see Gates).

## Gates

```sh
./tools/ci.sh
```

1. **Generator == committed file.** Regenerating leaves `xiao-ac-dimmer.kicad_sch`
   and `symbols/xiao-ac.kicad_sym` byte-identical, so neither the committed
   schematic nor the symbol library it draws `J1`/`J2` from is ever stale.
2. **Netlist == intent.** `tools/check_netlist.py` exports a netlist with
   `kicad-cli` and asserts it against the intended netlist: every net present
   with exactly the intended pins, no unintended net at all (that would be a
   short), only the deliberately open pins reported unconnected, and every pin
   of the two XIAO socket rows carrying the *module's* pin name — `D0..D6` on
   `J1`, `VBUS, GND, 3V3_OUT, D10, D9/BOOT, D8, D7` on `J2` — so the schematic
   and its netlist say which pin is which instead of leaving it to a comment.
   This gate caught a rotated-symbol pin swap that would have fitted the
   Schottky diode backwards.
3. **ERC clean.** `kicad-cli sch erc` reports 0 violations.
4. **Board DRC clean.** `tools/check_board.py` — 0 errors, 0 warnings, including
   the 3 mm mains/logic clearance rule in `xiao-ac-dimmer.kicad_dru`. The same
   check asserts the rules DRC has no rule for: every footprint id names its
   library, the four M3 mounting holes are where the design says with an empty
   6 mm copper keepout, and the two socket rows are one mating interface that a
   XIAO actually fits (15.24 mm apart — the defect that got through ERC, DRC,
   the netlist and the router).
5. **Board == generator.** `tools/check_regen.py` regenerates the board in a
   throwaway copy of the tools and compares every footprint and every copper
   item against the committed board — 24 footprints (20 parts + 4 mounting
   holes) and 502 tracks+vias today.
   The board file is not *byte*-reproducible (pcbnew stamps fresh UUIDs and
   writes items in its own order), so this compares geometry, which is the part
   a person would have had to edit. `docs/PCB-NOTES.md` has the measurement and
   the two sabotage runs.
6. **The gates' own tests.** `tools/tests/test_board_gate.py` breaks each rule
   that check 4 enforces — a moved or renamed hole, a track or pad inside the
   keepout, a hole tied to a net, a plated or undersized hole, a footprint id
   with no library nickname, a missing hole, a socket row moved or respaced —
   and asserts `check_board.py` reports it. `tools/tests/test_pin_names.py` does
   the same for check 2's pin names: a renamed pin, the rows back to
   `Pin_1..Pin_7`, a renumbered row. `test_board_routes.py` regenerates and runs
   DRC; `test_route_geometry.py` and `test_route_open.py` pin the router's
   geometry and its off-grid edge case. A rule that has never been seen to fail
   is not a gate.

## Circuit in one paragraph

Cord hot goes through a 3.15 A fuse, then feeds an MOV, the HLK-PM01's AC input
and the triac's A1; neutral runs straight through to the outlet, unswitched.
The HLK's isolated 5 V reaches the XIAO's VBUS pad through a Schottky diode. An
H11AA1 across the mains (47 k in each leg) pulls D2 low at every zero crossing;
firmware then fires the MOC3021 random-phase opto from D1 through 220 Ω, which
triggers the BTA16-600B through 1 k, with a 100 Ω + 100 nF snubber across it.
Part-by-part reasoning, including what is deliberately *not* proven: DESIGN.md.

## Bill of materials (all through-hole)

| Ref | Part | Note |
| --- | --- | --- |
| PS1 | HLK-PM01 | isolated 100–240 VAC → 5 V 0.6 A |
| F1 | 5×20 mm fuse clip + 3.15 A slow-blow | hot leg only |
| MOV1 | S14K150 varistor | 150 VAC rating |
| Q1 | BTA16-600B | TO-220, small heatsink |
| U2 | MOC3021M | *random-phase* opto-triac, DIP-6 |
| U1 | H11AA1 | AC-input optocoupler, DIP-6 |
| D5 | SS14 | Schottky, VBUS feed |
| R1, R2 | 47 k 1/4 W | ZCD legs (≈1.3 mA rms each) |
| R3 | 220 Ω | MOC LED from 3.3 V (≈9 mA) |
| R4 | 1 k | triac gate |
| R5 | 10 k | ZCD pull-up to 3V3 |
| RS1 | 100 Ω | snubber |
| C1 | 470 µF 16 V | 5 V bulk |
| C2 | 100 nF | XIAO decoupling |
| CS1 | 100 nF 400 V film | snubber |
| J1, J2 | 2 × 1×07 2.54 mm socket | XIAO: J1 = D0..D6, J2 = 5V..D7 |
| J3, J4 | 2-pole 5.08 mm screw terminal | cord in / lamp out |

## Safety — read before powering anything up

- The hot is switched and fused; the neutral is never broken and never fused
  on its own.
- Never work on it live. First power-up on a GFCI/RCD outlet. **Never flash
  firmware with mains connected.**
- The layout slice will enforce ≥3 mm clearance across the barrier with a
  routed isolation slot. Do not shrink it to make the board smaller.
- 3.15 A suits a ~60 W lamp. A larger load needs the fuse, the copper and the
  triac's heatsinking rechecked.
- Only dimmable LED bulbs dim; some need a bleeder, some buzz, some refuse
  below ~20 %. That is measured on the bench, not simulated.
- Nothing here is a safety certification. The insulation barrier is the
  HLK-PM01, the optos and the layout, and the enclosure is yours.

## Files

```
xiao-ac-dimmer.kicad_sch   generated schematic (the reviewable design)
xiao-ac-dimmer.kicad_pcb   generated board -- never hand-edit
xiao-ac-dimmer.kicad_dru   the 3 mm mains/logic barrier and the 1 mm mains width
xiao-ac-dimmer.kicad_pro   project + netclass settings
symbols/xiao-ac.kicad_sym  the socket rows' symbols, pins named D0..D6 / VBUS..D7
sym-lib-table fp-lib-table so the libraries resolve without global config
tools/kicadlib.py          s-expression reader, symbol flattening (extends)
tools/gen_sch.py           the circuit + schematic generator
tools/gen_pcb.py           placement + board generator
tools/route.py             the maze router
tools/check_netlist.py     gate: exported netlist == intended netlist (and pin names)
tools/check_board.py       gate: kicad-cli pcb drc + the rules DRC cannot express
tools/check_regen.py       gate: committed board == generated board (geometry)
tools/ci.sh                the gate
tools/probe_libs.py        diagnostic: does each embedded symbol load?
tools/tests/               the gates' own tests (every rule, seen to fail)
sim/                       ngspice decks and measured results
docs/PCB-NOTES.md          board status, and what the router needed
DESIGN.md                  engineering decisions and open items
BOM.md                     sourcing and mechanical notes
```

## Requirements

KiCad 9 (`kicad-cli`) and ngspice 44:

```sh
sudo apt-get install kicad kicad-symbols kicad-footprints ngspice
```

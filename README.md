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
xiao-ac-dimmer.kicad_pro   project + netclass settings
symbols/xiao-ac.kicad_sym  the socket rows' symbols, pins named D0..D6 / VBUS..D7
sym-lib-table fp-lib-table so the libraries resolve without global config
tools/kicadlib.py          s-expression reader, symbol flattening (extends)
tools/gen_sch.py           the circuit + schematic generator
tools/check_netlist.py     gate: exported netlist == intended netlist (and pin names)
tools/ci.sh                the gate
tools/probe_libs.py        diagnostic: does each embedded symbol load?
sim/                       ngspice decks and measured results
DESIGN.md                  engineering decisions and open items
```

## Requirements

KiCad 9 (`kicad-cli`) and ngspice 44:

```sh
sudo apt-get install kicad kicad-symbols kicad-footprints ngspice
```

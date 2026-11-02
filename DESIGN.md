# Design notes

One-channel inline dimmer. Cord in (J3), lamp out (J4), a XIAO ESP32C3 in two
7-pin sockets, a phase-control triac in the hot leg.

## Decisions, and why

1. **One channel per box.** An inline module is one plug in, one socket out. Two
   independently switched circuits in the same inline box would need either two
   cords or a shared-neutral multi-conductor cable that no normal plug/socket
   pair can terminate. Two lights = two boxes.
2. **Mains-fed, not USB-fed.** An inline box lives at the lamp with no USB
   available, but L and N are right there, so an HLK-PM01 (isolated 100–240 VAC
   → 5 V 0.6 A) sits on the board.
3. **Schottky (D5) between the HLK's +5 V and the XIAO's VBUS pad.** Seeed's own
   documentation requires a diode when VBUS is fed externally; it also stops the
   supply fighting USB. 470 µF bulk (C1) covers the LED-strip-free but still
   capacitive-ish load and keeps the HLK out of current limit.
4. **Hot-only switching, neutral continuous.** The fuse and the triac are both
   in the hot leg; the neutral runs from J3 to J4 untouched. Nothing on the logic
   side is ever referenced to mains.
5. **MOC3021M, not MOC3063.** Random-phase opto-triac. A zero-cross part
   (MOC3063/MOC3062) *waits for the zero crossing* to turn on, which is exactly
   what a phase dimmer must not do — it can only switch whole half-cycles.
   **This corrects what I said in chat earlier** (I named MOC3063 before the
   dimming requirement was settled).
6. **0.5 W-ish ZCD: 47 k in each leg.** The H11AA1 takes ~1.3 mA rms through the
   two 47 k resistors (≈0.08 W each), pulling its phototransistor on for roughly
   the middle of each half-cycle and giving a clean edge at each zero crossing.
   R5 (10 k) pulls the collector up to 3V3. Signal lands on D2 (GPIO4, interrupt
   capable); the trigger is on D1 (GPIO3).
7. **Pin choice.** D1/D2 on a XIAO ESP32C3 are GPIO3/GPIO4. Avoid GPIO2, 8 and 9
   — they are strapping pins, and a load on them can stop the board booting or
   entering the bootloader.
8. **XIAO socket order** (Seeed front-pinout diagram, verified against the
   vendor image): left column top→bottom = D0, D1, D2, D3, D4, D5, D6; right
   column top→bottom = 5V (VBUS), GND, 3V3, D10, D9, D8, D7. Confirm against the
   physical board with a continuity check before applying power — getting 5 V and
   GND the wrong way round kills the XIAO.
9. **Snubber 100 Ω + 100 nF/400 V across the triac.** Damps the commutation
   dv/dt into loads that look capacitive or inductive at 60 Hz; without it cheap
   LED drivers can latch the triac on. CS1 sits on the mains side.
10. **MOV S14K150 across L–N, after the fuse.** Clamps line transients; 150 VAC
    rating for a 120 V nominal line. It is a sacrificial part: if it has
    absorbed a big surge, replace it, not just the fuse.
11. **3.15 A fuse** in the hot leg, before everything else. A 60 W lamp draws
    ~0.5 A; the margin is for inrush of LED drivers and for a fault.
12. **BTA16-600B** (16 A, 600 V) in TO-220 — far more than a lamp needs, which
    buys thermal margin and inrush tolerance. Small heatsink above ~1 A.

## What the gates prove

- `tools/check_netlist.py` — the netlist exported from the schematic equals the
  intent: 16 nets, no extras, 13 pins deliberately open and nothing else. This is
  the gate that caught the rotated-symbol pin swap which would have fitted D5
  backwards (the exact failure that feeds 5 V into the XIAO the wrong way).
- `kicad-cli sch erc --severity-all --exit-code-violations` — 0 violations.
- `sim/results.txt` — the dimming curve (RMS output vs trigger delay) matches the
  closed-form answer to 0.00 % over ten points at 120 Vrms/60 Hz into 240 Ω.

## What is NOT proven

- **No safety claim of any kind.** Nothing in this repo certifies the board for
  mains use. The barrier is the HLK-PM01, the optos and the layout; the layout
  slice will enforce it with a `Mains` netclass (≥3 mm clearance plus a routed
  isolation slot under the triac and terminals, no copper pour crossing the
  barrier). Do not shrink that to save board area.
- **Gate drive, ZCD timing budget and snubber are not simulated yet** — next
  slice, in ngspice, against the same schematic.
- **Bulb behaviour cannot be simulated.** Only dimmable LED bulbs dim; some need
  a bleeder resistor, some buzz, some give up below ~20 %. Measure with the
  actual bulbs.
- **Thermal and fault behaviour** (contact-less now, but triac dissipation,
  fuse coordination, MOV ageing) are datasheet arguments here, not measurements.

## Open items / known weak points

- Never flash the XIAO with mains connected.
- The HLK-PM01 is an open-frame module: its pins and body belong inside the
  enclosure, and its DC side must not be touched once powered.
- The 3V3 rail from the XIAO feeds only R5 (10 k), so the XIAO's regulator load
  is negligible.
- Firmware: phase-angle control needs a zero-cross ISR and a delay timer per
  half-cycle. ESPHome's `ac_dimmer` component does exactly this if you would
  rather not write it.
- Cosmetic: the generated schematic uses the stub-plus-label style, so it is
  sparse in places and dense around the XIAO sockets. Wires can be drawn by hand
  later without changing the netlist — the gate will still pass.

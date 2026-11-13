# Parked — state of this board (2026-11-12)

**Status: design and gates complete; not yet sent to fab.** It is one pipeline step behind its
sibling `xiao-ac-ssr`, which is already at the fab-order stage.

## Where it stands

- Board: 150.0 × 57.0 mm, 2 layers, through-hole, same design family as `xiao-ac-ssr`.
  family as `xiao-ac-ssr`.
- **All five gates green** (`./tools/ci.sh`), including the nickname + mounting-hole + socket rules,
  the netlist pin names, and the board-provenance gate that ties the committed `.kicad_pcb` to
  `tools/gen_pcb.py`.
- **No gerbers produced yet** — this board is not orderable as it stands. `tools/gerbers.sh` is the
  step to run.
- Circuit is *not* the SSR's, and must not be confused with it: this is the phase-control dimmer —
  `BTA16-600B` (standard gate) + `MOC3021M` (**random-phase**) + 1 kΩ / 220 Ω, with the H11AA1
  zero-cross detector, an RC snubber, and an X2 capacitor. The SSR is `BTA16-600SW` + `MOC3063M`
  (zero-cross) + 360 Ω / 150 Ω. The parts fit each other's footprints and produce a board that does
  not work.

## Do next, in order

1. **Run `./tools/gerbers.sh`** and upload the resulting zip to the fab — same checkout settings the
   SSR used: 2 layers, 1.6 mm, 1 oz, **LeadFree HASL**, Remove Mark, flying-probe test,
   Confirm Production file → **Yes**, and **Global Standard Direct Line** for shipping (it avoids
   UPS's brokerage into Canada).
2. **Eyeball the gerber layers** — the one check the gates cannot do.
3. **Review the parts cart** against `BOM.md` before buying (the SSR's cart review found a wrong
   lead form on the varistor, a duplicate line per capacitor role, and a multi-pack counted as
   single units — expect the same classes of error here).
4. **Assemble and bring up** per the counterpart SSR procedure: GFCI outlet only, insulation test
   before first power-up, never probe while live.

## Traps already recorded (do not re-litigate)

- **Mating interfaces are a real gate gap.** The gates check the design against itself; none asks
  "does the ordered part fit this pattern". Place mating parts as locked objects and measure the
  part's real envelope, not the footprint's name.
- **A footprint deviation from a KiCad library part is guilty until proven** — `lib_footprint_mismatch`
  fires the moment a pad moves. Revert an unproven deviation; never weaken the gate to keep it.
- **Do not confuse this board with `xiao-ac-ssr`.** Same footprints, different parts, and one of them
  is a dimmer while the other is a switch.

## Resuming after a long gap

```bash
git pull && ./tools/ci.sh     # expect: gates OK, 0 errors, 0 warnings
./tools/gerbers.sh            # then continue at "Do next" above
```

Design rationale lives in `DESIGN.md`; board notes in `docs/PCB-NOTES.md`.

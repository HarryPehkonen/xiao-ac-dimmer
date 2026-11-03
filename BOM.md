# BOM — one board

Generated from the schematic, not typed from memory:

```bash
kicad-cli sch export bom --fields "Reference,Value,Footprint" \
  -o bom.csv xiao-ac-dimmer.kicad_sch
```

20 parts. `bom.csv` is the source of truth for values and footprints; this file
adds the part of the BOM a generator cannot know: **where to buy it, and what it
costs to get it here.**

## The sourcing rule

> **Consolidate to the fewest orders first. Origin is a tiebreaker on price, not
> an absolute.** A US-origin part that saves a shipment wins; a $6 saving that
> creates a second shipment loses.

Two constraints in tension, both Harri's:

1. **Non-US origin preferred** — US-origin parts carry tariff and political
   cost. DigiKey's Canadian presence is welcome as a *channel* (one shipment,
   CAD pricing, traceability), not as a statement about origin.
2. **Shipping is per-supplier and it is not small.** DigiKey CA: **free delivery
   at $100 CAD or more; about $15 CAD below that** (their delivery page states
   the $100 threshold; the sub-$100 charge has been reported rising to $15).

So a 20-line BOM can carry more shipping than parts. Two ways out: **pad the
order over $100** (spares of the passives are nearly free, and more boards are
coming), or **accept the charge once** rather than paying it several times.

## Where each part comes from

| Source | Parts |
| --- | --- |
| **DigiKey CA** (one order) | `C1` 470µF 16V · `C2` 100nF · `CS1` 100nF 400V · `D5` SS14 · `F1` 5×20mm fuseholder clip + 3.15A fuse · `MOV1` S14K150 · `Q1` BTA16-600B · `U1` H11AA1 · `U2` MOC3021M · `R1`,`R2` 47k · `R3` 220 · `R4` 1k · `R5` 10k · `RS1` 100 · `J1`,`J2` 1×07 pin sockets · `J3`,`J4` 5.08mm 2-pin terminal blocks |
| **AliExpress** | `PS1` HLK-PM01 5V 3W (about $1.79 CAD) |
| **Check the drawer first** | `U2` MOC3021M · `U1` H11AA1 · all resistors · 100nF / 470µF caps |

**Check the drawer first, seriously.** If the optos and the passives are already
in stock, the DigiKey order collapses to the awkward parts — terminals, fuse
holder, MOV, sockets — perhaps $25 of goods carrying $15 of shipping. That is
exactly the case where padding the order beats paying the charge.

### Why not the DigiKey alternative for PS1

Mean Well IRM-03-5 (`1866-3020-ND`) is the electrical equivalent (5V 3W 0.6A,
85–305 VAC in) and DigiKey stocks it, but: it is a **US-brand part at about
$8.17 CAD** after tariff, against $1.79; the swap costs **footprint change plus
rerouting PS1's pads and re-checking the 3mm barrier**; and the HLK-PM01's
footprint is already in the design. DigiKey publishes no Hi-Link parts at all —
their own TechForum cross-reference thread says they "cannot duplicate the
footprint shown on the HLK-PM01 data sheet" and names Recom RAC03-05SK
(`945-3441-ND`) as an electrically-correct substitute *with the wrong pin
layout*. KiCad has no RAC03 footprint; it does have the IRM-03 one.

**HLK-PM01 input range: 100–240 VAC, universal** — the manufacturer's own page
says "Rated input voltage 100-240Vac", and it is tested at 120 V and 230 V.
Listings titled "220V to 5V" are using the Chinese-market convention; it works
on North American 120 V mains. Max input current <0.2A.

### One spec to tighten

`CS1` is currently `100nF 400V`. For snubber duty across a mains triac, specify
the **part class**: an X2 or mains-duty film capacitor rated **250 VAC or
better**. "400 V" is a DC rating; it is not the same claim.

## Mechanical — mounting

The board has **no mounting holes yet**. Adding them is a small change to
`tools/gen_pcb.py`, not a redesign:

- 4 × M3 clearance holes (3.2mm drill) in the corners, **5mm inset** from the
  board edge, each with a 6mm copper keepout so no net comes near the screw.
- The mounting pads stay **isolated** — connected to no net, no copper ring
  under the screw head.
- **Nylon standoffs, not metal.** This is a two-wire appliance with no earth
  conductor, so there is nothing for a metal standoff or a metal enclosure to be
  safely bonded to. Plastic standoffs and a plastic box avoid the question
  entirely.
- Adding holes means re-running the router: the corner keepouts change the
  available corridors. Cheap now that the gate is known-good.

## Mechanical — thermal

`Q1` (BTA16-600B) is the only real heat source. Its dissipation is the on-state
drop times load current, roughly 1.0–1.2 V at 1 A:

| Load | Dissipation | Verdict |
| --- | --- | --- |
| 60 W lamp (~0.5 A) | ~0.6 W | No heatsink. ~35 °C rise on a TO-220 in free air |
| 100 W lamp (~0.85 A) | ~1.0 W | Borderline. ~60 °C rise; a small clip-on heatsink is cheap insurance |
| Board ceiling, 3.15 A | ~3.5–4 W | **Real heatsink required.** ~5 °C/W, tab-mounted |

Notes that matter more than the table:

- **BTA (isolated tab), not BTB.** The `A` part's tab is electrically isolated,
  so a heatsink needs no insulating pad. Keep the heatsink **floating** —
  connected to no net.
- In an **enclosed box** the ambient is 40–50 °C, not 25 °C. Derate accordingly;
  the numbers above assume free air.
- `PS1`, the snubber, `MOV1` and the fuse are thermally irrelevant at this
  power level.
- Ventilation in the box is worth more than a bigger heatsink.

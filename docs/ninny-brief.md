# Close the last two nets on the XIAO AC dimmer PCB

## The repository

`xiao-ac-dimmer` — a single-channel inline AC dimmer board for a Seeed XIAO
ESP32C3 (mains cord in, lamp socket out, phase-control triac). Everything is
generated headless; there is no GUI on this machine.

| file | what it is |
| --- | --- |
| `tools/gen_sch.py` | generates `xiao-ac-dimmer.kicad_sch` from a part/net table |
| `tools/check_netlist.py` | gate: exported netlist == intended netlist |
| `tools/gen_pcb.py` | places footprints (zone packer) and routes the board |
| `tools/route.py` | the maze router (A* over a 0.5 mm grid, two layers, vias) |
| `tools/check_board.py` | gate: `kicad-cli pcb drc`, exit 0 = no violations |
| `tools/ci.sh` | the gate: schematic staleness + netlist + ERC |
| `xiao-ac-dimmer.kicad_pcb` | GENERATED — never hand-edit it |
| `xiao-ac-dimmer.kicad_dru` | custom DRC rules (the mains isolation barrier) |

Toolchain: `kicad-cli` 9.0.2 and `pcbnew` 9.0.2, the Python bindings only under
**`/usr/bin/python3`** (not a venv). Regenerate the board with
`/usr/bin/python3 tools/gen_pcb.py`; run the gate with
`/usr/bin/python3 tools/check_board.py`; the schematic gate is `./tools/ci.sh`.

## The red test — this is the whole task

```
/usr/bin/python3 tools/check_board.py    # exits 1 today
```

3 `unconnected_items` errors: 14 of 16 nets route. The two that do not are
**`LOAD_L`** (J4.1 → Q1.2) and **`ZCD_OUT`** (R5.2 → U1.5). No shorts and no
clearance violations exist — do not break that.

## Diagnosis already done — use it, do not redo it

The router prints, for each failure, how much of the *landing pad's* opening
survives (`cells=49` is the full opening disc):

```
LOAD_L   J4.1 -> Q1.2  pad-veto=22 copper-veto L0=19/L1=11 free L0=8/L1=16
ZCD_OUT  R5.2 -> U1.5  pad-veto=19 copper-veto L0=27/L1=0  free L0=3/L1=30
```

- `pad-veto` = cells blocked by *neighbouring pads* (its own pin column,
  2.54 mm pitch)
- `copper-veto L0/L1` = cells blocked by already-routed copper, per layer
- `free` = cells actually opened

Reading: both landing pads sit in a 2.54 mm pin column. The neighbours' keepouts
eat most of the opening and what survives does not reach open space on both
layers. **Placement is not the constraint any more — the opening is.** Note that
one layer is often clear (`ZCD_OUT` has `free L1=30`), so an opening that
explores per layer, and a channel that runs *along* the pin row as well as
perpendicular to it, are the obvious places to look.

## What to build

1. **Tests, starting with one that fails today.** Your *first* test must be red:
   a test that the whole board routes completely — 16/16 nets, or equivalently
   `check_board.py` exits 0 — fails right now and passes when this work is done.
   Write that one first and watch it fail before you touch the router. The
   pure-function tests below come after it:
   - `_to_segments` merges collinear grid steps into one segment; turns a
     corner into two; splits at a layer change; never emits a zero-length run.
   - `_c`/`_mm` round-trip on the 0.5 mm grid.
   - the escape spoke is perpendicular to the nearest neighbour, for a
     neighbour above, below, left and right.
2. **Make the two nets route.** `python3 tools/check_board.py` must exit 0.
3. **Wire `check_board.py` into `tools/ci.sh`** in the *same commit* that makes
   it pass. A gate that fails proves nothing and trains people to ignore it.
4. Update the numbers in `docs/PCB-NOTES.md`.

## Hard constraints — do not do any of these

- Do **not** edit `xiao-ac-dimmer.kicad_dru`. The 3 mm mains isolation barrier
  is the point of the board. Weakening it is not a fix.
- Do **not** relax the router's clearance constants to make DRC pass. The floor
  is **measured**: 0.25 mm margin produced 12 shorts against `no-net` pads,
  0.5 mm is clean but wastes the space dense pin columns need, 0.4 mm holds.
- Do **not** delete parts, pads or nets, and do not change the net list in
  `tools/gen_sch.py`.
- Do **not** hand-edit `xiao-ac-dimmer.kicad_pcb`. It is generated; the fix
  belongs in `tools/gen_pcb.py` / `tools/route.py` so regeneration reproduces
  the result.
- Do **not** commit. Leave the working tree for review.
- **Explore in `/tmp`, never in the repo.** The previous attempt at this brief
  wrote seven throwaway prototype scripts into `tmp_diag/` in the tree; they
  would have shipped in the patch. Keep the tree to the change itself.
- **Run the acceptance command after every source write.** It takes about a
  second — `time /usr/bin/python3 tools/check_board.py`. The previous attempt
  made nine writes and ran it zero times, and spent 23 steps guessing at
  geometry it could have measured. The suite is the only feedback that matters
  here; use it constantly.

## Acceptance

- `/usr/bin/python3 tools/check_board.py` exits 0.
- `./tools/ci.sh` still passes (schematic stale check, netlist == intent, ERC
  clean).
- The router tests pass.
- `git diff --stat` shows **no** change to `xiao-ac-dimmer.kicad_dru` and no
  change to the nets in `tools/gen_sch.py`.

## Report back

What you changed and why; the real command output showing 16/16 routed and the
DRC counts; anything you could not fix and what you tried. If a net still will
not route, say so plainly — do not make the gate pass by any other means.

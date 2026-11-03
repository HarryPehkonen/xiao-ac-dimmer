#!/bin/sh
# Gate for this repo.  Five checks, all machine-verifiable:
#   1. the committed schematic is exactly what the generator produces
#   2. the netlist exported from it equals the intended netlist
#   3. ERC reports no violations
#   4. the board passes DRC with no violations, and honours the rules DRC has
#      no rule for (every footprint id names its library, the mounting holes
#      are where the design says with an empty copper keepout, and the two
#      socket rows are one mating interface that a XIAO actually fits)
#   5. the rules in 4 have been seen to fail -- each is broken in
#      tools/tests/test_board_gate.py and check_board.py must report it
# Run from anywhere:  ./tools/ci.sh
set -eu
cd "$(dirname "$0")/.."

echo "== committed schematic matches the generator"
before=$(sha256sum xiao-ac-dimmer.kicad_sch | cut -d' ' -f1)
python3 tools/gen_sch.py > /dev/null
after=$(sha256sum xiao-ac-dimmer.kicad_sch | cut -d' ' -f1)
if [ "$before" != "$after" ]; then
    echo "FAIL: xiao-ac-dimmer.kicad_sch was stale -- regenerated, review and commit"
    exit 1
fi

echo "== netlist matches intent"
python3 tools/check_netlist.py

echo "== ERC"
kicad-cli sch erc --severity-all --exit-code-violations \
    -o /dev/null xiao-ac-dimmer.kicad_sch

echo "== board DRC and the rules it cannot express"
/usr/bin/python3 tools/check_board.py

echo "== the board gate's own tests (each gate rule, seen to fail)"
# Seen to fail, not just seen to pass: tools/tests/test_board_gate.py breaks
# every rule check_board.py asserts -- including the XIAO socket's mating
# geometry, which ERC and DRC cannot see at all -- and requires the report.
/usr/bin/python3 -m pytest tools/tests -q > /dev/null 2>&1 || {
    /usr/bin/python3 -m pytest tools/tests -q
    exit 1
}

echo "OK"

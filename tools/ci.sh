#!/bin/sh
# Gate for this repo.  Six checks, all machine-verifiable:
#   1. the committed schematic -- and the symbol library it draws J1/J2 from --
#      is exactly what the generator produces
#   2. the netlist exported from it equals the intended netlist, and every pin
#      of the two XIAO socket rows carries the *module's* pin name
#      (see "The socket symbol" in docs/PCB-NOTES.md)
#   3. ERC reports no violations
#   4. the board passes DRC with no violations, and honours the rules DRC has
#      no rule for (every footprint id names its library, the mounting holes
#      are where the design says with an empty copper keepout, and the two
#      socket rows are one mating interface that a XIAO actually fits)
#   5. the committed board is the one the generator produces (placement + copper)
#   6. the rules in 2 and 4 have been seen to fail -- each is broken in
#      tools/tests/ and check_board.py or check_netlist.py must report it
# Run from anywhere:  ./tools/ci.sh
set -eu
cd "$(dirname "$0")/.."

echo "== committed schematic matches the generator"
# The symbol library is generated too: a stale copy would give a schematic
# whose cached lib_symbols no longer matches the symbols/xiao-ac.kicad_sym that
# sym-lib-table points at (another thing ERC's library check would notice).
gen() {
    sha256sum xiao-ac-dimmer.kicad_sch symbols/xiao-ac.kicad_sym |
        sha256sum | cut -d' ' -f1
}
before=$(gen)
python3 tools/gen_sch.py > /dev/null
after=$(gen)
if [ "$before" != "$after" ]; then
    echo "FAIL: xiao-ac-dimmer.kicad_sch or symbols/xiao-ac.kicad_sym was stale -- regenerated, review and commit"
    exit 1
fi

echo "== netlist matches intent (nets and the socket rows' pin names)"
python3 tools/check_netlist.py

echo "== ERC"
kicad-cli sch erc --severity-all --exit-code-violations \
    -o /dev/null xiao-ac-dimmer.kicad_sch

echo "== board DRC and the rules it cannot express"
/usr/bin/python3 tools/check_board.py

echo "== committed board matches the generator"
# Quiet when it passes (pcbnew prints image-handler noise on stdout), loud when
# it fails -- which is the only time a person needs to read it.
/usr/bin/python3 tools/check_regen.py > /dev/null 2>&1 || {
    /usr/bin/python3 tools/check_regen.py
    exit 1
}

echo "== the gate's own tests (every rule, seen to fail)"
# Seen to fail, not just seen to pass: tools/tests/test_board_gate.py breaks
# every rule check_board.py asserts -- including the XIAO socket's mating
# geometry, which ERC and DRC cannot see at all -- and
# tools/tests/test_pin_names.py breaks the socket rows' pin names, which ERC
# and the netlist's connectivity cannot see either.  Each requires the report.
/usr/bin/python3 -m pytest tools/tests -q > /dev/null 2>&1 || {
    /usr/bin/python3 -m pytest tools/tests -q
    exit 1
}

echo "OK"

#!/usr/bin/env python3
"""Gate: the board passes DRC with no violations.

    python3 tools/check_board.py        # exit 0 = clean
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_pcb

BOARD = gen_pcb.BOARD


def main():
    report = "/tmp/drc.rpt"
    r = subprocess.run(["kicad-cli", "pcb", "drc", "--exit-code-violations",
                        "-o", report, BOARD], capture_output=True, text=True)
    text = open(report, encoding="utf-8").read() if os.path.exists(report) else ""

    kinds = {}
    for kind, sev in re.findall(
            r"^\[([a-z_]+)\]:[^\n]*\n[^\n]*;\s*(error|warning)\s*$", text, re.M):
        kinds[(kind, sev)] = kinds.get((kind, sev), 0) + 1
    errs = sum(n for (k, s), n in kinds.items() if s == "error")
    warns = sum(n for (k, s), n in kinds.items() if s == "warning")

    for (kind, sev), n in sorted(kinds.items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {sev:<8} {kind:<28} {n}")
    print(f"{errs} error(s), {warns} warning(s)")

    # show the first few distinct complaints so a failure is actionable
    if r.returncode != 0:
        seen = set()
        for block in re.split(r"\n(?=\[)", text):
            m = re.match(r"\[([a-z_]+)\]:", block)
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                print("  --- example ---")
                print("  " + block.strip().replace("\n", "\n  ")[:400])
                if len(seen) >= 3:
                    break
    return 1 if r.returncode != 0 else 0


if __name__ == "__main__":
    sys.exit(main())

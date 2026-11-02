#!/usr/bin/env python3
"""Find which embedded lib_symbol breaks the schematic load.

For each library id used by the generator, emit a one-symbol schematic and
ask kicad-cli to export a netlist from it.
"""
import os
import subprocess
import sys
import uuid

sys.path.insert(0, "/home/harri/hermes-workspace/xiao-ac-dimmer/tools")
import kicadlib as kl
import gen_sch

TMP = "/home/harri/.hermes/profiles/hermes-dev/cache/scratch/probe"
os.makedirs(TMP, exist_ok=True)


def one(lib):
    node, _ = kl.flatten(lib)
    node = list(node)
    node[1] = '"' + lib + '"'
    body = kl.to_text(node, 1)
    root = str(uuid.uuid4())
    sch = [
        "(kicad_sch", "\t(version 20250114)", '\t(generator "probe")',
        '\t(generator_version "9.0")', f'\t(uuid "{root}")', '\t(paper "A3")',
        "\t(lib_symbols", body, "\t)",
        "\t(symbol", f'\t\t(lib_id "{lib}")', "\t\t(at 100 100 0)", "\t\t(unit 1)",
        "\t\t(exclude_from_sim no)", "\t\t(in_bom yes)", "\t\t(on_board yes)",
        "\t\t(dnp no)", f'\t\t(uuid "{uuid.uuid4()}")',
        '\t\t(property "Reference" "X1"', "\t\t\t(at 100 95 0)",
        "\t\t\t(effects", "\t\t\t\t(font", "\t\t\t\t\t(size 1.27 1.27)",
        "\t\t\t\t)", "\t\t\t)", "\t\t)",
        '\t\t(property "Value" "V"', "\t\t\t(at 100 105 0)",
        "\t\t\t(effects", "\t\t\t\t(font", "\t\t\t\t\t(size 1.27 1.27)",
        "\t\t\t\t)", "\t\t\t)", "\t\t)",
        "\t\t(instances", '\t\t\t(project "probe"', f'\t\t\t\t(path "/{root}"',
        '\t\t\t\t\t(reference "X1")', "\t\t\t\t\t(unit 1)", "\t\t\t\t)",
        "\t\t\t)", "\t\t)", "\t)",
        "\t(sheet_instances", '\t\t(path "/"', '\t\t\t(page "1")', "\t\t)", "\t)",
        ")"]
    path = os.path.join(TMP, lib.replace(":", "_") + ".kicad_sch")
    open(path, "w").write("\n".join(sch) + "\n")
    r = subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format",
                        "kicadsexpr", "-o", path + ".net", path],
                       capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


if __name__ == "__main__":
    libs = sorted({p["lib"] for p in gen_sch.PARTS})
    for lib in libs:
        code, msg = one(lib)
        print(f"{'OK  ' if code == 0 else 'FAIL'} {lib:<40} {msg[:90]}")

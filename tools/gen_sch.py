#!/usr/bin/env python3
"""Generate the KiCad schematic for the XIAO AC dimmer board.

Connectivity is expressed as labelled stubs: every pin gets a 2.54 mm wire
away from the symbol body plus a local label naming its net.  kicad-cli
exports a netlist from that, and tools/check_netlist.py asserts the exported
nets are exactly the intent recorded below -- so the schematic is verified
by machine, not by eye.

    python3 tools/gen_sch.py            # writes xiao-ac-dimmer.kicad_sch
"""
import math
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kicadlib as kl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = "xiao-ac-dimmer"
STUB = 2.54          # mm, length of the labelled stub
FONT = 1.27

TERM = ("TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02"
        "_P5.08mm_Horizontal")
FUSEHLD = ("Fuse:Fuseholder_Clip-5x20mm_Keystone_3512P_Inline_"
           "P23.62x7.27mm_D1.02x2.41x1.02x1.57mm_Horizontal")
R_AX = "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal"
DIP6 = "Package_DIP:DIP-6_W7.62mm"
SOCK7 = "Connector_PinSocket_2.54mm:PinSocket_1x07_P2.54mm_Vertical"


def uid(*key):
    """Deterministic UUID, so regenerating the schematic is a clean diff."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, PROJECT + ":" + ":".join(key)))


# ---------------------------------------------------------------- circuit ----
# Mains safety shape: the fuse and the triac are both in the HOT leg, the
# neutral runs straight through, and nothing on the logic side touches it.
PARTS = [
    # mains inlet, protection, isolated supply
    {"ref": "J3", "lib": "Connector:Screw_Terminal_01x02", "val": "AC IN (cord)",
     "fp": TERM, "at": (40, 60, 0), "pins": {"1": "L_IN", "2": "N_AC"}},
    {"ref": "F1", "lib": "Device:Fuse", "val": "3.15A", "fp": FUSEHLD,
     "at": (70, 55, 90), "pins": {"1": "L_IN", "2": "L_FUSED"}},
    {"ref": "MOV1", "lib": "Device:Varistor", "val": "S14K150",
     "fp": "Varistor:RV_Disc_D12mm_W4.5mm_P7.5mm", "at": (100, 75, 0),
     "pins": {"1": "L_FUSED", "2": "N_AC"}},
    {"ref": "PS1", "lib": "Converter_ACDC:HLK-PM01", "val": "HLK-PM01 5V 0.6A",
     "fp": "Converter_ACDC:Converter_ACDC_Hi-Link_HLK-PMxx", "at": (60, 120, 0),
     "pins": {"1": "L_FUSED", "2": "N_AC", "3": "GND", "4": "+5V_PS"}},
    # Schottky: Seeed require a diode between an external 5V source and VBUS
    {"ref": "D5", "lib": "Device:D_Schottky", "val": "SS14",
     "fp": "Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal", "at": (95, 125, 90),
     "pins": {"1": "+5V_XIAO", "2": "+5V_PS"}},
    {"ref": "C1", "lib": "Device:C_Polarized", "val": "470uF 16V",
     "fp": "Capacitor_THT:CP_Radial_D8.0mm_P3.50mm", "at": (120, 125, 0),
     "pins": {"1": "+5V_PS", "2": "GND"}},
    {"ref": "C2", "lib": "Device:C", "val": "100nF",
     "fp": "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm", "at": (140, 125, 0),
     "pins": {"1": "+5V_XIAO", "2": "GND"}},
    # zero-cross detector: one 47k in each leg, H11AA1 across the mains
    {"ref": "R1", "lib": "Device:R", "val": "47k", "fp": R_AX,
     "at": (110, 160, 0), "pins": {"1": "L_FUSED", "2": "ZCD_A"}},
    {"ref": "R2", "lib": "Device:R", "val": "47k", "fp": R_AX,
     "at": (130, 175, 0), "pins": {"1": "N_AC", "2": "ZCD_B"}},
    {"ref": "U1", "lib": "Isolator:H11AA1", "val": "H11AA1", "fp": DIP6,
     "at": (165, 165, 0),
     "pins": {"1": "ZCD_A", "2": "ZCD_B", "4": "GND", "5": "ZCD_OUT", "6": "NO"}},
    {"ref": "R5", "lib": "Device:R", "val": "10k", "fp": R_AX,
     "at": (195, 150, 0), "pins": {"1": "+3V3", "2": "ZCD_OUT"}},
    # XIAO sockets.  LEFT top->bottom = D0..D6 ; RIGHT top->bottom = 5V, GND,
    # 3V3, D10, D9, D8, D7 (Seeed front pinout diagram).
    {"ref": "J1", "lib": "Connector_Generic:Conn_01x07", "val": "XIAO left D0..D6",
     "fp": SOCK7, "at": (220, 100, 0), "pins": {"2": "GATE_DRV", "3": "ZCD_OUT"},
     "nc": ["1", "4", "5", "6", "7"]},
    {"ref": "J2", "lib": "Connector_Generic:Conn_01x07",
     "val": "XIAO right 5V,GND,3V3,D10,D9,D8,D7", "fp": SOCK7, "at": (255, 100, 0),
     "pins": {"1": "+5V_XIAO", "2": "GND", "3": "+3V3"},
     "nc": ["4", "5", "6", "7"]},
    # trigger: GPIO3 (D1) -> 220R -> MOC3021 LED ; MOC output drives the gate
    {"ref": "R3", "lib": "Device:R", "val": "220", "fp": R_AX,
     "at": (220, 190, 0), "pins": {"1": "GATE_DRV", "2": "MOC_A"}},
    {"ref": "U2", "lib": "Relay_SolidState:MOC3021M", "val": "MOC3021M", "fp": DIP6,
     "at": (245, 190, 0),
     "pins": {"1": "MOC_A", "2": "GND", "4": "MOC_MT2", "6": "LOAD_L"}},
    {"ref": "R4", "lib": "Device:R", "val": "1k", "fp": R_AX,
     "at": (275, 200, 0), "pins": {"1": "MOC_MT2", "2": "TRIAC_G"}},
    {"ref": "Q1", "lib": "Triac_Thyristor:BTA16-600B", "val": "BTA16-600B",
     "fp": "Package_TO_SOT_THT:TO-220-3_Vertical", "at": (300, 225, 0),
     "pins": {"1": "L_FUSED", "2": "LOAD_L", "3": "TRIAC_G"}},
    {"ref": "RS1", "lib": "Device:R", "val": "100", "fp": R_AX,
     "at": (325, 205, 90), "pins": {"1": "L_FUSED", "2": "SNUB_MID"}},
    {"ref": "CS1", "lib": "Device:C", "val": "100nF 400V",
     "fp": "Capacitor_THT:C_Rect_L7.0mm_W2.0mm_P5.00mm", "at": (350, 205, 90),
     "pins": {"1": "SNUB_MID", "2": "LOAD_L"}},
    # mains outlet (lamp), neutral unswitched
    {"ref": "J4", "lib": "Connector:Screw_Terminal_01x02", "val": "AC OUT (lamp)",
     "fp": TERM, "at": (350, 60, 0), "pins": {"1": "LOAD_L", "2": "N_AC"}},
    # ERC: L_IN and N_AC are fed by a passive terminal block
    {"ref": "FLG1", "lib": "power:PWR_FLAG", "val": "PWR_FLAG", "fp": "",
     "at": (40, 85, 0), "pins": {"1": "L_FUSED"}},
    {"ref": "FLG2", "lib": "power:PWR_FLAG", "val": "PWR_FLAG", "fp": "",
     "at": (40, 95, 0), "pins": {"1": "N_AC"}},
]


def nets():
    """{net: [(ref, pin)]} -- the intended netlist."""
    out = {}
    for p in PARTS:
        for pin, net in p["pins"].items():
            if net == "NO":
                continue
            out.setdefault(net, []).append((p["ref"], pin))
    return {k: sorted(v) for k, v in out.items()}


def nc_pins(part):
    """Pins marked no-connect: the explicit list plus 'NO' in the pin map."""
    return sorted(set(part.get("nc", [])) |
                  {pin for pin, net in part["pins"].items() if net == "NO"})


# ------------------------------------------------------------- geometry -----
def _rot_sheet(vx, vy, rot):
    """Rotate a sheet-space vector by the instance rotation (KiCad counts
    rotation counter-clockwise on screen; sheet y grows downward)."""
    for _ in range(int(rot // 90) % 4):
        vx, vy = vy, -vx
    return (round(vx, 4), round(vy, 4))


def pin_xy(px, py, rot, x0, y0):
    """Symbol-space pin point -> sheet coords (symbol y is up, sheet y down)."""
    vx, vy = _rot_sheet(px, -py, rot)
    return (round(x0 + vx, 3), round(y0 + vy, 3))


def out_dir(angle, rot):
    """Unit vector pointing away from the symbol body, in sheet coords."""
    th = math.radians(angle + 180)
    return _rot_sheet(math.cos(th), -math.sin(th), rot)


# ------------------------------------------------------------- emission -----
GRID = 1.27          # KiCad's connection grid, mm


def snap(v):
    """Pull a coordinate onto the connection grid (ERC flags off-grid ends)."""
    return round(round(v / GRID) * GRID, 4)


def symbol_block(part, used_geo, root_uuid, at):
    ref, lib = part["ref"], part["lib"]
    x, y, rot = at
    lines = ["\t(symbol",
             f'\t\t(lib_id "{lib}")',
             f"\t\t(at {x} {y} {rot})",
             "\t\t(unit 1)",
             "\t\t(exclude_from_sim no)",
             "\t\t(in_bom yes)",
             "\t\t(on_board yes)",
             "\t\t(dnp no)",
             f'\t\t(uuid "{uid("sym", ref)}")']
    for name, text, dy, size, hide in (
            ("Reference", ref, -5.08, FONT, False),
            ("Value", part["val"], 5.08, FONT, False),
            ("Footprint", part["fp"], 7.62, 0.254, True),
            ("Datasheet", "", 0, FONT, True),
            ("Description", "", 0, FONT, True)):
        lines += [f'\t\t(property "{name}" "{text}"',
                  f"\t\t\t(at {x} {round(y + dy, 3)} 0)",
                  "\t\t\t(effects",
                  "\t\t\t\t(font",
                  f"\t\t\t\t\t(size {size} {size})",
                  "\t\t\t\t)"]
        if hide:
            lines.append("\t\t\t\t(hide yes)")
        lines += ["\t\t\t)", "\t\t)"]
    for g in used_geo:
        lines += [f'\t\t(pin "{g["num"]}"',
                  f'\t\t\t(uuid "{uid("pin", ref, g["num"])}")',
                  "\t\t)"]
    lines += ["\t\t(instances",
              f'\t\t\t(project "{PROJECT}"',
              f'\t\t\t\t(path "/{root_uuid}"',
              f'\t\t\t\t\t(reference "{ref}")',
              "\t\t\t\t\t(unit 1)",
              "\t\t\t\t)",
              "\t\t\t)",
              "\t\t)",
              "\t)"]
    return lines


def build():
    root_uuid = uid("root")
    geos, libs = {}, {}
    for part in PARTS:
        lib = part["lib"]
        if lib in libs:
            continue
        node, _ = kl.flatten(lib)
        node = list(node)
        node[1] = '"' + lib + '"'
        libs[lib] = kl.to_text(node, 1)
        geos[lib] = kl.pins_geo(node)

    out = ["(kicad_sch",
           "\t(version 20250114)",
           '\t(generator "gen_sch.py")',
           '\t(generator_version "9.0")',
           f'\t(uuid "{root_uuid}")',
           '\t(paper "A3")',
           "\t(title_block",
           '\t\t(title "XIAO AC dimmer - 1 channel, inline cord")',
           '\t\t(date "2026-11-01")',
           '\t\t(rev "0.1")',
           "\t)",
           "\t(lib_symbols"]
    for lib in sorted(libs):
        out.append(libs[lib])
    out.append("\t)")

    wires, labels, ncs = [], [], []
    for part in PARTS:
        ref, lib = part["ref"], part["lib"]
        at = (snap(part["at"][0]), snap(part["at"][1]), part["at"][2])
        x, y, rot = at
        wanted = sorted(set(part["pins"]) | set(nc_pins(part)))
        used_geo = [g for g in geos[lib] if g["num"] in wanted]
        missing = set(wanted) - {g["num"] for g in used_geo}
        assert not missing, f"{ref}: no such pin(s) {sorted(missing)}"
        out.extend(symbol_block(part, used_geo, root_uuid, at))
        for g in used_geo:
            px, py = pin_xy(g["x"], g["y"], rot, x, y)
            net = part["pins"].get(g["num"])
            if net is None or net == "NO":
                ncs.append((px, py))
                continue
            vx, vy = out_dir(g["angle"], rot)
            ex, ey = round(px + vx * STUB, 3), round(py + vy * STUB, 3)
            wires.append((px, py, ex, ey, uid("w", ref, g["num"])))
            labels.append((net, ex, ey, 180 if vx < -0.5 else 0,
                           "right" if vx < -0.5 else "left",
                           uid("l", ref, g["num"])))

    for x0, y0, x1, y1, u in wires:
        out += ["\t(wire",
                "\t\t(pts",
                f"\t\t\t(xy {x0} {y0}) (xy {x1} {y1})",
                "\t\t)",
                "\t\t(stroke",
                "\t\t\t(width 0)",
                "\t\t\t(type solid)",
                "\t\t)",
                f'\t\t(uuid "{u}")',
                "\t)"]
    for net, x, y, ang, just, u in sorted(labels, key=lambda t: (t[0], t[1], t[2])):
        out += [f'\t(label "{net}"',
                f"\t\t(at {x} {y} {ang})",
                "\t\t(effects",
                "\t\t\t(font",
                f"\t\t\t\t(size {FONT} {FONT})",
                "\t\t\t)",
                f"\t\t\t(justify {just} bottom)",
                "\t\t)",
                f'\t\t(uuid "{u}")',
                "\t)"]
    for x, y in sorted(ncs):
        out += ["\t(no_connect",
                f"\t\t(at {x} {y})",
                f'\t\t(uuid "{uid("nc", str(x), str(y))}")',
                "\t)"]
    out += ["\t(sheet_instances",
            '\t\t(path "/"',
            '\t\t\t(page "1")',
            "\t\t)",
            "\t)",
            ")"]
    return "\n".join(out) + "\n"


PROJECT_JSON = """{
  "board": {
    "design_settings": {
      "defaults": {},
      "rules": {},
      "track_widths": [],
      "via_dimensions": []
    },
    "layer_presets": [],
    "viewports": []
  },
  "libraries": {
    "pinned_footprint_libs": [],
    "pinned_symbol_libs": []
  },
  "meta": {
    "filename": "%s.kicad_pro",
    "version": 1
  },
  "schematic": {
    "annotate_start_num": 0,
    "legacy_lib_dir": "",
    "legacy_lib_list": []
  },
  "sheets": [],
  "text_variables": {}
}
"""


def write_project():
    """The .kicad_pro plus the two library tables, so the schematic resolves
    its libraries without any global configuration."""
    syms = sorted({p["lib"].split(":")[0] for p in PARTS})
    fps = sorted({p["fp"].split(":")[0] for p in PARTS if p["fp"]})
    open(os.path.join(ROOT, PROJECT + ".kicad_pro"), "w").write(
        PROJECT_JSON % PROJECT)
    open(os.path.join(ROOT, "sym-lib-table"), "w").write(
        "(sym_lib_table\n\t(version 7)\n" + "".join(
            f'\t(lib (name "{n}")(type "KiCad")'
            f'(uri "${{KICAD9_SYMBOL_DIR}}/{n}.kicad_sym")(options "")(descr ""))\n'
            for n in syms) + ")\n")
    open(os.path.join(ROOT, "fp-lib-table"), "w").write(
        "(fp_lib_table\n\t(version 7)\n" + "".join(
            f'\t(lib (name "{n}")(type "KiCad")'
            f'(uri "${{KICAD9_FOOTPRINT_DIR}}/{n}.pretty")(options "")(descr ""))\n'
            for n in fps) + ")\n")
    print(f"wrote {PROJECT}.kicad_pro, sym-lib-table, fp-lib-table "
          f"({len(syms)} symbol libs, {len(fps)} footprint libs)")


if __name__ == "__main__":
    text = build()
    path = os.path.join(ROOT, PROJECT + ".kicad_sch")
    open(path, "w").write(text)
    print(f"wrote {path} ({len(text.splitlines())} lines)")
    write_project()
    for net, members in sorted(nets().items()):
        print(f"  {net:<10} {' '.join(r + '.' + p for r, p in members)}")

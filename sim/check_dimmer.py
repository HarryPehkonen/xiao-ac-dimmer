#!/usr/bin/env python3
"""Leading-edge dimmer: ngspice RMS output vs closed form.

Theory (resistive load, trigger angle theta after each zero crossing):
    Vrms = Vpk * sqrt( ((pi - theta)/2 + sin(2*theta)/4) / pi )
with theta = 2*pi*f*td. theta = 0 must give Vpk/sqrt(2) = 120.2 Vrms.
"""
import math, re, subprocess, tempfile, os

SCRATCH = "/home/harri/.hermes/profiles/hermes-dev/cache/scratch"
TPL = os.path.join(SCRATCH, "dimmer_template.cir")
F, VPK, RLOAD = 60.0, 170.0, 240.0
DELAYS_MS = [0.2, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0]

def theory(td):
    th = 2 * math.pi * F * td
    if th > math.pi:
        return 0.0
    return VPK * math.sqrt(((math.pi - th) / 2 + math.sin(2 * th) / 4) / math.pi)

tpl = open(TPL).read()
print(f"{'delay(ms)':>9} {'theta(deg)':>10} {'sim Vrms':>9} {'theory':>8} "
      f"{'err%':>7} {'watts/240R':>10}")
worst = 0.0
for ms in DELAYS_MS:
    td = ms / 1000.0
    deck = os.path.join(SCRATCH, f"dim_{ms}ms.cir")
    open(deck, "w").write(tpl.replace("@TD@", f"{td:.6f}"))
    out = subprocess.run(["ngspice", "-b", deck], capture_output=True, text=True,
                         timeout=120).stdout
    m = re.search(r"vrms\s*=\s*([-\d.eE+]+)", out)
    if not m:
        print(f"{ms:>9} FAILED to parse; raw tail: {out.strip()[-200:]}")
        continue
    sim = float(m.group(1))
    th = theory(td)
    err = abs(sim - th) / th * 100 if th else 0.0
    worst = max(worst, err)
    print(f"{ms:>9} {math.degrees(2*math.pi*F*td):>10.1f} {sim:>9.2f} {th:>8.2f} "
          f"{err:>7.2f} {sim*sim/RLOAD:>10.1f}")
print(f"\nworst disagreement vs closed form: {worst:.2f}%  (load {RLOAD} ohm resistive)")

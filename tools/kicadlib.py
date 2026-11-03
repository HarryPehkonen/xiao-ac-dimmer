#!/usr/bin/env python3
"""Minimal KiCad s-expression reader + symbol probe.

KiCad's .kicad_sym / .kicad_sch files are s-expressions. This module is the
only place that knows how to read them, so the generator stays readable.

    python3 kicadlib.py find <pattern>          # symbol names in the libs
    python3 kicadlib.py pins <Lib:Symbol>       # pin table for one symbol
    python3 kicadlib.py dump <Lib:Symbol>       # raw definition (for lib_symbols)

Quoted strings are kept WITH their quotes so a node can be re-emitted verbatim.
"""
import os
import re
import sys

SYMDIR = "/usr/share/kicad/symbols"
# A project may carry its own symbols instead of adding them to KiCad's global
# tables: `symbols/<lib>.kicad_sym` beside the schematic, i.e. what a
# sym-lib-table entry points at with ${KIPRJMOD}.  Resolve those too, so
# flatten() works for a project library exactly as it does for a stock one.
LOCALDIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "symbols")


def lib_file(name):
    """Path of the .kicad_sym that defines Lib:Symbol (stock, then local)."""
    lib = name.split(":", 1)[0]
    for d in (SYMDIR, LOCALDIR):
        path = os.path.join(d, lib + ".kicad_sym")
        if os.path.exists(path):
            return path
    raise KeyError(f"no {lib}.kicad_sym in {SYMDIR} or {LOCALDIR}")


def parse(text):
    """Parse an s-expression file -> list of top-level nodes (nested lists)."""
    out, stack, token, in_str, esc = [], [], "", False, False
    for ch in text:
        if in_str:
            token += ch
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
                stack[-1].append(token)
                token = ""
            continue
        if ch == '"':
            if token:
                stack[-1].append(token)
                token = ""
            in_str = True
            token = '"'
        elif ch == "(":
            if token:
                stack[-1].append(token)
                token = ""
            stack.append([])
        elif ch == ")":
            if token:
                stack[-1].append(token)
                token = ""
            node = stack.pop()
            if stack:
                stack[-1].append(node)
            else:
                out.append(node)
        elif ch.isspace():
            if token:
                stack[-1].append(token)
                token = ""
        else:
            if not stack:                      # tolerate stray leading text
                continue
            token += ch
    return out


def head(node):
    return node[0] if node and isinstance(node[0], str) else None


def kids(node, name):
    return [c for c in node if isinstance(c, list) and head(c) == name]


def kid(node, name):
    got = kids(node, name)
    return got[0] if got else None


def unquote(tok):
    return tok[1:-1] if isinstance(tok, str) and tok.startswith('"') else tok


def load_symbol(name):
    """Return (node, raw_text) for Lib:Symbol from the installed libraries."""
    lib, sym = name.split(":", 1)
    path = lib_file(name)
    text = open(path, encoding="utf-8", errors="replace").read()
    for node in kids(parse(text)[0], "symbol"):
        if unquote(node[1]) == sym:
            start = text.find('(symbol "' + sym + '"')
            return node, _slice(text, start)
    raise KeyError(f"{name} not found in {path}")


def _slice(text, start):
    """Return the balanced s-expression starting at `start`."""
    depth, i, in_str, esc = 0, start, False, False
    while i < len(text):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    raise ValueError("unbalanced s-expression")


def flatten(name):
    """Return (node, text) for a symbol flattened against its (extends BASE).

    eeschema writes derived symbols out in full inside a schematic's
    lib_symbols block, so unit sub-symbol names must be renamed too.
    """
    node, raw = load_symbol(name)
    ext = kid(node, "extends")
    if ext is None:
        return node, raw
    base_name = unquote(ext[1])
    lib = name.split(":")[0]
    base, _ = load_symbol(f"{lib}:{base_name}")
    new_name = name.split(":", 1)[1]
    out = []
    for c in base:
        if isinstance(c, str):
            out.append(c)
        elif head(c) == "symbol":                 # a unit sub-symbol
            c = list(c)
            unit = unquote(c[1])
            if unit.startswith(base_name):
                c[1] = '"' + new_name + unit[len(base_name):] + '"'
            out.append(c)
        elif head(c) != "property":
            out.append(c)
    out[1] = '"' + new_name + '"'
    overrides = {unquote(p[1]): p for p in kids(node, "property")}
    have = {unquote(p[1]): i for i, p in enumerate(out)
            if isinstance(p, list) and head(p) == "property"}
    for key, prop in overrides.items():
        if key in have:
            out[have[key]] = prop
        else:
            out.append(prop)
    for c in node:
        if isinstance(c, list) and head(c) in ("symbol",):   # derived-only units
            out.append(c)
    return out, to_text(out)


def to_text(node, indent=0):
    """Serialize a parsed node back to s-expression text."""
    if not isinstance(node, list):
        return str(node)
    if not any(isinstance(c, list) for c in node):
        return "(" + " ".join(str(c) for c in node) + ")"
    pad = "\t" * (indent + 1)
    parts = []
    for c in node:
        if isinstance(c, list):
            parts.append("\n" + pad + to_text(c, indent + 1))
        else:
            parts.append(" " + str(c))
    return "(" + "".join(parts).lstrip() + ")"


def pins_geo(sym):
    """[{num,name,etype,x,y,angle,length}] with pin geometry, units included."""
    found = []

    def walk(node):
        for c in node:
            if not isinstance(c, list):
                continue
            if head(c) == "pin":
                at = kid(c, "at")
                ln = kid(c, "length")
                num, nam = kid(c, "number"), kid(c, "name")
                found.append({
                    "num": unquote(num[1]) if num else "?",
                    "name": unquote(nam[1]) if nam else "~",
                    "etype": str(c[1]),
                    "x": float(at[1]), "y": float(at[2]),
                    "angle": float(at[3]) if len(at) > 3 else 0.0,
                    "length": float(ln[1]) if ln else 0.0,
                })
            else:
                walk(c)
    walk(sym)
    seen, out = set(), []
    for p in found:
        if p["num"] not in seen:
            seen.add(p["num"])
            out.append(p)
    return out


def pins(sym):
    """[(number, name, etype)] for every pin, including those in nested units."""
    found = []

    def walk(node):
        for c in node:
            if not isinstance(c, list):
                continue
            if head(c) == "pin":
                num, nam = kid(c, "number"), kid(c, "name")
                found.append((unquote(num[1]) if num else "?",
                              unquote(nam[1]) if nam else "",
                              str(c[1])))
            else:
                walk(c)
    walk(sym)
    return sorted(set(found), key=lambda p: p[0])


def search(pattern):
    rx = re.compile(pattern, re.I)
    hits = []
    for fn in sorted(os.listdir(SYMDIR)):
        if not fn.endswith(".kicad_sym"):
            continue
        lib = fn[:-9]
        for node in kids(parse(open(os.path.join(SYMDIR, fn), encoding="utf-8",
                                      errors="replace").read())[0], "symbol"):
            nm = unquote(node[1])
            if rx.search(nm):
                hits.append(f"{lib}:{nm}")
    return hits


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "find":
        print("\n".join(search(sys.argv[2])))
    elif cmd == "pins":
        sym, _ = flatten(sys.argv[2])
        for num, nam, etype in pins(sym):
            print(f"  pin {num:>4}  {nam:<24} {etype}")
    elif cmd == "dump":
        print(flatten(sys.argv[2])[1])

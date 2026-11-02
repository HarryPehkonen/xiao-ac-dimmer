#!/usr/bin/env python3
"""Grid maze router for the generated board (headless, via pcbnew).

KiCad has no autorouter.  This is a small A* over a 0.5 mm grid with two
copper layers and vias, which is enough for a small through-hole board and,
unlike a hand-written coordinate table, survives a placement change.

Obstacles: every footprint's bounding box (inflated by the net's clearance),
earlier routes, and the board edge.  A net's own pads are opened up on the
layer they sit on so the router can actually reach them.  Clearance is
per-net: mains nets keep 3 mm from everything that is not mains, so the DRC
rule and the router agree.

    from route import route
    report = route(board, netitems, nets)
"""
import heapq

import pcbnew

GRID = 0.5                      # mm
W, H = 150.0, 95.0              # mm, board size
MAINS = {"L_IN", "L_FUSED", "N_AC", "LOAD_L", "SNUB_MID", "ZCD_A", "ZCD_B",
         # mains-referenced: the triac gate circuit is on the hot side of the
         # opto, so these carry mains potential and owe logic 3 mm too.
         # Classifying them as signal made them demand 3 mm from the mains
         # zone they live in -- unroutable by construction.
         "MOC_MT2", "TRIAC_G"}

CLEAR_MAINS = 3.0               # mains <-> anything else
CLEAR_MAINS_LOCAL = 1.0         # mains <-> mains (the 3 mm rule is the barrier)
CLEAR_NORMAL = 0.4              # everything <-> everything.  DRC requires
                                # 0.2 mm for the default netclass, but this is
                                # not just that plus slack: the router reasons
                                # about cell centres, so a diagonal run can pass
                                # ~0.4 mm closer to a pad than the cell model
                                # says (measured: 0.25 gave 12 shorts against
                                # no-net pads, 0.5 gave none, 0.4 is the floor).
WIDTH_MAINS = 1.5
WIDTH_POWER = 0.6
WIDTH_SIGNAL = 0.4
VIA_R_MAINS, VIA_R_SIGNAL = 0.5, 0.4     # via copper radius: 1.0 / 0.8 mm
                                   # diameter vias.  Blocking them at the
                                   # *track* half-width left them 0.2 mm
                                   # under-sized and tracks clipped the vias.
VIA_COST = 12                   # in cells, so vias are used deliberately
QUANT = GRID * 0.71             # half a cell diagonal: blocking is per cell
                                # centre, so every radius needs this much
                                # slack or tracks clip pads between cells


def _c(v):
    return int(round(v / GRID))


def _mm(i):
    return i * GRID


class Grid:
    def __init__(self):
        self.nx, self.ny = _c(W) + 1, _c(H) + 1
        self.blocked = [bytearray(self.nx * self.ny), bytearray(self.nx * self.ny)]

    def idx(self, x, y):
        return y * self.nx + x

    def inside(self, x, y):
        return 2 <= x < self.nx - 2 and 2 <= y < self.ny - 2

    def block(self, x, y, layer=None):
        if not (0 <= x < self.nx and 0 <= y < self.ny):
            return
        if layer is None:
            self.blocked[0][self.idx(x, y)] = 1
            self.blocked[1][self.idx(x, y)] = 1
        else:
            self.blocked[layer][self.idx(x, y)] = 1

    def is_blocked(self, x, y, layer):
        return self.blocked[layer][self.idx(x, y)]

    def block_box(self, x0, y0, x1, y1, layer=None):
        for cx in range(_c(x0), _c(x1) + 1):
            for cy in range(_c(y0), _c(y1) + 1):
                self.block(cx, cy, layer)

    def block_disc(self, x0, y0, r, layer=None, clear=False):
        cr = _c(r)
        cx0, cy0 = _c(x0), _c(y0)
        for dx in range(-cr, cr + 1):
            for dy in range(-cr, cr + 1):
                if dx * dx + dy * dy <= cr * cr:
                    if clear:
                        self.unblock(cx0 + dx, cy0 + dy, layer)
                    else:
                        self.block(cx0 + dx, cy0 + dy, layer)

    def unblock(self, x, y, layer=None):
        if not (0 <= x < self.nx and 0 <= y < self.ny):
            return
        if layer is None:
            self.blocked[0][self.idx(x, y)] = 0
            self.blocked[1][self.idx(x, y)] = 0
        else:
            self.blocked[layer][self.idx(x, y)] = 0


def astar(grid, start, goal):
    """start/goal are (x, y, layer).  Returns a path or None."""
    def h(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1]) + 6 * abs(a[2] - b[2])

    openq = [(h(start, goal), 0, start)]
    came, cost = {}, {start: 0}
    while openq:
        _, g, cur = heapq.heappop(openq)
        if cur == goal:
            path = [cur]
            while cur in came:
                cur = came[cur]
                path.append(cur)
            return path[::-1]
        if g > cost.get(cur, 1e18):
            continue
        x, y, layer = cur
        nbrs = []
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if grid.inside(nx, ny) and not grid.is_blocked(nx, ny, layer):
                nbrs.append(((nx, ny, layer), 1))
        other = 1 - layer
        if not grid.is_blocked(x, y, other):
            nbrs.append(((x, y, other), VIA_COST))
        for nxt, w in nbrs:
            ng = g + w
            if ng < cost.get(nxt, 1e18):
                cost[nxt] = ng
                came[nxt] = cur
                heapq.heappush(openq, (ng + h(nxt, goal), ng, nxt))
    return None


def _pad_half(pad):
    size = pad.GetSize()
    return max(pcbnew.ToMM(size.x), pcbnew.ToMM(size.y)) / 2


def _pad_disc(pad, grid, layer, clear):
    """Block (or clear) exactly the same disc for a pad.  Clearing a smaller
    disc than was blocked leaves a ring around the pad and it cannot route out;
    clearing a larger one opens the neighbouring pad up to a short."""
    p = pad.GetPosition()
    r = _pad_half(pad) + CLEAR_NORMAL + WIDTH_SIGNAL / 2 + QUANT
    grid.block_disc(pcbnew.ToMM(p.x), pcbnew.ToMM(p.y), r, layer, clear=clear)


def _to_segments(path):
    """Merge collinear grid steps into single track segments.

    One PCB_TRACK per 0.5 mm grid step produced 2,161 segments for 16 nets --
    file bloat, slow DRC, and a board nobody can read.  Merge runs instead.
    """
    segs, start, d0 = [], path[0], None
    for a, b in zip(path, path[1:]):
        if a[2] != b[2]:                      # layer change closes the run
            if d0 is not None:
                segs.append((start, a))
            start, d0 = b, None
            continue
        d = (b[0] - a[0], b[1] - a[1])
        if d0 is not None and d != d0:
            segs.append((start, a))
            start = a
        d0 = d
    if d0 is not None:
        segs.append((start, path[-1]))
    return segs


def _diagnose(grid, pad, mine, all_pads, vetoes):
    """Why a pad cannot be reached: how its opening survives the vetoes.

    Returns a short string for the failure message.  Guessing at placement
    changes without this wasted several rounds.
    """
    p = pad.GetPosition()
    cx0, cy0 = _c(pcbnew.ToMM(p.x)), _c(pcbnew.ToMM(p.y))
    cr = _c(_pad_half(pad) + CLEAR_NORMAL + WIDTH_SIGNAL / 2 + QUANT)
    veto = [(pcbnew.ToMM(q.GetPosition().x), pcbnew.ToMM(q.GetPosition().y),
             _pad_half(q) + CLEAR_NORMAL + WIDTH_SIGNAL / 2 + QUANT)
            for q, key in all_pads if key not in mine]
    tot = padveto = 0
    cop = [0, 0]
    free = [0, 0]
    for dx in range(-cr, cr + 1):
        for dy in range(-cr, cr + 1):
            if dx * dx + dy * dy > cr * cr:
                continue
            tot += 1
            mx, my = _mm(cx0 + dx), _mm(cy0 + dy)
            if any((mx - vx) ** 2 + (my - vy) ** 2 <= vr * vr
                   for vx, vy, vr in veto):
                padveto += 1
                continue
            for l in (0, 1):
                if any(v.is_blocked(cx0 + dx, cy0 + dy, l) for v in vetoes):
                    cop[l] += 1
                else:
                    free[l] += 1
    return (f"cells={tot} pad-veto={padveto} copper-veto L0={cop[0]}/L1={cop[1]} "
            f"free L0={free[0]}/L1={free[1]}")


def _open(grid, pad, mine, all_pads, vetoes):
    """Make a net's own pad reachable without opening a hole over a neighbour.

    A pad's keepout disc overlaps the next pad's at 2.54 mm pitch, so simply
    clearing around my pad would free cells that sit on someone else's copper.
    Every other pad therefore vetoes the cells it owns.
    """
    veto = [(pcbnew.ToMM(q.GetPosition().x), pcbnew.ToMM(q.GetPosition().y),
             _pad_half(q) + CLEAR_NORMAL + WIDTH_SIGNAL / 2 + QUANT)
            for q, key in all_pads if key not in mine]
    p = pad.GetPosition()
    mx0, my0 = pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)
    cx0, cy0 = _c(mx0), _c(my0)
    cr = _c(_pad_half(pad) + CLEAR_NORMAL + WIDTH_SIGNAL / 2 + QUANT)
    # an escape spoke perpendicular to the pin row.  A pad in a 2.54 mm column
    # has most of its opening vetoed by its own neighbours (measured: 21 of 49
    # cells, leaving a sliver that does not reach open space), so every pad
    # gets a channel out sideways.
    near = None
    for q, key in all_pads:
        if key in mine:
            continue
        qx, qy = pcbnew.ToMM(q.GetPosition().x), pcbnew.ToMM(q.GetPosition().y)
        ddx, ddy = qx - mx0, qy - my0
        dist = (ddx * ddx + ddy * ddy) ** 0.5
        if 0 < dist < 4.0 and (near is None or dist < near[0]):
            near = (dist, ddx / dist, ddy / dist)

    for dx in range(-cr, cr + 1):
        for dy in range(-cr, cr + 1):
            if dx * dx + dy * dy > cr * cr:
                continue
            mx, my = _mm(cx0 + dx), _mm(cy0 + dy)
            if any((mx - vx) ** 2 + (my - vy) ** 2 <= vr * vr
                   for vx, vy, vr in veto):
                continue
            # per layer: copper on the other layer is no obstacle here
            cx, cy = cx0 + dx, cy0 + dy
            if not any(v.is_blocked(cx, cy, 0) for v in vetoes):
                grid.unblock(cx, cy, 0)
            if not any(v.is_blocked(cx, cy, 1) for v in vetoes):
                grid.unblock(cx, cy, 1)

    if near is not None:
        ux, uy = -near[2], near[1]          # perpendicular to the neighbour
        for sgn in (1, -1):
            for k in range(1, cr + 2):
                cx = cx0 + int(round(sgn * ux * k))
                cy = cy0 + int(round(sgn * uy * k))
                mx, my = _mm(cx), _mm(cy)
                if any((mx - vx) ** 2 + (my - vy) ** 2 <= vr * vr
                       for vx, vy, vr in veto):
                    break                    # runs into another pad: stop
                for l in (0, 1):
                    if not any(v.is_blocked(cx, cy, l) for v in vetoes):
                        grid.unblock(cx, cy, l)


def route(board, netitems, nets, verbose=True):
    """Route every net.  Returns {'routed': n, 'failed': {net: reason}}."""
    g_sig, g_mains = Grid(), Grid()        # keepout the active net obeys
    # Four records of routed copper, one per (copper class, consumer class)
    # clearance pair, so that opening a pad never shaves the outer ring off an
    # earlier route's clearance and never over-vetoes a pad either.
    cop_m2m, cop_m2s = Grid(), Grid()      # mains copper, for mains / logic
    cop_s2s, cop_s2m = Grid(), Grid()      # signal copper, for logic / mains

    # Copper, not bodies, is what matters: block every pad inflated by a
    # generous radius, on both layers.  Blocking whole footprint bounding
    # boxes instead traps a pad inside its own box and nothing routes.
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            _pad_disc(pad, g_sig, None, clear=False)
            _pad_disc(pad, g_mains, None, clear=False)

    def span(n):
        """Shortest pad-to-pad hop in the net: short nets route first, while
        there is still room, instead of being walled in by the long ones."""
        ps = _pads(board, n)
        if len(ps) < 2:
            return 0
        best = None
        for i, a in enumerate(ps):
            for b in ps[i + 1:]:
                pa, pb = a.GetPosition(), b.GetPosition()
                d = ((pa.x - pb.x) ** 2 + (pa.y - pb.y) ** 2) ** 0.5
                best = d if best is None else min(best, d)
        return best

    order = sorted(nets, key=lambda n: (n not in MAINS, len(nets[n]) > 2,
                                        span(n)))
    failed = {}
    routed = 0
    all_pads = []

    for fp in board.GetFootprints():
        for pad in fp.Pads():
            all_pads.append((pad, (fp.GetReference(), pad.GetNumber())))

    for net in order:
        pads = [p for p in _pads(board, net)]
        if len(pads) < 2:
            continue
        mains = net in MAINS
        width = (WIDTH_MAINS if mains else
                 WIDTH_POWER if net in ("GND", "+5V_PS", "+5V_XIAO", "+3V3")
                 else WIDTH_SIGNAL)
        clear = CLEAR_MAINS if mains else CLEAR_NORMAL
        half = width / 2
        # Two occupancy grids: g_sig holds what a *logic* net must avoid (mains
        # copper plus the barrier), g_mains what a *mains* net must avoid.  One
        # grid would fence the mains nets off from each other by their own 3 mm
        # keepout and nothing in the mains zone would route.
        grid = g_mains if mains else g_sig
        own = CLEAR_MAINS_LOCAL if mains else CLEAR_NORMAL
        via_r = VIA_R_MAINS if mains else VIA_R_SIGNAL

        # every pad keeps its keepout; this net's own pads are then opened --
        # re-asserting first means an earlier net cannot have left a hole
        for q, _key in all_pads:
            _pad_disc(q, grid, None, clear=False)
        mine = {(p.GetParentFootprint().GetReference(), p.GetNumber())
                for p in pads}
        for pad in pads:
            _open(grid, pad, mine, all_pads,
                  (cop_m2m, cop_s2m) if mains else (cop_m2s, cop_s2s))

        ok = True
        segs, vias = [], []
        anchor = pads[0]
        for pad in pads[1:]:
            s = (_c(pcbnew.ToMM(anchor.GetPosition().x)),
                 _c(pcbnew.ToMM(anchor.GetPosition().y)), 0)
            g = (_c(pcbnew.ToMM(pad.GetPosition().x)),
                 _c(pcbnew.ToMM(pad.GetPosition().y)), 0)
            grid.unblock(s[0], s[1], None)
            grid.unblock(g[0], g[1], None)
            path = astar(grid, s, g)
            if path is None:
                vet = (cop_m2m, cop_s2m) if mains else (cop_m2s, cop_s2s)
                why = _diagnose(grid, pad, mine, all_pads, vet)
                failed[net] = (f"no path {_ref(anchor)}.{anchor.GetNumber()}"
                               f" -> {_ref(pad)}.{pad.GetNumber()} [{why}]")
                ok = False
                break
            for i, (prev, cur) in enumerate(zip(path, path[1:])):
                if prev[2] != cur[2]:
                    if i < 2 or i > len(path) - 3:
                        continue        # a pad already joins the two layers,
                                        # and a via on top of a pad's hole
                                        # breaks the hole-to-hole rule
                    vias.append((cur[0], cur[1]))
                    via = pcbnew.PCB_VIA(board)
                    via.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(_mm(cur[0])),
                                                    pcbnew.FromMM(_mm(cur[1]))))
                    via.SetWidth(pcbnew.FromMM(0.8 if not mains else 1.0))
                    via.SetDrill(pcbnew.FromMM(0.4 if not mains else 0.5))
                    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                    via.SetNet(netitems[net])
                    board.Add(via)
            for a, b in _to_segments(path):
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(_mm(a[0])),
                                           pcbnew.FromMM(_mm(a[1]))))
                t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(_mm(b[0])),
                                         pcbnew.FromMM(_mm(b[1]))))
                t.SetWidth(pcbnew.FromMM(width))
                t.SetLayer(pcbnew.F_Cu if a[2] == 0 else pcbnew.B_Cu)
                t.SetNet(netitems[net])
                board.Add(t)
            segs.extend(path)
            anchor = pad
        # the new copper becomes an obstacle for later nets, on the layer it
        # sits on; a via blocks both.  Each grid takes the clearance this net
        # owes the other class.
        for g, r in ((g_sig, clear), (g_mains, own)):
            for x, y, l in segs:
                g.block_disc(_mm(x), _mm(y), half + r + QUANT, l)
            for x, y in vias:
                g.block_disc(_mm(x), _mm(y), max(half, via_r) + r + QUANT)

        # record the new copper at the spacing it owes each class
        for g, r in ((cop_m2m, CLEAR_MAINS_LOCAL), (cop_m2s, CLEAR_MAINS)) \
                if mains else ((cop_s2s, CLEAR_NORMAL), (cop_s2m, CLEAR_MAINS)):
            for x, y, l in segs:
                g.block_disc(_mm(x), _mm(y), half + r + QUANT, l)
            for x, y in vias:
                g.block_disc(_mm(x), _mm(y), max(half, via_r) + r + QUANT)

        # close the net's own pads again, inflated by this net's clearance
        for pad in pads:
            p = pad.GetPosition()
            for g, r in ((g_sig, clear), (g_mains, own)):
                g.block_disc(pcbnew.ToMM(p.x), pcbnew.ToMM(p.y),
                             _pad_half(pad) + r + half + QUANT)
        if ok:
            routed += 1
    if verbose:
        print(f"routed {routed}/{len(nets)} nets"
              + (f", failed: {failed}" if failed else ""))
    return {"routed": routed, "failed": failed}


def _ref(pad):
    try:
        return pad.GetParentFootprint().GetReference()
    except AttributeError:
        return "?"


def _pads(board, net):
    """Pads of a net, in a stable order (schematic order would be nicer, but
    footprint order keeps re-runs deterministic)."""
    out = []
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        for pad in fp.Pads():
            if pad.GetNetname().lstrip("/") == net:
                out.append(pad)
    return out

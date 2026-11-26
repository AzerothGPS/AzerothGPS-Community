"""worldgrid.walked_links' mesh walks compiled with Numba (optional: `pip install numba`; without it, or with
AGPS_WG_ACCEL=off, worldgrid walks them in Python). The same rules and the same float operations in the same order as
worldgrid.mesh_walk, joined_within and navmesh's _in_poly / _height_on, so the links come out byte-equal
(tests/test_bake_speed.py, and perf/gpu-bake's tile checks). The sets the Python walk iterates (a poly's neighbors, a
cell's polys) are handed over in their own iteration order: a tie goes the same way.

Per tile: the mesh and the cells' surfaces as flat arrays (`pack`), then one call (`links`) for every surface's eight
directions."""

from __future__ import annotations

import math

import numpy as np

try:
    import numba as _nb
except ImportError:  # (an optional speed-up: CI and the other PCs walk in Python)
    _nb = None

AVAILABLE = _nb is not None


def _floordiv(vx, wx):
    """CPython's float // (Objects/floatobject.c float_floor_div): fmod-based, not floor(vx / wx)."""
    mod = float(np.fmod(vx, wx))  # (C's fmod, exact; numba has no math.fmod)
    div = (vx - mod) / wx
    if mod != 0.0:
        if (wx < 0) != (mod < 0):
            div -= 1.0
    if div != 0.0:
        fd = math.floor(div)
        if div - fd > 0.5:
            fd += 1.0
    else:
        fd = math.copysign(0.0, vx / wx)
    return fd


def _split(x):
    t = x * 134217729.0  # (Dekker's split, CPython's dl_split)
    hi = t - (t - x)
    return hi, x - hi


def _vnorm(a, b, mx):
    """CPython's vector_norm (Modules/mathmodule.c) for two values, |a| and |b| <= mx, finite, mx > 0 normal."""
    _m, max_e = math.frexp(mx)
    scale = math.ldexp(1.0, -max_e)
    csum = 1.0
    frac1 = 0.0
    frac2 = 0.0
    for x in (a, b):
        x *= scale
        xh, xl = _split(x)
        p = xh * xh
        q = xh * xl + xl * xh
        z = p + q
        zz = p - z + q + xl * xl
        s = csum + z
        t = (csum - s) + z
        csum = s
        frac1 += zz
        frac2 += t
    h = math.sqrt(csum - 1.0 + (frac1 + frac2))
    xh, xl = _split(-h)
    yh, yl = _split(h)
    p = xh * yh
    q = xh * yl + xl * yh
    z = p + q
    zz = p - z + q + xl * yl
    s = csum + z
    t = (csum - s) + z
    csum = s
    frac1 += zz
    frac2 += t
    x = csum - 1.0 + (frac1 + frac2)
    h += x / (2.0 * h)
    return h / scale


def _hypot(x, y):
    """CPython's math.hypot of two, to the last bit (a walk's length and step are the Python walk's)."""
    x = abs(x)
    y = abs(y)
    if math.isnan(x) or math.isnan(y):
        if math.isinf(x) or math.isinf(y):
            return math.inf
        return math.nan
    mx = max(x, y)
    if math.isinf(mx):
        return mx
    if mx == 0.0:
        return mx
    _m, e = math.frexp(mx)
    if e < -1023:
        dmin = 2.2250738585072014e-308
        return dmin * _vnorm(x / dmin, y / dmin, mx / dmin)
    return _vnorm(x, y, mx)


def _in_poly(vs0, vs1, vx, vy, x, y):
    sign = 0
    n = vs1 - vs0
    for k in range(n):
        o = vs0 + k
        a = vs0 + (k + 1) % n
        c = (vx[a] - vx[o]) * (y - vy[o]) - (vy[a] - vy[o]) * (x - vx[o])
        if abs(c) < 1e-9:
            continue
        s = 1 if c > 0 else -1
        if sign == 0:
            sign = s
        elif s != sign:
            return False
    return True


def _height_on(vs0, vs1, vx, vy, vz, x, y):
    n = vs1 - vs0
    for k in range(1, n - 1):
        a = vs0
        b = vs0 + k
        c = vs0 + k + 1
        det = (vy[b] - vy[c]) * (vx[a] - vx[c]) + (vx[c] - vx[b]) * (vy[a] - vy[c])
        if abs(det) < 1e-9:
            continue
        l1 = ((vy[b] - vy[c]) * (x - vx[c]) + (vx[c] - vx[b]) * (y - vy[c])) / det
        l2 = ((vy[c] - vy[a]) * (x - vx[c]) + (vx[a] - vx[c]) * (y - vy[c])) / det
        l3 = 1 - l1 - l2
        if min(l1, l2, l3) >= -1e-6:
            return l1 * vz[a] + l2 * vz[b] + l3 * vz[c]
    best = vs0
    bd = (vx[vs0] - x) ** 2 + (vy[vs0] - y) ** 2
    for q in range(vs0 + 1, vs1):
        d = (vx[q] - x) ** 2 + (vy[q] - y) ** 2
        if d < bd:
            best, bd = q, d
    return vz[best]


def _dist2_poly(vs0, vs1, vx, vy, x, y):
    """navmesh._dist2_poly: the squared distance to the poly's nearest point (_closest_on_poly, _closest_seg)."""
    n = vs1 - vs0
    got = False
    bd = 0.0
    bpx = 0.0
    bpy = 0.0
    for k in range(n):
        a = vs0 + k
        b = vs0 + (k + 1) % n
        wx = vx[b] - vx[a]
        wy = vy[b] - vy[a]
        L2 = wx * wx + wy * wy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - vx[a]) * wx + (y - vy[a]) * wy) / L2))
        px = vx[a] + wx * t
        py = vy[a] + wy * t
        d = (px - x) ** 2 + (py - y) ** 2
        if not got or d < bd:
            bd, bpx, bpy, got = d, px, py, True
    return (bpx - x) ** 2 + (bpy - y) ** 2


def _poly_at(s, pstart, pids, vstart, vx, vy, vz, x, y, z):
    """worldgrid._poly_at over the surface's polys (in their set's order)."""
    best = -1
    bk0 = 0
    bk1 = 0.0
    for r in range(pstart[s], pstart[s + 1]):
        p = pids[r]
        v0 = vstart[p]
        v1 = vstart[p + 1]
        if _in_poly(v0, v1, vx, vy, x, y):
            k0 = 0
            k1 = abs(_height_on(v0, v1, vx, vy, vz, x, y) - z)
        else:
            k0 = 1
            k1 = _dist2_poly(v0, v1, vx, vy, x, y)
        if best < 0 or k0 < bk0 or (k0 == bk0 and k1 < bk1):
            best, bk0, bk1 = p, k0, k1
    return best


def _sign(vs0, vs1, vx, vy):
    n = vs1 - vs0
    area = 0.0
    for k in range(n):
        a = vs0 + k
        b = vs0 + (k + 1) % n
        area += vx[a] * vy[b] - vx[b] * vy[a]
    return 1.0 if area >= 0 else -1.0


def _inside(q, box, vstart, vx, vy, x, y):
    return (box[q, 0] - 1e-6 <= x <= box[q, 2] + 1e-6 and box[q, 1] - 1e-6 <= y <= box[q, 3] + 1e-6
            and _in_poly(vstart[q], vstart[q + 1], vx, vy, x, y))


def _near_cell(x, y, x0, y0, cell, n):
    i = int(_floordiv(x - x0, cell))
    j = int(_floordiv(y - y0, cell))
    if 0 <= i < n and 0 <= j < n:
        return i * n + j
    return -1


def _clear_over(c, px, py, hq, h, nstart, npolys, box, vstart, vx, vy, vz, drop_min, clear_z):
    """worldgrid._clear_over: no poly of cell c's at (px, py) between hq + clear_z and h + clear_z."""
    if c < 0:
        return True
    for r in range(nstart[c], nstart[c + 1]):
        q = npolys[r]
        if _inside(q, box, vstart, vx, vy, px, py):
            hz = _height_on(vstart[q], vstart[q + 1], vx, vy, vz, px, py)
            if hq + clear_z < hz < h + clear_z:
                return False
    return True


def _mesh_walk(ax, ay, az, pid0, bx, by, tmark, tstamp, tz, drop_max, vstart, vx, vy, vz, sg, box, estart, ens, nbstart,
               nbs, nstart, npolys, x0, y0, cell, n, drop_min, end_z, scan_yd, scan_min, clear_z, clear_min):
    """worldgrid.mesh_walk: 1 WALK, 2 DROP, 0 none (`tmark[p] == tstamp`: p is one of the target surface's polys)."""
    L = _hypot(bx - ax, by - ay)
    if L < 1e-6:
        return 1
    eps = min(0.02, 0.05 / L)
    cur = pid0
    t = 0.0
    how = 1
    for _ in range(300):
        v0 = vstart[cur]
        v1 = vstart[cur + 1]
        nv = v1 - v0
        sgn = sg[cur]
        best = 2.0
        k = -1
        for e in range(nv):
            a = v0 + e
            b = v0 + (e + 1) % nv
            c0 = sgn * ((vx[b] - vx[a]) * (ay - vy[a]) - (vy[b] - vy[a]) * (ax - vx[a]))
            c1 = sgn * ((vx[b] - vx[a]) * (by - vy[a]) - (vy[b] - vy[a]) * (bx - vx[a]))
            if c1 < c0 and c1 < 0:
                tt = c0 / (c0 - c1)
                if tt >= t - 1e-7 and tt < best:
                    best = tt
                    k = e
        te = best
        if te >= 1.0 or k < 0:
            if tmark[cur] == tstamp:
                return how
            # (or one joined to the surface's polys within two links at about its height: worldgrid.mesh_walk's)
            if abs(_height_on(v0, v1, vx, vy, vz, bx, by) - tz) <= end_z:
                for r1 in range(nbstart[cur], nbstart[cur + 1]):
                    q1 = nbs[r1]
                    if tmark[q1] == tstamp:
                        return how
                    for r2 in range(nbstart[q1], nbstart[q1 + 1]):
                        if tmark[nbs[r2]] == tstamp:
                            return how
            return 0
        hx = ax + (bx - ax) * te
        hy = ay + (by - ay) * te
        h = _height_on(v0, v1, vx, vy, vz, hx, hy)
        t = te + eps
        yx = ax + (bx - ax) * t
        yy = ay + (by - ay) * t
        nxt = -1
        ne = estart[cur + 1] - estart[cur]
        e = ens[estart[cur] + k] if k < ne else -2
        if e >= 0:
            nxt = e
        elif e == -2:
            found = False
            bestd = 0.0
            for r in range(nbstart[cur], nbstart[cur + 1]):
                q = nbs[r]
                if _inside(q, box, vstart, vx, vy, yx, yy):
                    d = abs(_height_on(vstart[q], vstart[q + 1], vx, vy, vz, yx, yy) - h)
                    if not found or d < bestd:
                        nxt = q
                        bestd = d
                        found = True
            if nxt < 0:
                for r1 in range(nbstart[cur], nbstart[cur + 1]):
                    r = nbs[r1]
                    for r2 in range(nbstart[r], nbstart[r + 1]):
                        q = nbs[r2]
                        if q != cur and _inside(q, box, vstart, vx, vy, yx, yy) and abs(
                                _height_on(vstart[q], vstart[q + 1], vx, vy, vz, yx, yy) - h) <= 2.0:
                            nxt = q
                            break
                    if nxt >= 0:
                        break
        if nxt < 0:
            hi = 0.0
            got = False
            c = _near_cell(yx, yy, x0, y0, cell, n)
            if c >= 0:
                for r in range(nstart[c], nstart[c + 1]):
                    q = npolys[r]
                    if q == cur:
                        continue
                    if not _inside(q, box, vstart, vx, vy, yx, yy):
                        continue
                    hq = _height_on(vstart[q], vstart[q + 1], vx, vy, vz, yx, yy)
                    if drop_min <= h - hq <= drop_max and (not got or hq > hi):
                        nxt = q
                        hi = hq
                        got = True
                if got and h - hi >= clear_min and not _clear_over(c, yx, yy, hi, h, nstart, npolys, box, vstart, vx, vy, vz, drop_min,
                                           clear_z):
                    return 0
            if nxt < 0 and drop_max >= scan_min:
                # (on along the line: a sheer cliff's foot, worldgrid.DROP_SCAN_*)
                for m in range(1, int(scan_yd / 0.5) + 1):
                    ts = te + m * 0.5 / L
                    if ts >= 1.0:
                        break
                    px = ax + (bx - ax) * ts
                    py = ay + (by - ay) * ts
                    c2 = _near_cell(px, py, x0, y0, cell, n)
                    if c2 >= 0:
                        for r in range(nstart[c2], nstart[c2 + 1]):
                            q = npolys[r]
                            if q == cur or not _inside(q, box, vstart, vx, vy, px, py):
                                continue
                            hq = _height_on(vstart[q], vstart[q + 1], vx, vy, vz, px, py)
                            if scan_min <= h - hq <= drop_max and (not got or hq > hi):
                                nxt = q
                                hi = hq
                                got = True
                    if nxt >= 0:
                        if h - hi >= clear_min and not _clear_over(c2, px, py, hi, h, nstart, npolys, box, vstart, vx, vy, vz, drop_min,
                                           clear_z):
                            return 0
                        t = ts + eps
                        break
            if nxt < 0:
                return 0
            how = 2
        cur = nxt
    return 0


def _joined_within(s, t, pstart, pids, ci, cj, dx, dy, n, nstart, npolys, nbstart, nbs, amark, bmark, smark, stamp,
                   front):
    """worldgrid.joined_within over the polys of cells (ci, cj), its neighbor that way and the two beside (allowed)."""
    for r in range(pstart[t], pstart[t + 1]):
        bmark[pids[r]] = stamp
    for r in range(pstart[s], pstart[s + 1]):
        if bmark[pids[r]] == stamp:
            return True
    for (a, b) in ((ci, cj), (ci + dx, cj + dy), (ci + dx, cj), (ci, cj + dy)):
        if 0 <= a < n and 0 <= b < n:
            c = a * n + b
            for r in range(nstart[c], nstart[c + 1]):
                amark[npolys[r]] = stamp
    nf = 0
    for r in range(pstart[s], pstart[s + 1]):
        p = pids[r]
        if amark[p] == stamp and smark[p] != stamp:
            smark[p] = stamp
            front[nf] = p
            nf += 1
    while nf > 0:
        nf -= 1
        p = front[nf]
        for r in range(nbstart[p], nbstart[p + 1]):
            q = nbs[r]
            if bmark[q] == stamp:
                return True
            if amark[q] == stamp and smark[q] != stamp:
                smark[q] = stamp
                front[nf] = q
                nf += 1
    return False


def _links(sz, spx, spy, sp0, scell, pstart, pids, cfirst, ccount, n, dirs, up, down, vstart, vx, vy, vz, box, estart,
           ens, nbstart, nbs, nstart, npolys, x0, y0, cell, drop_max, drop_min, end_z, round_z, scan_yd, scan_min,
           clear_z, clear_min):
    """Every surface's row: per direction the neighbor cell's surface (its k there) linked, or -1."""
    npoly = len(vstart) - 1
    sg = np.empty(npoly)
    for p in range(npoly):
        sg[p] = _sign(vstart[p], vstart[p + 1], vx, vy)
    ns = len(sz)
    out = np.full((ns, 8), -1, np.int64)
    tmark = np.zeros(npoly, np.int64)
    amark = np.zeros(npoly, np.int64)
    bmark = np.zeros(npoly, np.int64)
    smark = np.zeros(npoly, np.int64)
    front = np.empty(npoly + 1, np.int64)
    stamp = 0
    for s in range(ns):
        if sp0[s] == -2:  # (worked out here: the surface's start poly)
            sp0[s] = _poly_at(s, pstart, pids, vstart, vx, vy, vz, spx[s], spy[s], sz[s])
    mc = 1
    for c in range(len(ccount)):
        mc = max(mc, ccount[c])
    ck = np.empty(mc, np.int64)
    cd = np.empty(mc)
    for s in range(ns):
        if pstart[s + 1] == pstart[s]:
            continue  # (a swim surface: linked by the water's rule)
        ci = scell[s] // n
        cj = scell[s] % n
        for d in range(8):
            dx = dirs[d, 0]
            dy = dirs[d, 1]
            a = ci + dx
            b = cj + dy
            if not (0 <= a < n and 0 <= b < n):
                continue
            c = a * n + b
            f = cfirst[c]
            cnt = ccount[c]
            if cnt == 0:
                continue
            # (the candidates by height apart, then k: an insertion sort, stable)
            m = 0
            for kk in range(cnt):
                tt = f + kk
                if pstart[tt + 1] == pstart[tt]:
                    continue
                if sz[tt] - sz[s] <= up[d] and sz[s] - sz[tt] <= down[d]:
                    adz = abs(sz[tt] - sz[s])
                    q = m
                    while q > 0 and cd[q - 1] > adz:
                        cd[q] = cd[q - 1]
                        ck[q] = ck[q - 1]
                        q -= 1
                    cd[q] = adz
                    ck[q] = kk
                    m += 1
            best = -1
            drop = -1
            for r in range(m):
                kk = ck[r]
                tt = f + kk
                stamp += 1
                for z in range(pstart[tt], pstart[tt + 1]):
                    tmark[pids[z]] = stamp
                how = _mesh_walk(spx[s], spy[s], sz[s], sp0[s], spx[tt], spy[tt], tmark, stamp, sz[tt], drop_max,
                                 vstart, vx, vy, vz, sg, box, estart, ens, nbstart, nbs, nstart, npolys, x0, y0, cell,
                                 n, drop_min, end_z, scan_yd, scan_min, clear_z, clear_min)
                if how == 0 and cd[r] <= round_z:
                    stamp += 1
                    if _joined_within(s, tt, pstart, pids, ci, cj, dx, dy, n, nstart, npolys, nbstart, nbs, amark,
                                      bmark, smark, stamp, front):
                        how = 1
                if how == 1:
                    best = kk
                    break
                if how == 2 and drop < 0:
                    drop = kk
            out[s, d] = best if best >= 0 else drop
    return out


if AVAILABLE:
    _jit = _nb.njit(cache=True, nogil=True)
    _floordiv = _jit(_floordiv)
    _split = _jit(_split)
    _vnorm = _jit(_vnorm)
    _hypot = _jit(_hypot)
    _in_poly = _jit(_in_poly)
    _height_on = _jit(_height_on)
    _sign = _jit(_sign)
    _dist2_poly = _jit(_dist2_poly)
    _poly_at = _jit(_poly_at)
    _clear_over = _jit(_clear_over)
    _inside = _jit(_inside)
    _near_cell = _jit(_near_cell)
    _mesh_walk = _jit(_mesh_walk)
    _joined_within = _jit(_joined_within)
    _links = _jit(_links)


def _csr(lists):
    start = np.zeros(len(lists) + 1, np.int64)
    if lists:
        start[1:] = np.cumsum([len(v) for v in lists])
    flat = np.fromiter((x for v in lists for x in v), np.int64, int(start[-1]))
    return start, flat


def pack_mesh(mesh) -> dict:
    """The tile's mesh as arrays (worldgrid._Mesh): vertices, boxes, edges' neighbors, polys' neighbors (in their sets'
    own order)."""
    vstart = np.zeros(len(mesh.vs) + 1, np.int64)
    if mesh.vs:
        vstart[1:] = np.cumsum([len(vs) for vs in mesh.vs])
    xyz = np.array([v for vs in mesh.vs for v in vs], np.float64).reshape(-1, 3)
    estart, ens = _csr(mesh.ens)
    nbstart, nbs = _csr([list(s) for s in mesh.nb])
    box = np.array(mesh.box, np.float64).reshape(-1, 4)
    return {"vstart": vstart, "vx": np.ascontiguousarray(xyz[:, 0]), "vy": np.ascontiguousarray(xyz[:, 1]),
            "vz": np.ascontiguousarray(xyz[:, 2]), "box": box, "estart": estart, "ens": ens, "nbstart": nbstart,
            "nbs": nbs}


def links(surf: dict, mesh, cell: float, samples: dict, x0: float, y0: float, dirs, up, down, drop_max,
          drop_min, end_z, round_z, scan_yd=0.0, scan_min=1e9, clear_z=1e9, clear_min=0.0) -> dict:
    """walked_links' first pass (each surface's straight links, before the diagonals' check) from the compiled walk:
    {(i, j, k): row}. Each surface's start poly as worldgrid's pid_of, compiled."""
    n = 0
    for (i, j) in list(samples) + list(surf):
        n = max(n, i + 1, j + 1)
    m = pack_mesh(mesh)
    near = [()] * (n * n)
    for (i, j), got in samples.items():
        if got:
            near[i * n + j] = list({sm[1] for sm in got})  # (the Python walk's set, in its own order)
    nstart, npolys = _csr(near)
    keys = list(surf)
    sz, spx, spy, sp0, scell, plist = [], [], [], [], [], []
    cfirst = np.full(n * n, -1, np.int64)
    ccount = np.zeros(n * n, np.int64)
    for (i, j) in keys:
        ss = surf[(i, j)]
        cfirst[i * n + j] = len(sz)
        ccount[i * n + j] = len(ss)
        for k, s in enumerate(ss):
            sz.append(s[0])
            spx.append(s[2])
            spy.append(s[3])
            sp0.append(-2 if s[1] else -1)  # (-2: _links works out the start poly)
            scell.append(i * n + j)
            plist.append(list(s[1]))
    pstart, pids = _csr(plist)
    out = _links(np.array(sz, np.float64), np.array(spx, np.float64), np.array(spy, np.float64),
                 np.array(sp0, np.int64), np.array(scell, np.int64), pstart, pids, cfirst, ccount, n,
                 np.array(dirs, np.int64), np.array(up, np.float64), np.array(down, np.float64), m["vstart"], m["vx"],
                 m["vy"], m["vz"], m["box"], m["estart"], m["ens"], m["nbstart"], m["nbs"], nstart, npolys, float(x0),
                 float(y0), float(cell), float(drop_max), float(drop_min), float(end_z), float(round_z), float(scan_yd),
                 float(scan_min), float(clear_z), float(clear_min))
    res = {}
    r = 0
    for (i, j) in keys:
        for k in range(len(surf[(i, j)])):
            res[(i, j, k)] = out[r].tolist()
            r += 1
    return res

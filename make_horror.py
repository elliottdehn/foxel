#!/usr/bin/env python3
"""Generate horror.fxl: a rigged eldritch horror monster in FXL, with
an idle animation (tentacle-skirt ripple, writhing arc tentacles).

A lopsided pear-shaped mass of deep-violet flesh standing on a skirt
of eight curling ground tentacles, three more arching from its flanks.
A wide jagged maw of ivory needle teeth gapes across the lower body;
above it one huge acid-green eye and a scatter of smaller mismatched
eyes, each ringed in near-black. Void-dark spikes crown the head and
cluster on one shoulder. Analytic-density technique after
make_spider.py (calibrated ramp, fine grades near iso, hard materials
in separately-placed parts).
"""
import math
import numpy as np

W, H, D = 88, 72, 88
CX, CZ = 43.0, 42.5          # plan-view center; the maw faces +z

g = np.full((W, H, D), '.', dtype='<U1')
dens = np.zeros((W, H, D))   # current alpha per cell, for max-union
halo_ok = np.zeros((W, H, D), bool)

# Fine grades near the iso threshold (127): the ramp writes ~26 alpha
# per voxel, so grades spaced ~7 near iso give marching cubes sub-voxel
# surface resolution instead of terracing (see make_spider.py).
SOLID_ALPHAS = [255, 192, 158, 138, 131]
SHELL_ALPHAS = [124, 117, 110, 104, 97, 92, 86, 80, 74, 68]
SHELL_CHARS = '0123456789'

MATS = {
    'flesh': ('ABCDE', '5A3878'),    # deep violet hide
    'pale':  ('FGHIJ', '8E9E6A'),    # sickly barnacle patches
    'dark':  ('KLMNO', '2A1C38'),    # void-dark spikes + mottle
    'wine':  ('PQRST', '8C3060'),    # bruised magenta tentacle tips
}
ACCENTS = {
    'o': ('1309218C', 140),          # eye liner rings, near-black
    'y': ('B4F03C', 255),            # eye glow, acid green
    'u': ('0C0614', 255),            # pupils
    'f': ('E8DFC8', 255),            # needle teeth, ivory
}
SHELL_RGB = '2A2333'

ALPHA_OF = {'.': 0}
for chars, _rgb in MATS.values():
    for ch, a in zip(chars, SOLID_ALPHAS):
        ALPHA_OF[ch] = a
for ch, a in zip(SHELL_CHARS, SHELL_ALPHAS):
    ALPHA_OF[ch] = a
for ch, (_hex, a) in ACCENTS.items():
    ALPHA_OF[ch] = a

g_eyes = np.full((W, H, D), '.', dtype='<U1')   # glow + pupils, hard
g_maw = np.full((W, H, D), '.', dtype='<U1')    # back wall + teeth, hard

XX, YY, ZZ = np.meshgrid(np.arange(W, dtype=float),
                         np.arange(H, dtype=float),
                         np.arange(D, dtype=float), indexing='ij')


def _region(x0, x1, y0, y1, z0, z1):
    return (slice(max(int(x0), 0), min(int(x1) + 1, W)),
            slice(max(int(y0), 0), min(int(y1) + 1, H)),
            slice(max(int(z0), 0), min(int(z1) + 1, D)))


def blend(a, mat, reg):
    """Density-max union of an analytic alpha field into the grid,
    quantized to the material's solid grades + shared shell grades."""
    chars = np.array(list(MATS[mat][0]) + list(SHELL_CHARS))
    levels = np.array(SOLID_ALPHAS + SHELL_ALPHAS, float)
    a = np.minimum(a, 255.0)
    idx = np.abs(a[..., None] - levels).argmin(-1)
    newa = levels[idx]
    gg, dd, hh = g[reg], dens[reg], halo_ok[reg]
    take = (a >= 4.0) & (newa > dd)
    gg[take] = chars[idx][take]
    dd[take] = newa[take]
    hh[take] = True


def soft_ellipsoid(cx, cy, cz, rx, ry, rz, mat, ramp=26.0):
    reg = _region(cx - rx - 3, cx + rx + 3, cy - ry - 3, cy + ry + 3,
                  cz - rz - 3, cz + rz + 3)
    s = np.sqrt(((XX[reg] - cx) / rx) ** 2 + ((YY[reg] - cy) / ry) ** 2
                + ((ZZ[reg] - cz) / rz) ** 2)
    rm = (rx * ry * rz) ** (1.0 / 3.0)   # s-units -> ~voxels
    blend(127.5 - (s - 1.0) * rm * ramp, mat, reg)


def soft_cone(b, t, r0, r1, mat, ramp=26.0):
    """Analytic tapered capsule-cone from base b to tip t, circular
    cross-section shrinking r0 -> r1, rounded ends."""
    b = np.asarray(b, float)
    t = np.asarray(t, float)
    pad = max(r0, r1) + 3.0
    reg = _region(min(b[0], t[0]) - pad, max(b[0], t[0]) + pad,
                  min(b[1], t[1]) - pad, max(b[1], t[1]) + pad,
                  min(b[2], t[2]) - pad, max(b[2], t[2]) + pad)
    axis = t - b
    L = np.linalg.norm(axis)
    ah = axis / L
    u = np.cross(ah, [0.0, 0.0, 1.0])
    if np.linalg.norm(u) < 0.3:
        u = np.cross(ah, [0.0, 1.0, 0.0])
    u /= np.linalg.norm(u)
    v = np.cross(ah, u)
    px, py, pz = XX[reg] - b[0], YY[reg] - b[1], ZZ[reg] - b[2]
    tpar = (px * ah[0] + py * ah[1] + pz * ah[2]) / L
    tc = np.clip(tpar, 0.0, 1.0)
    r = np.maximum(r0 + (r1 - r0) * tc, 0.3)
    wx, wy, wz = px - ah[0] * tc * L, py - ah[1] * tc * L, pz - ah[2] * tc * L
    lu = (wx * u[0] + wy * u[1] + wz * u[2]) / r
    lv = (wx * v[0] + wy * v[1] + wz * v[2]) / r
    la = (wx * ah[0] + wy * ah[1] + wz * ah[2]) / 0.7
    s = np.sqrt(lu * lu + lv * lv + la * la)
    a = 127.5 - (s - 1.0) * np.maximum(r, 0.5) * ramp
    a = np.where((tpar < -0.25) | (tpar > 1.25), 0.0, a)
    blend(a, mat, reg)


def catmull(pts, samples_per_seg=6):
    """Catmull-Rom sample through the control points."""
    pts = [np.asarray(p, float) for p in pts]
    ext = [pts[0]] + pts + [pts[-1]]
    out = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for tt in np.linspace(0.0, 1.0, samples_per_seg, endpoint=False):
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * tt
                              + (2 * p0 - 5 * p1 + 4 * p2 - p3) * tt ** 2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * tt ** 3))
    out.append(pts[-1])
    return out


def tentacle(pts, r0, r1, mat):
    """Smooth tapered tentacle along a control polyline; overlapping
    capsule-cone segments blend by density max-union. Tip radius stays
    >= ~0.7: thin diagonal soft-cones pinch below iso and disconnect."""
    smp = catmull(pts)
    lens = [np.linalg.norm(smp[i + 1] - smp[i]) for i in range(len(smp) - 1)]
    total = sum(lens)
    acc = 0.0
    for i in range(len(smp) - 1):
        t0, t1 = acc / total, (acc + lens[i]) / total
        acc += lens[i]
        soft_cone(smp[i], smp[i + 1],
                  r0 + (r1 - r0) * t0, r0 + (r1 - r0) * t1, mat)


def recolor(mask, src_mat, dst_mat):
    """Swap material color on already-solid voxels grade-for-grade so
    the surface does not move."""
    for sc, dc in zip(MATS[src_mat][0], MATS[dst_mat][0]):
        m = mask & (g == sc)
        g[m] = dc


def put_part(gp, x, y, z, ch):
    x, y, z = int(round(x)), int(round(y)), int(round(z))
    if 0 <= x < W and 0 <= y < H and 0 <= z < D:
        gp[x, y, z] = ch


# ---- body masses: lopsided pear, leaning slightly --------------------------
soft_ellipsoid(CX, 16, CZ - 0.5, 15.5, 9.0, 14.5, 'flesh')     # base bulge
soft_ellipsoid(CX + 0.5, 26, CZ + 0.5, 14.5, 10.0, 13.5, 'flesh')  # belly
soft_ellipsoid(CX - 0.5, 36, CZ + 0.5, 13.0, 9.5, 12.0, 'flesh')   # midriff
soft_ellipsoid(CX + 0.5, 45, CZ, 11.0, 9.0, 10.5, 'flesh')     # head mass
soft_ellipsoid(CX - 0.5, 53, CZ - 0.5, 8.0, 7.0, 7.5, 'flesh') # crown

UPPER = (CX + 0.5, 45.0, CZ, 11.0, 9.0, 10.5)
MID = (CX - 0.5, 36.0, CZ + 0.5, 13.0, 9.5, 12.0)
CROWN = (CX - 0.5, 53.0, CZ - 0.5, 8.0, 7.0, 7.5)

# ---- tentacle skirt: eight curling ground tentacles ------------------------
tips = []
ground_chains = []             # (hip, knee, tip) per tentacle, for the rig
arc_chains = []
_ground_curves = []            # control points, for the clearance check
GROUND = [   # (angle deg from +z, reach scale, curl sign)
    # all curls swirl the SAME way: alternating signs made neighboring
    # tips drift toward each other and weld (solids < ~3 voxels apart
    # fuse visually AND geodesically — the skin flood crossed between
    # tentacles, so lifting one dragged the next)
    (12, 1.00, 1), (57, 0.88, 1), (98, 0.96, 1), (148, 0.85, 1),
    (198, 1.00, 1), (243, 0.90, 1), (286, 0.97, 1), (333, 0.87, 1),
]
for th_deg, rs, curl in GROUND:
    th = math.radians(th_deg)
    dx, dz = math.sin(th), math.cos(th)
    tx, tz = math.cos(th) * curl, -math.sin(th) * curl
    jit = ((th_deg * 7) % 5) * 0.3          # deterministic irregularity

    def p(rad, drift, y):
        return (CX + dx * rad * rs + tx * drift,
                y, CZ + dz * rad * rs + tz * drift)

    # thinner bases on a wider, lower exit ring: eight tentacles of
    # radius 3.3 on the old tight ring left no gaps — the skirt was
    # BORN welded and only separated halfway out
    pts = [p(9, 0, 10.5), p(15, 2, 5.5 + jit * 0.5), p(21, 5, 2.4),
           p(26, 8.5, 1.5), p(28.5, 12, 3.4 + jit)]
    tentacle(pts, 2.8, 0.85, 'flesh')
    tips.append(np.asarray(pts[-1], float))
    ground_chains.append((pts[1], pts[2], pts[4]))
    _ground_curves.append([np.asarray(q, float) for q in pts])

# adjacent ground tentacles must stay clear of each other beyond the
# base merge — closer than ~3 voxels they weld visually and the skin
# flood crosses, dragging neighbors along in animation
for _i in range(len(_ground_curves)):
    _a = np.array(catmull(_ground_curves[_i]))
    _b = np.array(catmull(_ground_curves[(_i + 1) % len(_ground_curves)]))
    _ta = np.linspace(0, 1, len(_a))
    _tb = np.linspace(0, 1, len(_b))
    _ra = 2.8 + (0.85 - 2.8) * _ta
    _rb = 2.8 + (0.85 - 2.8) * _tb
    _d = np.linalg.norm(_a[:, None, :] - _b[None, :, :], axis=2)
    _gap = _d - _ra[:, None] - _rb[None, :]
    # check everywhere the tentacles are exposed flesh (they exit the
    # body bulge by ~15% along the curve), not just the outer half
    _outer = (_ta[:, None] > 0.15) & (_tb[None, :] > 0.15)
    _min = _gap[_outer].min()
    assert _min >= 2.5, 'tentacles %d/%d weld: gap %.2f' \
        % (_i + 1, (_i + 1) % 8 + 1, _min)

# ---- three arching flank tentacles (asymmetric) ----------------------------
ARCS = [
    # left one rears high above the crown
    ([(CX - 7, 32, CZ + 2), (CX - 12, 40, CZ + 3), (CX - 15.5, 50, CZ),
      (CX - 13, 59, CZ - 4), (CX - 9, 64, CZ - 6)], 2.6, 0.8),
    # right one reaches forward and out like a grasping arm
    ([(CX + 8, 30, CZ - 1), (CX + 15, 33, CZ + 3), (CX + 21, 28, CZ + 7),
      (CX + 25, 21, CZ + 9)], 2.4, 0.8),
    # a shorter one snakes up the back
    ([(CX - 3, 31, CZ - 8), (CX - 6, 38, CZ - 14), (CX - 10, 45, CZ - 17.5)],
     2.2, 0.75),
]
for pts, r0, r1 in ARCS:
    tentacle(pts, r0, r1, 'flesh')
    tips.append(np.asarray(pts[-1], float))
    arc_chains.append((pts[0], pts[len(pts) // 2], pts[-1]))

# ---- void-dark spikes: crown crest + right-shoulder cluster ----------------
HORNS = [   # curved void-dark horns on the crown
    ([(41, 54, 40), (37, 61, 36), (36, 67, 39)], 2.4),
    ([(45, 54, 43), (49, 60, 45), (48, 65, 42)], 2.0),
    ([(42, 55, 45), (41, 61, 48), (43, 65, 47)], 1.6),
    ([(40, 55, 37), (36, 60, 33), (33, 63, 34)], 1.5),
]
for pts, r0 in HORNS:
    tentacle(pts, r0, 0.75, 'dark')   # thinner diagonal tips pinch
                                      # below iso and detach
SPIKES = [
    ((52, 47, 42), (58, 53, 41), 1.2),   # shoulder cluster, right side only
    ((53, 45, 45), (58, 48, 48), 1.0),
    ((51, 49, 45), (54, 55, 47), 0.9),
]
for b, t, r0 in SPIKES:
    soft_cone(b, t, r0, 0.7, 'dark')

# ---- skin variation (recolors preserve the density grade) ------------------
fleck = ((XX * 7 + YY * 13 + ZZ * 5) % 29) < 3
recolor(fleck, 'flesh', 'dark')                       # dark mottle
for pcx, pcy, pcz, pr in ((CX - 9, 14, CZ + 10, 5.0),  # barnacle patches
                          (CX + 11, 20, CZ - 8, 4.2),
                          (CX - 12, 27, CZ - 6, 3.6)):
    patch = ((XX - pcx) ** 2 + (YY - pcy) ** 2 + (ZZ - pcz) ** 2) <= pr ** 2
    recolor(patch, 'flesh', 'pale')
for tp in tips:                                       # bruised tentacle tips
    near = ((XX - tp[0]) ** 2 + (YY - tp[1]) ** 2
            + (ZZ - tp[2]) ** 2) <= 4.5 ** 2
    recolor(near, 'flesh', 'wine')

# ---- eyes: one huge, many small, all ringed in near-black ------------------
def surf_point(mass, th_deg, y):
    cx, cy, cz, rx, ry, rz = mass
    k = math.sqrt(max(1.0 - ((y - cy) / ry) ** 2, 0.05))
    th = math.radians(th_deg)
    return (cx + rx * k * math.sin(th), y, cz + rz * k * math.cos(th)), th


EYES = [   # (mass, angle deg from +z, y, radius)
    (UPPER, 8, 46.0, 3.4),      # the great eye
    (UPPER, -32, 48.0, 1.7),
    (UPPER, 40, 47.0, 1.3),
    (UPPER, -60, 43.5, 1.1),
    (MID, -20, 39.0, 1.5),
    (MID, 33, 38.5, 1.2),
    (MID, 62, 35.5, 1.5),
    (MID, -48, 34.5, 1.0),
    (CROWN, -12, 55.0, 1.4),
    (CROWN, 30, 54.0, 1.0),
]
FLESH_SOLID = list(MATS['flesh'][0])
for mass, th_deg, ey, er in EYES:
    (sx, _, sz), th = surf_point(mass, th_deg, ey)
    ex = sx + math.sin(th) * 0.3
    ez = sz + math.cos(th) * 0.3
    # liner ring: recolor flesh solids around the socket to near-black
    ring = ((XX - ex) ** 2 + (YY - ey) ** 2 + (ZZ - ez) ** 2) \
        <= (er + 1.1) ** 2
    for sc in FLESH_SOLID:
        m = ring & (g == sc)
        g[m] = 'o'
    for x in range(int(ex - er - 1), int(ex + er + 2)):
        for y in range(int(ey - er - 1), int(ey + er + 2)):
            for z in range(int(ez - er - 1), int(ez + er + 2)):
                if (x - ex) ** 2 + (y - ey) ** 2 + (z - ez) ** 2 <= er ** 2:
                    put_part(g_eyes, x, y, z, 'y')
    if er >= 1.3:              # vertical slit pupil on the larger eyes
        slit = 0.9 if er > 2 else 0.6
        for x in range(int(ex - er - 1), int(ex + er + 2)):
            for y in range(int(ey - er - 1), int(ey + er + 2)):
                for z in range(int(ez - er - 1), int(ez + er + 2)):
                    if (x - ex) ** 2 + (y - ey) ** 2 + (z - ez) ** 2 \
                            <= er ** 2 and abs(x - ex) <= slit \
                            and z >= ez + er - 2.2:
                        put_part(g_eyes, x, y, z, 'u')

# ---- the maw: a real carved 3D cavity --------------------------------------
# A soft ellipsoid is SUBTRACTED from the body density (smooth boolean
# difference with the same 26-alpha/voxel ramp), so the mouth is true
# concave geometry: the gums, roof and floor are visible flesh from
# every angle. Teeth are then simply stuck into that flesh as separate
# part geometry — no surface-hugging guards needed.
MX, MY, MZ = CX, 27.0, 58.0
MRX, MRY, MRZ = 12.5, 5.2, 7.0

sE = np.sqrt(((XX - MX) / MRX) ** 2 + ((YY - MY) / MRY) ** 2
             + ((ZZ - MZ) / MRZ) ** 2)
rmE = (MRX * MRY * MRZ) ** (1.0 / 3.0)
cut = np.clip(127.5 + (sE - 1.0) * rmE * 26.0, 0.0, 300.0)
WINE_CHARS = np.array(list(MATS['wine'][0]) + list(SHELL_CHARS))
WINE_LVLS = np.array(SOLID_ALPHAS + SHELL_ALPHAS, float)
lower = (cut < dens) & (dens > 0)
gone = lower & (cut < 66.0)     # deep inside the cavity: air
keep = lower & ~gone            # near the new surface: requantized to
idx = np.abs(np.where(lower, cut, 0.0)[..., None]  # the wine ladder, so
             - WINE_LVLS).argmin(-1)               # the mouth interior
g[keep] = WINE_CHARS[idx][keep]                    # is gum-colored
dens[keep] = WINE_LVLS[idx][keep]
g[gone] = '.'
dens[gone] = 0.0

# bruised gum ring around the opening, and a dark gullet at the back
gum = (sE >= 0.95) & (sE <= 1.45) & (ZZ >= MZ - MRZ - 1)
recolor(gum, 'flesh', 'wine')
recolor(gum, 'pale', 'wine')
g[gum & (g == 'o')] = 'S'       # eye liners that bled onto the lip
throat = (sE <= 1.3) & (ZZ <= 52.5)
recolor(throat, 'wine', 'dark')
recolor(throat, 'flesh', 'dark')


def first_solid(xi, direction, z):
    """Scan from the mouth centerline up (+1) or down (-1) to the
    cavity roof/floor: the first row that is solid flesh again."""
    y = int(round(MY))
    for _ in range(12):
        if dens[xi, y, z] >= 127:
            return y
        y += direction
    return None


# needle teeth: planted straight into the cavity's roof and floor,
# irregular lengths, top and bottom rows interleaved. The two jaws
# live at different depths: above the mouth the face curves back
# (solid roof only at z<=53), below it the belly shelf bulges forward
# (floor at z 54-55) — measured, not assumed.
ti = 0
for tx in np.arange(MX - 10.6, MX + 10.7, 2.2):
    xi = int(round(tx + 0.5 * ((int(tx) * 7) % 3 - 1) * 0.4))
    roof = first_solid(xi, +1, 53)
    floor = first_solid(xi, -1, 54)
    if floor is None:
        floor = first_solid(xi, -1, 53)
    if roof is None or floor is None:
        continue
    gap = roof - floor
    if gap < 4:                 # opening too shallow at the corners
        continue
    top = (ti % 2 == 0)
    ti += 1
    L = 4 + (xi * 13) % 3
    if 6.5 < abs(xi - MX) < 9.5:
        L += 2                  # canines
    L = min(L, gap - 2)         # never bite through the opposite gum
    if top:
        yr, step = roof, -1
        zb, zs_, zt_ = (52, 53), (53, 54), 54   # buried / shaft / tip:
    else:                                       # hangs off the roof and
        yr, step = floor, 1                     # hooks forward
        zb, zs_, zt_ = (54, 55), (54, 55), 54
    rows = [(yr - step, [(xi, zb[0]), (xi, zb[1])]),    # buried in flesh
            (yr, [(xi, zb[0]), (xi, zb[1]), (xi + 1, zb[1])])]
    for k in range(1, L - 1):
        rows.append((yr + step * k, [(xi, zs_[0]), (xi, zs_[1])]))
    rows.append((yr + step * (L - 1), [(xi, zt_)]))
    for y, cells in rows:
        for xt, zt in cells:
            put_part(g_maw, xt, y, zt, 'f')

# ---- rig -------------------------------------------------------------------
# Chains (first bone of each chain is rigid): spine root->chest->head
# articulates the head; root->jaw and root->brow are rigid anchors
# whose seeds claim the mouth and face flesh (all rigid bones share
# the root transform, so contested rigid floods are visually free);
# each tentacle is root->hip (rigid coxa) ->knee->tip.
AVAIL = list('mabcdeghijklnpqrstvwxzUVWXYZ') + list('αβγδεζηθικλ')
JOINTS = {}                    # char -> (name, (x, y, z))
HINTS = {}
BONES = []                     # (name, c1, c2)


def add_joint(name, pos, hint=None):
    ch = AVAIL.pop(0)
    JOINTS[ch] = (name, tuple(int(round(v)) for v in pos))
    if hint:
        HINTS[ch] = hint
    return ch


ROOT = add_joint('root', (CX, 30, CZ))
CHEST = add_joint('chest', (CX, 40, CZ))
HEAD = add_joint('head', (CX, 53, CZ))
JAW = add_joint('jaw', (CX, 23, 49))
BROW = add_joint('brow', (CX, 45, 48))
BONES += [('spine', ROOT, CHEST), ('neck', CHEST, HEAD),
          ('jaw_link', ROOT, JAW), ('brow_link', ROOT, BROW)]
for i, (hip, knee, tip) in enumerate(ground_chains, 1):
    hc = add_joint('hip_t%d' % i, hip)
    kc = add_joint('knee_t%d' % i, knee, '+y')
    tc = add_joint('tip_t%d' % i, tip)
    BONES += [('coxa_t%d' % i, ROOT, hc), ('seg1_t%d' % i, hc, kc),
              ('seg2_t%d' % i, kc, tc)]
ARC_HINTS = ['-x', '+x+z', '-z']
for i, (base, mid, tip) in enumerate(arc_chains, 1):
    bc = add_joint('base_a%d' % i, base)
    mc = add_joint('mid_a%d' % i, mid, ARC_HINTS[i - 1])
    tc = add_joint('tip_a%d' % i, tip)
    BONES += [('root_a%d' % i, ROOT, bc), ('seg1_a%d' % i, bc, mc),
              ('seg2_a%d' % i, mc, tc)]

_color_chars = set(ALPHA_OF) - {'.'}
assert not _color_chars & set(JOINTS), 'joint chars collide with colors'

# ---- emit FXL --------------------------------------------------------------
SOLID = {ch for ch, a in ALPHA_OF.items() if a >= 127}

# borders are reserved for joint markers; only sub-iso shell cloud
# ever reaches them, so blanking is visually free
g[0, :, :] = g[W - 1, :, :] = '.'
g[:, :, 0] = g[:, :, D - 1] = '.'

H_used = 0
for y in range(H):
    if (g[:, y, :] != '.').any():
        H_used = y + 1
layers = []
for y in range(H_used):
    rows = [''.join(g[x, y, z] for x in range(W)) for z in range(D)]
    layers.append(rows)

# Inject sudoku-border joint markers (LANG.md 8). Crowded layers
# (eight knees share y~3) use stacked markers: scan inward from a
# border and drop the marker on the first blank; every cell crossed
# must itself be a marker, or that side is unusable. Stacks keep the
# joint at its EXACT coordinate — the old nudge-to-a-free-slot
# workaround moved joints by up to 2 voxels. Nudging survives only as
# a last resort for slots walled off by shell cloud.
_JS = set(JOINTS)


def _scan(cells):
    for order in (range(len(cells)), range(len(cells) - 1, -1, -1)):
        for i in order:
            if cells[i] == '.':
                return i
            if cells[i] not in _JS:
                break
    return None


for ch, (name, (jx, jy, jz)) in JOINTS.items():
    rows = layers[jy]
    placed = False
    for njx in (jx, jx - 1, jx + 1, jx - 2, jx + 2):
        r = _scan([rows[k][njx] for k in range(D)])
        if r is not None:
            rows[r] = rows[r][:njx] + ch + rows[r][njx + 1:]
            placed = True
            assert njx == jx or r in (0, D - 1), \
                'nudged marker for %s must sit on the border' % name
            break
    assert placed, 'no column-marker slot for %s' % name
    placed = False
    for njz in (jz, jz - 1, jz + 1, jz - 2, jz + 2):
        cells = list(rows[njz])
        if jx >= CX:
            cells = cells[::-1]
        c = _scan(cells)
        if c is not None:
            c = (W - 1 - c) if jx >= CX else c
            rows[njz] = rows[njz][:c] + ch + rows[njz][c + 1:]
            placed = True
            assert njz == jz or c in (0, W - 1), \
                'nudged marker for %s must sit on the border' % name
            break
    assert placed, 'no row-marker slot for %s' % name
layers = [tuple(rows) for rows in layers]

from collections import Counter
counts = Counter(layers)

out = []
out.append('# horror.fxl -- generated by make_horror.py, do not hand-edit.')
out.append('# %d x %d x %d voxels. Eldritch horror, rigged (%d joints,'
           ' %d bones).' % (W, H_used, D, len(JOINTS), len(BONES)))
out.append('')
for name, (chars, rgb) in MATS.items():
    for ch, a in zip(chars, SOLID_ALPHAS):
        out.append('%s = %s%s  # %s, alpha %d'
                   % (ch, rgb, '' if a == 255 else '%02X' % a, name, a))
for ci, al in enumerate(SHELL_ALPHAS):
    out.append('%s = %s%02X  # density shell %d, alpha %d'
               % (SHELL_CHARS[ci], SHELL_RGB, al, ci + 1, al))
out.append('o = 1309218C hard  # eye liner, near-black')
out.append('y = B4F03C hard  # eye glow, acid green')
out.append('u = 0C0614 hard  # pupil slits')
out.append('f = E8DFC8 hard  # needle teeth, ivory')
out.append('')
out.append('skin elastic')
out.append('')
for ch, (name, _pos) in JOINTS.items():
    out.append('%s = joint %s%s'
               % (ch, name, ' ' + HINTS[ch] if ch in HINTS else ''))
for nm, c1, c2 in BONES:
    out.append('%s = bone %s %s' % (nm, c1, c2))
out.append('')

names = {}
y = 0
while y < H_used:
    rows = layers[y]
    run = 1
    while y + run < H_used and layers[y + run] == rows:
        run += 1
    if counts[rows] > 1 and rows not in names:
        name = 's%d' % (len(names) + 1)
        names[rows] = name
        out.append('%s:  # y=%d' % (name, y))
        out.extend(rows)
        out.append('---')
    if rows in names:
        ref = '*%s' % names[rows]
        if run > 1:
            ref += ' %d' % run
        out.append('%s  # y=%d' % (ref, y))
        out.append('---')
    else:
        out.append('# y=%d' % y)
        out.extend(rows)
        out.append('---')
    y += run


def _part_layers(gp):
    ys = [y for y in range(H) if (gp[:, y, :] != '.').any()]
    y0 = min(ys)
    pls = []
    for y in range(y0, max(ys) + 1):
        pls.append([''.join(gp[x, y, z] for x in range(W))
                    for z in range(D)])
    return y0, pls


place_lines = []
for pname, gp in (('eyes', g_eyes), ('maw', g_maw)):
    py0, plyrs = _part_layers(gp)
    out.append('model %s:  # placed at y=%d' % (pname, py0))
    for rows in plyrs:
        out.extend(rows)
        out.append('---')
    place_lines.append('place %s +0 +%d +0' % (pname, py0))
out.extend(place_lines)
out.append('')

# idle: restless fidgeting — a ripple runs around the tentacle skirt
# (each tip lifts, curls inward, waggles and re-plants in turn, offset
# by 1/8 of the loop), the arc tentacles writhe continuously, the body
# bobs and the head sways on top.


def kf(pct, joint, dx, dy, dz, ease=''):
    out.append('%g%%: %s %+g %+g %+g%s'
               % (round(pct % 100.0, 2), joint, round(dx, 2), round(dy, 2),
                  round(dz, 2), ' ' + ease if ease else ''))


out.append('anim idle 4.2s loop:')
kf(0, 'root', 0, 0, 0)
kf(25, 'root', 0.4, -0.5, 0)
kf(50, 'root', 0, -0.9, 0)
kf(75, 'root', -0.4, -0.5, 0)
kf(0, 'chest', 0, 0, 0)
kf(0, 'head', 0, 0, 0)
kf(30, 'head', 1.8, -0.7, 0.6)
kf(65, 'head', -1.8, -0.7, -0.5)
for i, (th_deg, rs, curl) in enumerate(GROUND, 1):
    th = math.radians(th_deg)
    ox, oz = math.sin(th), math.cos(th)          # outward radial
    tx_, tz_ = math.cos(th) * curl, -math.sin(th) * curl   # tangential
    p0 = (i - 1) * 12.5
    name = 'tip_t%d' % i
    kf(p0, name, 0, 0, 0)                        # planted
    kf(p0 + 6, name,                             # big lift, curling in
       -ox * 3.2 + tx_ * 1.5, 5.5, -oz * 3.2 + tz_ * 1.5, 'ease-out')
    kf(p0 + 12, name,                            # waggle across
       tx_ * 4.0 - ox * 1.0, 3.5, tz_ * 4.0 - oz * 1.0)
    kf(p0 + 18, name,                            # sweep back out
       -tx_ * 2.5 + ox * 1.5, 2.0, -tz_ * 2.5 + oz * 1.5)
    kf(p0 + 24, name, 0, 0, 0, 'ease-out')       # re-plant
# arc tentacles: continuous writhing
kf(0, 'tip_a1', 0, 0, 0)
kf(18, 'tip_a1', 4.5, 2.0, 3.0)
kf(42, 'tip_a1', -4.0, 3.5, -2.5)
kf(68, 'tip_a1', 2.5, -1.2, 1.5)
kf(86, 'tip_a1', -1.5, 1.5, -1.0)
kf(0, 'tip_a2', 0, 0, 0)
kf(14, 'tip_a2', 2.5, 4.5, 3.0, 'ease-out')      # grasp up
kf(30, 'tip_a2', 0.8, 1.0, 6.0)                  # reach far forward
kf(46, 'tip_a2', 0, 0, 0)
kf(62, 'tip_a2', 3.5, 4.5, 1.5)                  # second grab
kf(80, 'tip_a2', 0, 0, 0, 'ease-out')
kf(0, 'tip_a3', 0, 0, 0)
kf(22, 'tip_a3', -3.0, 2.5, -2.0)
kf(50, 'tip_a3', 2.5, 3.5, -1.0)
kf(76, 'tip_a3', -1.2, 1.2, 1.2)
out.append('')

with open('horror.fxl', 'w') as f:
    f.write('\n'.join(out) + '\n')

n = int(np.isin(g, list(SOLID)).sum())
print('horror.fxl: %d solid voxels, %d layers (%d unique, %d shared defs)'
      % (n, H_used, len(counts), len(names)))

# Disconnected things must stay disconnected (AGENTS.md).
import sys
sys.path.insert(0, 'foxel')
import render as _render
_pal, _scene, _rig = _render.parse_fxl('horror.fxl')
_touching = _render.check_part_clearance(_pal, _scene)
assert not _touching, 'accessory parts touch: %s' % _touching
print('part clearance OK')

#!/usr/bin/env python3
"""Generate goblin.fxl: a rigged goblin with a walk cycle, in FXL.

Green skin smoothed by the graded density shells; crisp claws and
fangs opt out of the shells; eye sockets and mouth are carved after
the shell pass. Rig: 20 joints / 19 bones, waddling walk animation.
"""
import numpy as np

W, H, D = 45, 66, 24
CX, CZ = 22, 11

g = np.full((W, H, D), '.', dtype='<U1')
halo_ok = np.zeros((W, H, D), bool)

# Composed parts: materialized separately from the body (LANG.md 7).
gk = np.full((W, H, D), '.', dtype='<U1')   # kilt + rope
gt = np.full((W, H, D), '.', dtype='<U1')   # teeth + gums + mouth wall
ge = np.full((W, H, D), '.', dtype='<U1')   # eyes: liners + glow
gb = np.full((W, H, D), '.', dtype='<U1')   # wrist bands


def put_part(gp, x, y, z, ch):
    x, y, z = int(round(x)), int(round(y)), int(round(z))
    if 0 <= x < W and 0 <= y < H and 0 <= z < D:
        gp[x, y, z] = ch

SOLID = set('gGerbtysRvö')
PROTECT = set('tys')      # never carved

SHELL_ALPHAS = [104, 92, 80, 68, 56, 44, 33, 22, 12, 5]
SHELL_CHARS = '0123456789'
ALPHA_OF = {'g': 255, 'G': 192, 'e': 158, 'r': 131, 'b': 255,
            't': 255, 'y': 255, 's': 200, 'R': 255,
            'v': 255, 'ö': 255, '.': 0}
for _c, _a in zip(SHELL_CHARS, SHELL_ALPHAS):
    ALPHA_OF[_c] = _a
LADDER = [(255, 'g'), (192, 'G'), (158, 'e'), (131, 'r')] +     list(zip(SHELL_ALPHAS, SHELL_CHARS))


def put(x, y, z, ch, halo=True):
    x, y, z = int(round(x)), int(round(y)), int(round(z))
    if 0 <= x < W and 0 <= y < H and 0 <= z < D:
        g[x, y, z] = ch
        halo_ok[x, y, z] = halo


def knob(x, y, z):
    for dx, dz in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)):
        put(x + dx, y, z + dz, 'g')
    for dx, dz in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        put(x + dx, y, z + dz, 'G')


def long_bone(x, y0, y1, z):
    for yy in (y0, y0 + 1):
        knob(x, yy, z)
    for yy in range(y0 + 2, y1 - 1):
        put(x, yy, z, 'g')
        put(x - 1, yy, z, 'g')
        put(x + 1, yy, z, 'g')
        put(x, yy, z - 1, 'G')
        put(x, yy, z + 1, 'G')
    for yy in (y1 - 1, y1):
        knob(x, yy, z)


def fill_ellipse(y, cx, cz, rx, rz, ch, halo=True):
    for x in range(W):
        for z in range(D):
            if ((x - cx) / rx) ** 2 + ((z - cz) / rz) ** 2 <= 1.0:
                put(x, y, z, ch, halo)


def ellipsoid(cx, cy, cz, rx, ry, rz, ch, ymin=0, ymax=None):
    for x in range(W):
        for y in range(ymin, ymax if ymax is not None else H):
            for z in range(D):
                if (((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
                        + ((z - cz) / rz) ** 2) <= 1.0:
                    put(x, y, z, ch)


def write_max(x, y, z, ch):
    # borders are reserved for joint markers
    if 1 <= x < W - 1 and 0 <= y < H and 1 <= z < D - 1:
        if ALPHA_OF.get(g[x, y, z], 0) < ALPHA_OF[ch]:
            g[x, y, z] = ch
            halo_ok[x, y, z] = True


def soft_ellipsoid(cx, cy, cz, rx, ry, rz, ymin=0, ymax=None, slope=80.0):
    """Analytic density ellipsoid: alpha ramps smoothly through the whole
    ladder across ~1.5 voxels either side of the surface, so marching
    cubes reconstructs a smooth shape instead of hugging voxel steps."""
    rm = (rx * ry * rz) ** (1.0 / 3.0)
    for x in range(W):
        for y in range(ymin, ymax if ymax is not None else H):
            for z in range(D):
                s = np.sqrt(((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
                            + ((z - cz) / rz) ** 2)
                a = 127.5 - (s - 1.0) * rm * slope / max(rm, 1e-9)
                if a < 4:
                    continue
                best = min(LADDER, key=lambda t: abs(t[0] - min(a, 255)))
                write_max(x, y, z, best[1])


def soft_cone(bx, by, bz, tx, ty, tz, r0u, r0v, r1u, r1v, slope=80.0):
    """Analytic tapered fin from base to tip: elliptical cross-section
    in a frame perpendicular to the axis (u ~ horizontal, v ~ the
    other lateral), shrinking toward the tip, density ramping smoothly
    to a rounded point."""
    b = np.array([bx, by, bz], float)
    tip = np.array([tx, ty, tz], float)
    axis = tip - b
    L = np.linalg.norm(axis)
    ah = axis / L
    u = np.cross(ah, [0.0, 0.0, 1.0])
    if np.linalg.norm(u) < 0.3:
        u = np.cross(ah, [0.0, 1.0, 0.0])
    u /= np.linalg.norm(u)
    v = np.cross(ah, u)
    for x in range(W):
        for y in range(H):
            for z in range(D):
                p = np.array([x, y, z], float)
                t = float((p - b) @ ah) / L
                if t < -0.25 or t > 1.25:
                    continue
                tc = min(max(t, 0.0), 1.0)
                ru = r0u + (r1u - r0u) * tc
                rv = r0v + (r1v - r0v) * tc
                w = p - (b + ah * (tc * L))
                lu = float(w @ u) / max(ru, 0.3)
                lv = float(w @ v) / max(rv, 0.3)
                la = float(w @ ah) / 0.7
                s = np.sqrt(lu * lu + lv * lv + la * la)
                rm = (ru + rv) / 2
                a = 127.5 - (s - 1.0) * max(rm, 0.5) * slope \
                    / max(rm, 0.5)
                if a < 4:
                    continue
                best = min(LADDER, key=lambda q: abs(q[0] - min(a, 255)))
                write_max(x, y, z, best[1])


carve = []


def carve_box(x0, x1, y0, y1, z0, z1):
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            for z in range(z0, z1 + 1):
                carve.append((x, y, z))


# ---- legs and feet ---------------------------------------------------------
for side in (-1, 1):
    x = CX + side * 6
    for yy in (0, 1):                              # big flat feet
        for dx in range(-2, 3):
            for z in range(CZ - 1, CZ + 9):
                if z >= CZ + 7 and (abs(dx) > 1 or yy == 1):
                    continue
                put(x + dx, yy, z, 'g' if yy == 0 else 'G')
    long_bone(x, 2, 10, CZ)                        # shin
    long_bone(x, 11, 17, CZ)                       # thigh

# ---- pelvis + loincloth ----------------------------------------------------
for yy in (16, 17, 18):
    fill_ellipse(yy, CX, CZ, 6.5, 4.0, 'g')
for yy in (14, 15, 16, 17, 18):                    # loincloth band (kilt)
    for xx in range(W):
        for zz in range(D):
            if ((xx - CX) / 8.5) ** 2 + ((zz - CZ) / 5.8) ** 2 <= 1.0:
                put_part(gk, xx, yy, zz, 'b')
for yy in range(11, 15):                           # front flap (kilt)
    for xx in range(20, 25):
        for zz in (15, 16):
            put_part(gk, xx, yy, zz, 'b')

# ---- pot belly, chest, hunch ----------------------------------------------
soft_ellipsoid(CX, 24, CZ + 1.5, 9.5, 6.5, 7.5)    # belly
soft_ellipsoid(CX, 29, CZ + 0.5, 8.5, 4.0, 6.5)    # midriff blend
soft_ellipsoid(CX, 33.5, CZ - 0.5, 8.0, 5.0, 6.0)  # chest
soft_ellipsoid(CX, 35.5, CZ - 4.5, 5.5, 3.5, 3.2)  # upper-back hump

# ---- shoulders and long arms ----------------------------------------------
for yy in (36, 37):
    for dx in range(-12, 13):
        for dz in (-1, 0, 1):
            put(CX + dx, yy, CZ + dz, 'g' if dz == 0 else 'G')
for side in (-1, 1):
    x = CX + side * 13
    knob(x, 36, CZ)                                # shoulder ball
    long_bone(x, 27, 35, CZ)                       # upper arm
    long_bone(x, 18, 26, CZ)                       # forearm
    for yy in (13, 14, 15, 16):                    # big palm
        for dz in range(-3, 4):
            for dx in (-1, 0, 1):
                put(x + dx, yy, CZ + dz, 'g')
    for yy in (8, 9, 10, 11, 12):                  # three long claws, crisp
        for dz in (-3, 0, 3):
            put(x, yy, CZ + dz, 'g', halo=False)
            put(x - side, yy, CZ + dz, 'g', halo=False)

# ---- neck ------------------------------------------------------------------
for yy in (38, 39):
    fill_ellipse(yy, CX, CZ + 1, 2.6, 2.6, 'g')

# ---- head ------------------------------------------------------------------
fill_ellipse(40, CX, CZ + 2, 5.0, 5.0, 'g')        # jaw base
fill_ellipse(41, CX, CZ + 3.0, 6.5, 6.5, 'g')      # lower jaw, underbite
fill_ellipse(42, CX, CZ + 3.5, 7.0, 7.0, 'g')
fill_ellipse(43, CX, CZ + 3.0, 7.0, 6.5, 'g')
fill_ellipse(44, CX, CZ + 1.0, 7.0, 5.5, 'g')      # mouth level
fill_ellipse(45, CX, CZ + 1.0, 7.0, 5.5, 'g')
for yy in (46, 47, 48, 49):                        # midface
    fill_ellipse(yy, CX, CZ, 7.5, 6.0, 'g')

for yy in (50, 51):                                # heavy brow
    fill_ellipse(yy, CX, CZ, 7.5, 6.0, 'g')
    for dx in range(-5, 6):
        put(CX + dx, yy, 17, 'g')
soft_ellipsoid(CX, 52, CZ - 0.5, 8.0, 8.5, 6.5, ymin=52)   # bald dome

# pointy ears: smooth tapered fins ending in real points
soft_cone(15, 52.5, 11, 3.5, 55, 11, 3.6, 1.5, 0.4, 0.4)
soft_cone(2 * CX - 15, 52.5, 11, 2 * CX - 3.5, 55, 11, 3.6, 1.5, 0.4, 0.4)

# ---- carved features (applied after the shell pass) ------------------------
carve_box(17, 27, 44, 45, 17, 19)                  # wide mouth slit
for xx in range(17, 28):                           # dark mouth back wall
    for yy in (44, 45):
        put_part(gt, xx, yy, 16, 's')
        carve.append((xx, yy, 16))
for fx in (18, 26):                                # fangs rise from the jaw
    for yy in (43, 44, 45):
        put_part(gt, fx, yy, 18, 't')
        put_part(gt, fx, yy, 19, 't')
    carve_box(fx, fx, 46, 46, 17, 20)              # lip notch above the tip
for ex0 in (16, 25):                               # eye sockets
    for xx in range(ex0, ex0 + 4):                 # dark lining, 2 deep
        for yy in range(46, 50):
            for zz in (15, 16):
                put_part(ge, xx, yy, zz, 's')
                carve.append((xx, yy, zz))
    carve_box(ex0, ex0 + 3, 46, 49, 17, 19)
    for xx in (ex0 + 1, ex0 + 2):                  # yellow core on the wall
        for yy in (47, 48):
            put_part(ge, xx, yy, 16, 'y')

# Skin variation: deterministic mottling (darker green flecks) and a
# lighter belly patch, so the flesh reads organic instead of flat.
for xx in range(W):
    for yy in range(H):
        for zz in range(D):
            if g[xx, yy, zz] != 'g':
                continue
            if ((xx - CX) / 8.0) ** 2 + ((yy - 24) / 5.5) ** 2 \
                    + ((zz - CZ - 3.5) / 5.0) ** 2 <= 1.0:
                g[xx, yy, zz] = 'ö'                # belly highlight
            elif (xx * 7 + yy * 13 + zz * 5) % 17 < 3:
                g[xx, yy, zz] = 'v'                # mottle fleck

# Rope belt: a clean analytic ring cinching the kilt's top hem,
# with a knot and dangling ends at the front.
ROPE_Y = 18
for xx in range(1, W - 1):
    for zz in range(1, D - 1):
        s = np.sqrt(((xx - CX) / 8.5) ** 2 + ((zz - CZ) / 5.8) ** 2)
        if 0.97 <= s <= 1.12:
            put_part(gk, xx, ROPE_Y, zz, 'R')
zk = int(round(CZ + 5.8))
for xx in (CX - 1, CX, CX + 1):                    # knot
    put_part(gk, xx, ROPE_Y, zk + 1, 'R')
put_part(gk, CX, ROPE_Y, zk + 2, 'R')
for yy in (16, 17):                                # dangling ends
    put_part(gk, CX - 1, yy, zk, 'R')
    put_part(gk, CX + 1, yy, zk, 'R')

# Wrist bands: leather cuffs ringing each forearm above the hand.
for side in (-1, 1):
    x0 = CX + side * 13
    for yy in (17, 18, 19):
        for xx in range(1, W - 1):
            for zz in range(1, D - 1):
                rr = np.sqrt((xx - x0) ** 2 + (zz - CZ) ** 2)
                if rr <= 2.6:
                    put_part(gb, xx, yy, zz, 'b')

# ---- 10-grade density falloff (distance-field shells) ----------------------
import math as _math

def _shift(mask, dx, dy, dz):
    out = np.zeros_like(mask)
    sx = slice(max(dx, 0), W + min(dx, 0)) if dx else slice(None)
    tx = slice(max(-dx, 0), W + min(-dx, 0)) if dx else slice(None)
    sy = slice(max(dy, 0), H + min(dy, 0)) if dy else slice(None)
    ty = slice(max(-dy, 0), H + min(-dy, 0)) if dy else slice(None)
    sz = slice(max(dz, 0), D + min(dz, 0)) if dz else slice(None)
    tz = slice(max(-dz, 0), D + min(-dz, 0)) if dz else slice(None)
    out[tx, ty, tz] = mask[sx, sy, sz]
    return out

SHELL_ALPHAS = [104, 92, 80, 68, 56, 44, 33, 22, 12, 5]
SHELL_CHARS = '0123456789'

seedm = np.isin(g, list(SOLID)) & halo_ok
dist = np.full(g.shape, 99.0)
for dx in range(-3, 4):
    for dy in range(-3, 4):
        for dz in range(-3, 4):
            r2 = dx * dx + dy * dy + dz * dz
            if r2 == 0 or r2 > 9.01:
                continue
            near = _shift(seedm, dx, dy, dz)
            dist = np.where(near, np.minimum(dist, _math.sqrt(r2)), dist)

# Smooth ramp: alpha(d) = 127.5 * (1 + (0.6 - d) / 2.2), quantized to
# the 10 grades. The iso-crossing lands ~0.8 voxel out and the field
# decays gently over 3 voxels, so marching cubes sees a near-smooth
# density and the surface loses its stair steps.
alpha = 127.5 - (dist - 0.5) * 80.0
emptym = g == '.'
for ci in range(10):
    lo = 0 if ci == 0 else (SHELL_ALPHAS[ci - 1] + SHELL_ALPHAS[ci]) / 2
    hi = 300 if ci == 0 else lo
    pass
levels = np.array(SHELL_ALPHAS, float)
sel = emptym & (alpha > 3) & (dist < 90)
sel[0, :, :] = sel[-1, :, :] = False    # borders reserved for markers
sel[:, :, 0] = sel[:, :, -1] = False
idx = np.abs(alpha[..., None] - levels[None, None, None, :]).argmin(axis=-1)
for ci, ch in enumerate(SHELL_CHARS):
    g[sel & (idx == ci)] = ch

for x, y, z in carve:
    if g[x, y, z] not in PROTECT:
        g[x, y, z] = '.'

SHARP_ZONES = [
    (15, 29, 41, 46, 16, 23),   # mouth and fangs
    (15, 20, 45, 50, 14, 21),   # left eye
    (24, 29, 45, 50, 14, 21),   # right eye
]
hardm = np.isin(g, list('btysR'))
near_hard = np.zeros_like(hardm)
for _dx in (-1, 0, 1):
    for _dy in (-1, 0, 1):
        for _dz in (-1, 0, 1):
            if (_dx, _dy, _dz) != (0, 0, 0):
                near_hard |= _shift(hardm, _dx, _dy, _dz)
shellm = np.isin(g, list(SHELL_CHARS))
g[shellm & near_hard] = '.'

for x0, x1, y0, y1, z0, z1 in SHARP_ZONES:
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            for z in range(z0, z1 + 1):
                if g[x, y, z] in SHELL_CHARS:
                    g[x, y, z] = '.'

# Hooked nose: a smooth pointed cone like the ears, sweeping
# forward and down from the bridge between the eyes.
soft_cone(CX, 48.5, 15.5, CX, 44.5, 21.0, 2.0, 1.8, 0.35, 0.35)

# ---- emit FXL --------------------------------------------------------------
H_used = max(y for x in range(W) for y in range(H) for z in range(D)
             if g[x, y, z] != '.') + 1
layers = []
for y in range(H_used):
    rows = list(''.join(g[x, y, z] for x in range(W)) for z in range(D))
    layers.append(rows)

JOINTS = {
    'a': (16, 2, 11),  'A': (28, 2, 11),    # ankles
    'm': (16, 0, 18),  'M': (28, 0, 18),    # toes
    'k': (16, 10, 11), 'K': (28, 10, 11),   # knees
    'q': (16, 17, 11), 'Q': (28, 17, 11),   # hips
    'p': (22, 19, 11),                      # pelvis root
    'f': (9, 11, 12),  'F': (35, 11, 12),   # claw tips
    'w': (9, 18, 11),  'W': (35, 18, 11),   # wrists
    'o': (9, 26, 11),  'O': (35, 26, 11),   # elbows
    'c': (22, 33, 10),                      # chest
    'u': (9, 36, 11),  'U': (35, 36, 11),   # shoulders
    'n': (22, 39, 12),                      # neck top
    'd': (22, 52, 11),                      # head
}
BONES = [
    ('spine', 'p', 'c'), ('neck', 'c', 'n'), ('head', 'n', 'd'),
    ('clav_l', 'c', 'u'), ('clav_r', 'c', 'U'),
    ('uarm_l', 'u', 'o'), ('uarm_r', 'U', 'O'),
    ('farm_l', 'o', 'w'), ('farm_r', 'O', 'W'),
    ('hand_l', 'w', 'f'), ('hand_r', 'W', 'F'),
    ('hip_l', 'p', 'q'), ('hip_r', 'p', 'Q'),
    ('thigh_l', 'q', 'k'), ('thigh_r', 'Q', 'K'),
    ('shin_l', 'k', 'a'), ('shin_r', 'K', 'A'),
    ('foot_l', 'a', 'm'), ('foot_r', 'A', 'M'),
]
def _inject_markers(layers, JOINTS, width, cx):
    # Stacked border markers (LANG.md section 8): scan inward from a
    # border and drop the marker on the first blank; every cell crossed
    # must itself be a marker, or that side is unusable.
    js = set(JOINTS)
    for ch, (jx, jy, jz) in JOINTS.items():
        rows = layers[jy]
        placed = False
        for order in (range(len(rows)), range(len(rows) - 1, -1, -1)):
            for r in order:
                cell = rows[r][jx]
                if cell == '.':
                    rows[r] = rows[r][:jx] + ch + rows[r][jx + 1:]
                    placed = True
                    break
                if cell not in js:
                    break
            if placed:
                break
        assert placed, 'column marker %r blocked' % ch
        placed = False
        near, far = (range(width), range(width - 1, -1, -1))
        if jx >= cx:
            near, far = far, near
        for order in (near, far):
            for c in order:
                cell = rows[jz][c]
                if cell == '.':
                    rows[jz] = rows[jz][:c] + ch + rows[jz][c + 1:]
                    placed = True
                    break
                if cell not in js:
                    break
            if placed:
                break
        assert placed, 'row marker %r blocked' % ch

_inject_markers(layers, JOINTS, W, CX)
layers = [tuple(rows) for rows in layers]

from collections import Counter
counts = Counter(layers)

out = []
out.append('# goblin.fxl -- generated by make_goblin.py, do not hand-edit.')
out.append('# %d x %d x %d voxels.' % (W, H_used, D))
out.append('')
out.append('g = 58A83C          # goblin skin, full density')
out.append('G = 58A83CC0        # soft skin, alpha 192')
out.append('e = 58A83C9E        # skin grade, alpha 158')
out.append('r = 58A83C83        # skin grade, alpha 131')
for ci, al in enumerate(SHELL_ALPHAS):
    out.append('%s = 58A83C%02X        # density shell %d, alpha %d'
               % (SHELL_CHARS[ci], al, ci + 1, al))
out.append('b = 6B4A2B hard     # loincloth, brown')
out.append('t = F5EFD8 hard     # fangs')
out.append('s = 1A2010C8 hard   # mouth/socket back walls, dark')
out.append('y = FFD41E hard     # eye glow, yellow')
out.append('R = 9A7B4F hard     # rope belt')
out.append('v = 4A9134          # skin mottle, darker green')
out.append('ö = 76B24A          # belly, lighter green')
out.append('')
out.append('skin elastic')
out.append('')
JOINT_NAMES = {
    'a': 'ankle_l', 'A': 'ankle_r', 'm': 'toe_l', 'M': 'toe_r',
    'k': 'knee_l', 'K': 'knee_r', 'q': 'hip_l', 'Q': 'hip_r',
    'p': 'pelvis', 'f': 'hand_l', 'F': 'hand_r', 'w': 'wrist_l',
    'W': 'wrist_r', 'o': 'elbow_l', 'O': 'elbow_r', 'c': 'chest',
    'u': 'shoulder_l', 'U': 'shoulder_r', 'n': 'neck_top', 'd': 'head_top',
}
HINTS = {'k': '+z', 'K': '+z', 'o': '-z', 'O': '-z'}
FACING = {'hand_l': '+x+z', 'hand_r': '-x+z'}
for ch in JOINTS:
    out.append('%s = joint %s%s'
               % (ch, JOINT_NAMES[ch],
                  ' ' + HINTS[ch] if ch in HINTS else ''))
for nm, c1, c2 in BONES:
    out.append('%s = bone %s %s%s'
               % (nm, c1, c2, ' ' + FACING[nm] if nm in FACING else ''))
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
    out_layers = []
    for y in range(y0, max(ys) + 1):
        out_layers.append([''.join(gp[x, y, z] for x in range(W))
                           for z in range(D)])
    return y0, out_layers


place_lines = []
for pname, gp in (('kilt', gk), ('teeth', gt), ('eyes', ge),
                  ('cuffs', gb)):
    py0, plyrs = _part_layers(gp)
    out.append('model %s:  # placed at y=%d' % (pname, py0))
    for rows in plyrs:
        out.extend(rows)
        out.append('---')
    place_lines.append('place %s +0 +%d +0' % (pname, py0))
out.extend(place_lines)
out.append('')

out.append('anim walk 0.9s loop:')
out.append('0%: chest +0 +0 +0')
out.append('0%: pelvis +0 +0 +0')
out.append('25%: pelvis -2.5 -2 +0')
out.append('50%: pelvis +0 +0 +0')
out.append('75%: pelvis +2.5 -2 +0')
out.append('0%: head_top +0 +0 +0')
out.append('25%: head_top +1.5 -1 +0')
out.append('50%: head_top +0 +0 +0')
out.append('75%: head_top -1.5 -1 +0')
out.append('0%: ankle_l +0 +1 +5')
out.append('50%: ankle_l +0 +1 -5')
out.append('75%: ankle_l +0 +3 +0')
out.append('100%: ankle_l +0 +1 +5')
out.append('0%: ankle_r +0 +1 -5')
out.append('25%: ankle_r +0 +3 +0')
out.append('50%: ankle_r +0 +1 +5')
out.append('100%: ankle_r +0 +1 -5')
out.append('0%: elbow_l +0 +0.5 -2.5')
out.append('50%: elbow_l +0 +1 +3.5')
out.append('100%: elbow_l +0 +0.5 -2.5')
out.append('0%: elbow_r +0 +1 +3.5')
out.append('50%: elbow_r +0 +0.5 -2.5')
out.append('100%: elbow_r +0 +1 +3.5')
out.append('0%: wrist_l +0 +1 -5')
out.append('50%: wrist_l +0 +4 +7.5')
out.append('100%: wrist_l +0 +1 -5')
out.append('0%: wrist_r +0 +4 +7.5')
out.append('50%: wrist_r +0 +1 -5')
out.append('100%: wrist_r +0 +4 +7.5')

with open('goblin.fxl', 'w') as f:
    f.write('\n'.join(out) + '\n')

n = int(np.isin(g, list(SOLID)).sum())
print('goblin.fxl: %d solid voxels, %d layers (%d unique, %d shared defs)'
      % (n, H_used, len(counts), len(names)))

# Disconnected things must stay disconnected: verify no accessory
# parts touch each other (teeth/eyes share the dark face mask by
# design). Fails the build rather than shipping fused parts.
import render as _render
_pal, _scene, _rig = _render.parse_fxl('goblin.fxl')
_touching = _render.check_part_clearance(
    _pal, _scene, allow={('eyes', 'teeth')})
assert not _touching, 'accessory parts touch: %s' % _touching
print('part clearance OK')

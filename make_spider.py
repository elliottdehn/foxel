#!/usr/bin/env python3
"""Generate spider.fxl: a rigged, animated jeweled orb-weaver in FXL.

Deep-teal abdomen with gold folium markings, dark bronze
cephalothorax with an amber median stripe, eight arched legs (dark
femurs, amber tibiae, dark tarsi), a cluster of glowing gold eyes
lined in near-black, crisp ivory fangs. 38-joint rig with double-bend
legs; crawl / walk / idle / threat animations.

Analytic-density technique after make_goblin.py, vectorized with
numpy for the larger grid. Uses current foxel features: Unicode shell
grades (the old ASCII budget forced a trimmed ladder), hard materials
for eyes and fangs, composed models so face features cannot bleed
into the body, and elastic skinning for the leg joints.
"""
import numpy as np

W, H, D = 80, 34, 84
CEPH = np.array([40.0, 13.0, 52.0])   # cephalothorax center; head faces +z
ABD = np.array([40.0, 17.5, 28.5])    # abdomen center (kept clear of
                                      # the rear legs for skinning)

g = np.full((W, H, D), '.', dtype='<U1')
dens = np.zeros((W, H, D))            # current alpha per cell, for max-union
halo_ok = np.zeros((W, H, D), bool)

# Fine grades near the iso threshold (127): the ramp writes ~26 alpha
# per voxel, so grades spaced ~7 near iso give marching cubes sub-voxel
# surface-position resolution instead of terracing. Grade count is
# trimmed to leave exactly 34 palette chars for the joint markers.
SOLID_ALPHAS = [255, 192, 158, 138, 131]
SHELL_ALPHAS = [124, 117, 110, 104, 97, 92, 86, 80, 74, 68]
SHELL_CHARS = '012345αβγδ'

MATS = {
    'teal':  ('TUVtv', '1F8A80'),     # abdomen jewel teal
    'amber': ('ABCab', 'E0A34A'),     # gold/amber accents + leg bands
    'dark':  ('KLMkm', '3E3430'),     # dark bronze body + leg bands
}
ACCENTS = {
    'o': ('12101A8C', 140),           # eye-cluster liner, near-black
    'y': ('FFC83C', 255),             # eye glow, gold
    'f': ('EDE3CC', 255),             # fangs, ivory
}
SHELL_RGB = '2B2E36'

ALPHA_OF = {'.': 0}
for chars, _rgb in MATS.values():
    for ch, a in zip(chars, SOLID_ALPHAS):
        ALPHA_OF[ch] = a
for ch, a in zip(SHELL_CHARS, SHELL_ALPHAS):
    ALPHA_OF[ch] = a
for ch, (_hex, a) in ACCENTS.items():
    ALPHA_OF[ch] = a

g_eyes = np.full((W, H, D), '.', dtype='<U1')
g_fangs = np.full((W, H, D), '.', dtype='<U1')


def put_part(gp, x, y, z, ch):
    x, y, z = int(round(x)), int(round(y)), int(round(z))
    if 0 <= x < W and 0 <= y < H and 0 <= z < D:
        gp[x, y, z] = ch


XX, YY, ZZ = np.meshgrid(np.arange(W, dtype=float),
                         np.arange(H, dtype=float),
                         np.arange(D, dtype=float), indexing='ij')


def blend(a, mat):
    """Density-max union of an analytic alpha field into the grid,
    quantized to the material's solid grades + shared shell grades."""
    chars = np.array(list(MATS[mat][0]) + list(SHELL_CHARS))
    levels = np.array(SOLID_ALPHAS + SHELL_ALPHAS, float)
    a = np.minimum(a, 255.0)
    idx = np.abs(a[..., None] - levels).argmin(-1)
    newa = levels[idx]
    take = (a >= 4.0) & (newa > dens)
    g[take] = chars[idx][take]
    dens[take] = newa[take]
    halo_ok[take] = True


def soft_ellipsoid(cx, cy, cz, rx, ry, rz, mat, ramp=26.0):
    s = np.sqrt(((XX - cx) / rx) ** 2 + ((YY - cy) / ry) ** 2
                + ((ZZ - cz) / rz) ** 2)
    rm = (rx * ry * rz) ** (1.0 / 3.0)   # s-units -> ~voxels
    blend(127.5 - (s - 1.0) * rm * ramp, mat)


def soft_cone(b, t, r0, r1, mat, ramp=26.0):
    """Analytic tapered capsule-cone from base b to tip t, circular
    cross-section shrinking r0 -> r1, rounded ends."""
    b = np.asarray(b, float)
    t = np.asarray(t, float)
    axis = t - b
    L = np.linalg.norm(axis)
    ah = axis / L
    u = np.cross(ah, [0.0, 0.0, 1.0])
    if np.linalg.norm(u) < 0.3:
        u = np.cross(ah, [0.0, 1.0, 0.0])
    u /= np.linalg.norm(u)
    v = np.cross(ah, u)
    px, py, pz = XX - b[0], YY - b[1], ZZ - b[2]
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
    blend(a, mat)


def put(x, y, z, ch, halo=True):
    x, y, z = int(round(x)), int(round(y)), int(round(z))
    if 0 <= x < W and 0 <= y < H and 0 <= z < D:
        g[x, y, z] = ch
        dens[x, y, z] = ALPHA_OF[ch]
        halo_ok[x, y, z] = halo


def recolor(mask, src_mat, dst_mat):
    """Swap material color on already-solid voxels, preserving the
    density grade so the surface does not move."""
    for sc, dc in zip(MATS[src_mat][0], MATS[dst_mat][0]):
        m = mask & (g == sc)
        g[m] = dc


# ---- body masses -----------------------------------------------------------
soft_ellipsoid(*CEPH, 8.5, 5.5, 10.0, 'dark')                 # cephalothorax
soft_ellipsoid(40.0, 15.0, 57.5, 5.2, 4.2, 5.2, 'dark')       # eye mound
soft_ellipsoid(40.0, 9.5, 59.5, 3.4, 3.2, 3.8, 'dark')        # chelicerae
soft_ellipsoid(40.0, 15.0, 42.0, 3.4, 3.0, 3.6, 'dark')       # pedicel
soft_ellipsoid(*ABD, 11.5, 9.5, 13.5, 'teal')                 # abdomen

# ---- eight legs + rig bookkeeping ------------------------------------------
# Rig: root at the cephalothorax, an abdomen hinge, and hip->knee->mid
# ->foot per leg so IK keeps the double bend. Joint marker chars share
# the palette namespace; with the color chars above this uses all 62.
JOINTS = {'R': (40, 13, 52),          # root, cephalothorax center
          '8': (40, 13, 61),          # head anchor, through the face
          '6': (35, 15, 60),          # cheek anchors: sit in the weld
          '7': (45, 15, 60),          # bridge between eye mound and
                                      # front femur, blocking the
                                      # femur's skin flood at the face
          '9': (40, 15, 42),          # pedicel (waist)
          'Q': (40, 18, 26)}          # abdomen
JOINT_NAMES = {'R': 'root', '8': 'head', '6': 'cheek_l', '7': 'cheek_r',
               '9': 'pedicel', 'Q': 'abd'}
# parent-first; root first. head_link/cheek anchors give the face and
# ceph flanks stable bones to skin to (each is a chain's first bone,
# hence rigid) — without them those voxels flood-bind to the femurs
# and swing with the legs. The abdomen needs a 2-bone chain: the
# first bone of any IK chain is rigid, so root->abd alone could not
# articulate — abd_hinge (pedicel->abd) is the bone that bends.
BONES = [('head_link', 'R', '8'),
         ('cheek_link_l', 'R', '6'), ('cheek_link_r', 'R', '7'),
         ('abd_link', 'R', '9'), ('abd_hinge', '9', 'Q')]
HINTS = {}
LEG_CHARS = {('l', 1): 'EFGH', ('l', 2): 'IJOP',
             ('l', 3): 'SXYZ', ('l', 4): 'cdeg',
             ('r', 1): 'hijl', ('r', 2): 'npqr',
             ('r', 3): 'suwx', ('r', 4): 'zWDN'}

# (theta from +z, reach, knee_r, knee_y, mid_r, mid_y); base ring r=7, y=12
LEGS = [
    (30.0, 30.0, 15.0, 26.0, 23.0, 12.0),
    (62.0, 28.0, 14.0, 27.0, 22.0, 12.5),
    (100.0, 24.0, 12.0, 24.0, 19.0, 12.0),
    (139.0, 31.0, 17.5, 27.0, 25.0, 12.0),   # kept clear of the abdomen
]                                            # flank so skinning cannot
                                             # leak onto the rear tibia
for side, sname in ((-1.0, 'l'), (1.0, 'r')):
    for li, (th_deg, reach, kr, ky, mr, my) in enumerate(LEGS, 1):
        th = np.radians(th_deg)
        sx, cz = side * np.sin(th), np.cos(th)

        def ring(r, y):
            return (CEPH[0] + sx * r, y, CEPH[2] + cz * r)

        # sockets sit at r=8.2, near the ceph surface, so femur bone
        # segments exit the body instead of seeding ceph voxels
        base, knee, mid, foot = (ring(8.2, 12.0), ring(kr, ky),
                                 ring(mr, my), ring(reach, 1.3))
        soft_cone(base, knee, 1.9, 1.5, 'dark')    # femur
        soft_cone(knee, mid, 1.5, 1.15, 'amber')   # tibia
        soft_cone(mid, foot, 1.15, 0.68, 'dark')   # tarsus (thin diagonal
        # cones pinch below iso if the radius drops much further)

        hc, kc, mc, fc = LEG_CHARS[(sname, li)]
        sfx = '%s%d' % (sname, li)
        for ch, part, p in ((hc, 'hip', base), (kc, 'knee', knee),
                            (mc, 'mid', mid), (fc, 'foot', foot)):
            JOINTS[ch] = tuple(int(round(v)) for v in p)
            JOINT_NAMES[ch] = '%s_%s' % (part, sfx)
        BONES += [('coxa_' + sfx, 'R', hc), ('femur_' + sfx, hc, kc),
                  ('tibia_' + sfx, kc, mc), ('tarsus_' + sfx, mc, fc)]
        HINTS[kc] = '+y'
        HINTS[mc] = '+y'

    # pedipalps: short amber feelers beside the fangs
    soft_cone((40.0 + side * 3.2, 10.5, 59.0),
              (40.0 + side * 6.5, 6.5, 66.0), 1.1, 0.55, 'amber')

_palette_chars = set(''.join(c for c, _ in MATS.values())
                     + SHELL_CHARS + 'oyf')
assert not _palette_chars & set(JOINTS), 'joint chars collide with colors'

# spinnerets: small dark taper at the abdomen's rear
soft_cone((40.0, 13.0, 16.5), (40.0, 10.5, 13.0), 1.4, 0.5, 'dark')

# ---- markings (recolors preserve the density grade) ------------------------
sa = np.sqrt(((XX - ABD[0]) / 11.5) ** 2 + ((YY - ABD[1]) / 9.5) ** 2
             + ((ZZ - ABD[2]) / 13.5) ** 2)
# no upper bound: nearest-grade rounding makes the outermost solid
# voxel land slightly OUTSIDE s=1, and it is the one whose color shows
near_abd = sa >= 0.62
xr, zr = XX - ABD[0], ZZ - ABD[2]

stripe_w = 1.0 + 1.2 * np.clip((zr + 11.0) / 21.0, 0.0, 1.0)
folium = near_abd & (YY > 15.0) & (np.abs(xr) <= stripe_w)
for sxp, szp, r in ((5.5, 4.0, 2.2), (-5.5, 4.0, 2.2),
                    (6.5, -2.0, 2.0), (-6.5, -2.0, 2.0),
                    (4.5, -7.5, 1.8), (-4.5, -7.5, 1.8)):
    folium |= near_abd & (YY > 13.0) & \
        ((xr - sxp) ** 2 + (zr - szp) ** 2 <= r * r)
recolor(folium, 'teal', 'amber')

sc_ = np.sqrt(((XX - CEPH[0]) / 8.5) ** 2 + ((YY - CEPH[1]) / 5.5) ** 2
              + ((ZZ - CEPH[2]) / 10.0) ** 2)
stripe = (sc_ >= 0.62) & (YY > 14.0) & \
    (np.abs(XX - 40.0) <= 1.4) & (ZZ >= 44.0) & (ZZ <= 57.0)
recolor(stripe, 'dark', 'amber')

# ---- eye cluster -----------------------------------------------------------
sm = np.sqrt(((XX - 40.0) / 5.2) ** 2 + ((YY - 15.0) / 4.2) ** 2
             + ((ZZ - 57.5) / 5.2) ** 2)
liner = (sm >= 0.62) & (ZZ >= 57.5) & (YY >= 12.5) & (YY <= 19.0) & \
    (np.abs(XX - 40.0) <= 5.5)
for sch in MATS['dark'][0]:
    m = liner & (g == sch)
    g[m] = 'o'

EYES = [(1.8, 15.3, 1.05), (-1.8, 15.3, 1.05),     # anterior median (main)
        (4.4, 14.6, 0.8), (-4.4, 14.6, 0.8),       # anterior lateral
        (3.5, 17.1, 0.75), (-3.5, 17.1, 0.75)]     # posterior lateral
for ex, ey, er in EYES:
    root = 1.0 - (ex / 5.2) ** 2 - ((ey - 15.0) / 4.2) ** 2
    ez = 57.5 + 5.2 * np.sqrt(max(root, 0.0)) + 0.25
    cx = 40.0 + ex
    for x in range(int(cx - 2), int(cx + 3)):
        for y in range(int(ey - 2), int(ey + 3)):
            for z in range(int(ez - 2), int(ez + 3)):
                if (x - cx) ** 2 + (y - ey) ** 2 + (z - ez) ** 2 <= er * er:
                    put_part(g_eyes, x, y, z, 'y')

# ---- fangs: crisp, no shells -----------------------------------------------
for side in (-1, 1):
    fx = 40.0 + side * 1.8
    for y, z, r in ((9, 61.0, 1.2), (8, 61.7, 1.1), (7, 62.3, 0.9),
                    (6, 62.8, 0.7), (5, 63.2, 0.5), (4, 63.5, 0.3)):
        for x in range(int(fx - 2), int(fx + 3)):
            for zz in range(int(z - 2), int(z + 3)):
                if (x - fx) ** 2 + (zz - z) ** 2 <= r * r + 0.25:
                    put_part(g_fangs, x, y, zz, 'f')

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

_inject_markers(layers, JOINTS, W, 40)
layers = [tuple(rows) for rows in layers]

from collections import Counter
counts = Counter(layers)

out = []
out.append('# spider.fxl -- generated by make_spider.py, do not hand-edit.')
out.append('# %d x %d x %d voxels. Jeweled orb-weaver, static.' % (W, H_used, D))
out.append('')
for name, (chars, rgb) in MATS.items():
    for ch, a in zip(chars, SOLID_ALPHAS):
        out.append('%s = %s%s  # %s, alpha %d'
                   % (ch, rgb, '' if a == 255 else '%02X' % a, name, a))
for ci, al in enumerate(SHELL_ALPHAS):
    out.append('%s = %s%02X  # density shell %d, alpha %d'
               % (SHELL_CHARS[ci], SHELL_RGB, al, ci + 1, al))
out.append('o = 12101A8C hard  # eye-cluster liner, near-black')
out.append('y = FFC83C hard  # eye glow, gold')
out.append('f = EDE3CC hard  # fangs, ivory')
out.append('')
out.append('skin elastic')
out.append('')
for ch in JOINTS:
    out.append('%s = joint %s%s'
               % (ch, JOINT_NAMES[ch],
                  ' ' + HINTS[ch] if ch in HINTS else ''))
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
for pname, gp in (('eyes', g_eyes), ('fangs', g_fangs)):
    py0, plyrs = _part_layers(gp)
    out.append('model %s:  # placed at y=%d' % (pname, py0))
    for rows in plyrs:
        out.extend(rows)
        out.append('---')
    place_lines.append('place %s +0 +%d +0' % (pname, py0))
out.extend(place_lines)
out.append('')

# ---- animations ------------------------------------------------------------
def kf(pct, joint, dx, dy, dz, ease=''):
    out.append('%g%%: %s %+g %+g %+g%s'
               % (pct % 100.0, joint, dx, dy, dz,
                  ' ' + ease if ease else ''))


ALL_FEET = [('foot_%s%d' % (s, i), s, i)
            for s in ('l', 'r') for i in (1, 2, 3, 4)]

# crawl: slow prowl — alternating tetrapod gait (l1+r2+l3+r4 vs
# r1+l2+r3+l4), a rear-to-front metachronal stagger inside each
# group, feet dragging back in stance and lifting forward in swing,
# low body bob + abdomen sway.
out.append('anim crawl 1.1s loop:')
kf(0, 'root', 0, -0.5, 0)
kf(25, 'root', 0.6, 0.4, 0)
kf(50, 'root', 0, -0.5, 0)
kf(75, 'root', -0.6, 0.4, 0)
kf(0, 'abd', 0, 0.5, 0)
kf(25, 'abd', -0.9, -0.3, 0)
kf(50, 'abd', 0, 0.5, 0)
kf(75, 'abd', 0.9, -0.3, 0)
F, LIFT = 3.2, 2.6
for name, s, i in ALL_FEET:
    grp = 0 if (s, i) in (('l', 1), ('r', 2), ('l', 3), ('r', 4)) else 50
    phi = grp + (4 - i) * 3
    kf(55 + phi, name, 0, 0, -F, 'linear')     # stance ends: dragged back
    kf(70 + phi, name, 0, LIFT, 0.6)           # swing apex
    kf(85 + phi, name, 0, 0, F, 'ease-out')    # land forward
out.append('---')

# walk: brisk gait — high carriage, quick cadence, short stance,
# springy high-lift swing; same diagonal groups, tighter stagger.
out.append('anim walk 0.65s loop:')
kf(0, 'root', 0, 0.45, 0)
kf(25, 'root', 0.35, 0.95, 0)
kf(50, 'root', 0, 0.45, 0)
kf(75, 'root', -0.35, 0.95, 0)
kf(0, 'abd', 0, 0.8, 0)
kf(25, 'abd', -0.5, 0.2, 0.3)
kf(50, 'abd', 0, 0.8, 0)
kf(75, 'abd', 0.5, 0.2, 0.3)
WF, WLIFT = 2.3, 3.4
for name, s, i in ALL_FEET:
    grp = 0 if (s, i) in (('l', 1), ('r', 2), ('l', 3), ('r', 4)) else 50
    phi = grp + (4 - i) * 2
    kf(60 + phi, name, 0, 0, -WF, 'linear')    # short stance push
    kf(76 + phi, name, 0, WLIFT, 0.8)          # high, quick swing
    kf(90 + phi, name, 0, 0.2, WF, 'ease-out') # crisp placement
out.append('---')

# idle: breathing bob on pinned feet, slow abdomen sway, two front-
# foot taps.
out.append('anim idle 3.2s loop:')
kf(0, 'root', 0, 0, 0)
kf(50, 'root', 0, -0.7, 0)
kf(0, 'abd', 0, 0, 0)
kf(30, 'abd', 0.5, 0.9, -0.5)
kf(65, 'abd', -0.5, -0.2, 0.2)
for name, s, i in ALL_FEET:
    kf(0, name, 0, 0, 0)                       # pin: legs flex with the bob
kf(38, 'foot_r1', 0, 0, 0)
kf(46, 'foot_r1', 0, 2.2, 1.5)
kf(54, 'foot_r1', 0, 0, 0, 'ease-out')
kf(74, 'foot_l1', 0, 0, 0)
kf(82, 'foot_l1', 0, 2.2, 1.5)
kf(90, 'foot_l1', 0, 0, 0, 'ease-out')
out.append('---')

# threat: rear up onto the back legs, raise both front pairs, dip the
# abdomen; hold the display, then settle.
out.append('anim threat 2.6s loop:')
kf(0, 'root', 0, 0, 0)
kf(30, 'root', 0, 2.8, -2.0, 'ease-out')
kf(62, 'root', 0, 2.8, -2.0)
kf(0, 'abd', 0, 0, 0)
kf(30, 'abd', 0, -1.5, -1.8)
kf(62, 'abd', 0, -1.5, -1.8)
for name, s, i in ALL_FEET:
    if i >= 3:
        kf(0, name, 0, 0, 0)                   # rear feet stay planted
for s, sx in (('l', -1.0), ('r', 1.0)):
    for i, ry, rz, t0 in ((1, 10.5, 2.0, 32), (2, 8.0, 1.0, 36)):
        name = 'foot_%s%d' % (s, i)
        t0 += 0 if s == 'l' else 2             # slight l/r offset
        kf(0, name, 0, 0, 0)
        kf(t0, name, sx * 4.5, ry, rz, 'ease-out')
        kf(t0 + 28, name, sx * 4.5, ry, rz)
out.append('---')

with open('spider.fxl', 'w') as f:
    f.write('\n'.join(out) + '\n')

n = int(np.isin(g, list(SOLID)).sum())
print('spider.fxl: %d solid voxels, %d layers (%d unique, %d shared defs)'
      % (n, H_used, len(counts), len(names)))

# Disconnected things must stay disconnected (AGENTS.md).
import render as _render
_pal, _scene, _rig = _render.parse_fxl('spider.fxl')
_touching = _render.check_part_clearance(_pal, _scene)
assert not _touching, 'accessory parts touch: %s' % _touching
print('part clearance OK')

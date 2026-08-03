#!/usr/bin/env python3
"""Generate skeleton.fxl: a 43 x ~97 x 21 voxel skeleton in FXL (LANG.md).

The body (legs, pelvis, spine, ribs, arms) is painted with simple loops.
The head is hand-drawn layer by layer in the SKULL block -- no primitives.

A halo pass makes every empty voxel 6-adjacent to halo-eligible bone 'h'
(alpha 96, sub-threshold), which rounds surfaces under marching cubes
(IMPL.md section 5). Ribs, spine, sternum and teeth opt out so their gaps
stay crisp. 'x' cells are carved to empty AFTER the halo pass, keeping eye
sockets, nasal aperture and mouth gaps as dark cavities.

Repeated layers are emitted as FXL definitions and '*name N' references.
"""
import numpy as np

W, H, D = 43, 98, 22
CX, CZ = 21, 10

g = np.full((W, H, D), '.', dtype='<U1')
halo_ok = np.zeros((W, H, D), bool)

SOLID = set('Bbter')


def put(x, y, z, ch, halo=True):
    x, y, z = int(round(x)), int(round(y)), int(round(z))
    if 0 <= x < W and 0 <= y < H and 0 <= z < D:
        g[x, y, z] = ch
        halo_ok[x, y, z] = halo


def plus(x, y, z, ch='B'):
    """A 2x-scale bone cross-section: solid core with soft sides."""
    put(x, y, z, ch)
    put(x - 1, y, z, 'b')
    put(x + 1, y, z, 'b')
    put(x, y, z - 1, 'b')
    put(x, y, z + 1, 'b')


def column(x, y0, y1, z, ch='B'):
    for y in range(y0, y1 + 1):
        plus(x, y, z, ch)


def knob(x, y, z):
    """Flared bone end (epiphysis): solid cross with soft corners."""
    for dx, dz in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)):
        put(x + dx, y, z + dz, 'B')
    for dx, dz in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        put(x + dx, y, z + dz, 'b')


def long_bone(x, y0, y1, z):
    """Classic long bone: flared knob, slim waisted shaft, flared knob."""
    for yy in (y0, y0 + 1):
        knob(x, yy, z)
    for yy in range(y0 + 2, y1 - 1):
        put(x, yy, z, 'B')
        put(x, yy, z - 1, 'b')
        put(x, yy, z + 1, 'b')
    for yy in (y1 - 1, y1):
        knob(x, yy, z)


def ring(y, rx, rz, ch='B'):
    """A 2-voxel-thick rib ring, no halo (gaps must stay crisp)."""
    for r in (0.0, 0.9):
        for t in np.linspace(0, 2 * np.pi, 512):
            put(CX + (rx - r) * np.sin(t), y,
                CZ + (rz - r * rz / rx) * np.cos(t), ch, halo=False)


# ---- legs and feet ---------------------------------------------------------
for side in (-1, 1):
    x = CX + side * 8
    for yy in (0, 1):                              # foot, toes forward
        for dx in range(-2, 3):
            for z in range(CZ, CZ + 7):
                if z >= CZ + 5 and abs(dx) > 1:
                    continue
                put(x + dx, yy, z, 'B' if abs(dx) <= 1 and yy == 0 else 'b')
    long_bone(x, 2, 13, CZ)                        # tibia
    long_bone(x, 14, 27, CZ)                       # femur; lower knob = knee
    put(x, 14, CZ + 3, 'b')                        # patella, in front
    put(x, 15, CZ + 3, 'b')
    for yy in (28, 29):                            # hip ball
        plus(x, yy, CZ, 'b')
        put(x - side * 2, yy, CZ, 'b')

# ---- pelvis ----------------------------------------------------------------
for yy in (28, 29):
    for dx in range(-6, 7):
        put(CX + dx, yy, CZ, 'B')
        put(CX + dx, yy, CZ - 1, 'b')
        put(CX + dx, yy, CZ + 1, 'b')
for yy in (30, 31):
    for dx in range(-4, 5):
        put(CX + dx, yy, CZ, 'B')
    for dx in range(-2, 3):
        put(CX + dx, yy, CZ + 1, 'b')
for yy in (32, 33):                                # sacrum, ties to the spine
    for dx in range(-1, 2):
        put(CX + dx, yy, CZ, 'b')
    put(CX, yy, CZ - 2, 'b')
    put(CX, yy, CZ - 3, 'b')

# ---- lumbar spine (posterior, z = 5/6) -------------------------------------
for y in range(32, 40):
    put(CX, y, 5, 'B', halo=False)
    put(CX, y, 6, 'B', halo=False)
    put(CX - 1, y, 5, 'b', halo=False)
    put(CX + 1, y, 5, 'b', halo=False)
    put(CX, y, 7, 'b', halo=False)

# ---- ribcage: 2-thick rings, 2-layer gaps ----------------------------------
RIBS = [(40, 7.5, 4.2), (44, 9.5, 4.6), (48, 10.5, 5.0),
        (52, 10.5, 5.0), (56, 9.5, 4.6)]
for yb, rx, rz in RIBS:
    for yy in (yb, yb + 1):
        ring(yy, rx, rz)
        for dx in (-1, 0, 1):                      # spine knob
            put(CX + dx, yy, round(CZ - rz), 'B', halo=False)
        put(CX, yy, round(CZ + rz), 'B', halo=False)   # sternum
    for yy in (yb + 2, yb + 3):                    # gap: spine + sternum only
        if yy >= 60:
            continue
        put(CX, yy, 5, 'B', halo=False)
        put(CX, yy, 6, 'B', halo=False)
        put(CX, yy, 7, 'b', halo=False)
        put(CX, yy, 15, 'B', halo=False)
        put(CX, yy, 14, 'b', halo=False)

# ---- shoulders, clavicles, arms --------------------------------------------
for yy in (60, 61):
    for dx in range(-12, 13):
        put(CX + dx, yy, 13, 'b')                  # clavicle (front)
    for side in (-1, 1):
        s = CX + side * 12
        plus(s, yy, CZ)                            # shoulder ball
        put(s, yy, 13, 'B')
for side in (-1, 1):
    x = CX + side * 14                             # arm at x = 7 / 35
    put(x, 60, CZ, 'b')
    put(x, 61, CZ, 'b')
    long_bone(x, 46, 59, CZ)                       # humerus; lower knob = elbow
    put(x, 46, CZ - 3, 'b')                        # olecranon, elbow point at back
    put(x, 47, CZ - 3, 'b')
    long_bone(x, 36, 45, CZ)                       # forearm
    for yy in (34, 35):                            # wrist
        put(x, yy, CZ, 'b')
        put(x, yy, CZ + 1, 'b')
    for yy in (31, 32, 33):                        # palm, facing the body
        for dz in range(-2, 3):
            put(x, yy, CZ + dz, 'B' if dz == 0 else 'b')
            put(x - side, yy, CZ + dz, 'b')
    put(x, 32, CZ + 3, 'b')                        # thumb, forward
    put(x, 31, CZ + 3, 'b')
    for yy in (28, 29, 30):                        # fingers, crisp gaps
        for dz in (-2, 0, 2):
            put(x, yy, CZ + dz, 'B', halo=False)
            put(x - side, yy, CZ + dz, 'B', halo=False)

# ---- neck: curves forward from the spine to under the skull ----------------
for yy, zz in ((60, 6), (61, 7), (62, 8), (63, 9), (64, 9)):
    put(CX, yy, zz, 'B')
    put(CX, yy, zz + 1, 'B')
    put(CX - 1, yy, zz, 'b')
    put(CX + 1, yy, zz, 'b')

# ---- head, hand-drawn layer by layer from the neck up ----------------------
# Each layer is 22 rows (z0 back .. z21 front) x 43 cols. Chars as in the
# palette; 'x' = carve to empty AFTER the halo pass.
SKULL_Y0 = 65
E = '.' * 43
NECK_B = "....................BBB...................."
NECK_S = "....................bbb...................."
W5  = "...................bbbbb..................."
W7  = "..................bbbbbbb.................."
W9  = ".................bbbbbbbbb................."
W11 = "................bbbbbbbbbbb................"
W13 = "...............bbbbbbbbbbbbb..............."
W15 = "..............bbbbbbbbbbbbbbb.............."
W17 = ".............bbbbbbbbbbbbbbbbb............."
W19 = "............bbbbbbbbbbbbbbbbbbb............"
W21 = "...........bbbbbbbbbbbbbbbbbbbbb..........."
W23 = "..........bbbbbbbbbbbbbbbbbbbbbbb.........."
W25 = ".........bbbbbbbbbbbbbbbbbbbbbbbbb........."
W27 = "........bbbbbbbbbbbbbbbbbbbbbbbbbbb........"

NECKED = [E] * 9 + [NECK_B, NECK_S]     # z0-8 empty, vertebra at z9/z10

GRIN = NECKED + [
    E,                                              # z11
    "..............beeeeeeeeeeeeeeb.............",  # z12  dark cavity wall
    "..............bxxxxxxxxxxxxxxb.............",  # z13
    "..............bxxxxxxxxxxxxxxb.............",  # z14
    "..............bttxttxttxttxttb.............",  # z15  five 2-wide teeth
    "..............bttxttxttxttxttb.............",  # z16
    "..............xxxxxxxxxxxxxxxx.............",  # z17  carve halos
    E, E, E, E,                                     # z18-21
]

CHIN = NECKED + [
    E, E, E,                                        # z11-13
    ".................bbbbbbbbb.................",  # z14
    ".................bbbbbbbbb.................",  # z15
    E, E, E, E, E, E,                               # z16-21
]

MAXILLA = [
    E, E, E, E,                                     # z0-3
    W5, W9, W13, W13,                               # z4-7
    W17, W17, W17, W17, W17, W17, W17, W17,         # z8-15
    W13, W13,                                       # z16-17 lip band
    E, E, E, E,                                     # z18-21
]

NOSE_LOW = [
    E, E, E, E,                                     # z0-3
    W5, W9, W13, W13,                               # z4-7
    W17, W17, W17, W17, W17,                        # z8-12
    ".............bbbbbbeeeeebbbbbb.............",  # z13  wall
    ".............bbbbbbxxxxxbbbbbb.............",  # z14  5-wide aperture
    ".............bbbbbbxxxxxbbbbbb.............",  # z15
    "...............bbbbxxxxxbbbb...............",  # z16
    "...............bbbbxxxxxbbbb...............",  # z17
    "...................xxxxx...................",  # z18  carve halos
    E, E, E,                                        # z19-21
]
NOSE_HIGH = [
    E, E, E, E,
    W5, W9, W13, W13,
    W17, W17, W17, W17, W17,
    ".............bbbbbbbeeebbbbbbb.............",  # z13
    ".............bbbbbbbxxxbbbbbbb.............",  # z14  3-wide aperture
    ".............bbbbbbbxxxbbbbbbb.............",  # z15
    "...............bbbbbxxxbbbbb...............",  # z16
    "...............bbbbbxxxbbbbb...............",  # z17
    "....................xxx....................",  # z18
    E, E, E,
]

ORBIT_BASE = [
    W5,                                             # z0   occiput
    W9, W13, W17, W21,                              # z1-4
    W23, W23, W23, W23, W23, W23, W23, W23,         # z5-12
    "..........beeeeeeebbbbbbbeeeeeeeb..........",  # z13  socket back walls
]
ORBIT_LOW = ORBIT_BASE + [
    "..........bxxrrxxxbbbbbbbxxxrrxxb..........",  # z14  red 2x2 eye dots
    "..........bxxxxxxxbbbbbbbxxxxxxxb..........",  # z15
    "..........xxxxxxxxbbbbbbbxxxxxxxx..........",  # z16  sockets to the edge
    "..........xxxxxxxxbbbbbbbxxxxxxxx..........",  # z17
    "..........xxxxxxxx.......xxxxxxxx..........",  # z18  carve halos
    E, E, E,                                        # z19-21
]
ORBIT_HIGH = ORBIT_BASE + [
    "..........bxxxxxxxbbbbbbbxxxxxxxb..........",  # z14
    "..........bxxxxxxxbbbbbbbxxxxxxxb..........",  # z15
    "..........xxxxxxxxbbbbbbbxxxxxxxx..........",  # z16
    "..........xxxxxxxxbbbbbbbxxxxxxxx..........",  # z17
    "..........xxxxxxxx.......xxxxxxxx..........",  # z18
    E, E, E,
]

BROW = [
    W9, W13, W17, W21,                              # z0-3  deep occiput
    W23, W23, W23, W23, W23, W23,                   # z4-9
    W23, W23, W23, W23, W23, W23,                   # z10-15
    W21, W17, W13,                                  # z16-18 jutting brow
    E, E, E,
]

CRANIUM = [
    W13, W17, W21,                                  # z0-2  deep occiput
    W23, W23, W23, W23, W23, W23,                   # z3-8
    W23, W23, W23, W23, W23, W23,                   # z9-14
    W21, W17, W13,                                  # z15-17
    E, E, E, E,
]

DOME25 = [
    E,
    W13, W17, W21,
    W25, W25, W25, W25, W25, W25, W25, W25, W25, W25,
    W21, W17, W13,
    E, E, E, E, E,
]
DOME23 = [
    E, E,
    W13, W17, W21,
    W23, W23, W23, W23, W23, W23, W23, W23,
    W21, W17, W13,
    E, E, E, E, E, E,
]
DOME21 = [
    E, E,
    W9, W13, W17,
    W21, W21, W21, W21, W21, W21, W21, W21,
    W17, W13, W9,
    E, E, E, E, E, E,
]
DOME19 = [
    E, E, E,
    W9, W13,
    W19, W19, W19, W19, W19, W19, W19, W19,
    W13, W9,
    E, E, E, E, E, E, E,
]
DOME15 = [
    E, E, E, E,
    W9,
    W15, W15, W15, W15, W15, W15, W15, W15,
    W9,
    E, E, E, E, E, E, E, E,
]
DOME11 = [
    E, E, E, E, E,
    W7,
    W11, W11, W11, W11, W11, W11,
    W7,
    E, E, E, E, E, E, E, E, E,
]
CROWN = [
    E, E, E, E, E, E, E,
    W7, W7, W7, W7,
    E, E, E, E, E, E, E, E, E, E, E,
]

SKULL = (
    [NECKED + [E] * 11] * 2 +       # y=65-66  neck vertebrae
    [CHIN] * 2 +                    # y=67-68  chin strip
    [GRIN] * 4 +                    # y=69-72  grin, 4 tall
    [MAXILLA] * 2 +                 # y=73-74  lip band
    [NOSE_LOW] * 2 +                # y=75-76  nasal aperture, wide bottom
    [NOSE_HIGH] * 2 +               # y=77-78  nasal aperture, narrow top
    [ORBIT_LOW] * 2 +               # y=79-80  orbits with red eyes
    [ORBIT_HIGH] * 2 +              # y=81-82  orbits, upper half
    [BROW] * 2 +                    # y=83-84  brow, widest, juts forward
    [CRANIUM] * 4 +                 # y=85-88  cranium, deep occiput
    [DOME21, DOME19, DOME15, DOME11] +  # y=89-92 dome ladder
    [CROWN]                         # y=93     crown cap
)

carve = []
for i, layer in enumerate(SKULL):
    assert len(layer) == D, 'skull layer %d: %d rows' % (i, len(layer))
    y = SKULL_Y0 + i
    for z, row in enumerate(layer):
        assert len(row) == W, 'skull y=%d z=%d: %d cols' % (y, z, len(row))
        for x, ch in enumerate(row):
            if ch == '.':
                continue
            if ch == 'x':
                carve.append((x, y, z))
            else:
                put(x, y, z, ch, halo=(ch in 'Bb'))

# ---- graded halo: 3-shell density falloff (smooth-brush style) -------------
def dilate(mask, offsets):
    out = np.zeros_like(mask)
    for dx, dy, dz in offsets:
        sx = slice(max(dx, 0), W + min(dx, 0)) if dx else slice(None)
        tx = slice(max(-dx, 0), W + min(-dx, 0)) if dx else slice(None)
        sy = slice(max(dy, 0), H + min(dy, 0)) if dy else slice(None)
        ty = slice(max(-dy, 0), H + min(-dy, 0)) if dy else slice(None)
        sz = slice(max(dz, 0), D + min(dz, 0)) if dz else slice(None)
        tz = slice(max(-dz, 0), D + min(-dz, 0)) if dz else slice(None)
        out[tx, ty, tz] |= mask[sx, sy, sz]
    return out

OFF6 = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
OFF26 = [(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
         for dz in (-1, 0, 1) if (dx, dy, dz) != (0, 0, 0)]

seed = np.isin(g, list(SOLID)) & halo_ok
empty = g == '.'
d1 = dilate(seed, OFF6)                       # distance 1 (faces)
d14 = dilate(seed, OFF26)                     # distance <= sqrt(3)
d2 = dilate(d1 | seed, OFF6) | dilate(d14, OFF6)   # distance <= 2
g[empty & d1] = 'h'                           # alpha 112
g[empty & d14 & ~d1] = 'i'                    # alpha 66
g[empty & d2 & ~d14 & ~d1] = 'j'              # alpha 30

# ---- carve cavities (after halo, so they stay open and dark) ---------------
for x, y, z in carve:
    g[x, y, z] = '.'

# ---- emit FXL --------------------------------------------------------------
H_used = max(y for x in range(W) for y in range(H) for z in range(D)
             if g[x, y, z] != '.') + 1
layers = []
for y in range(H_used):
    rows = list(''.join(g[x, y, z] for x in range(W)) for z in range(D))
    layers.append(rows)

# ---- animation rig: joints marked with sudoku border notation --------------
JOINTS = {
    'a': (13, 2, 10),  'A': (29, 2, 10),    # ankles
    'm': (13, 0, 15),  'M': (29, 0, 15),    # toes
    'k': (13, 13, 10), 'K': (29, 13, 10),   # knees
    'g': (13, 28, 10), 'G': (29, 28, 10),   # hips
    'p': (21, 29, 10),                      # pelvis root
    'w': (7, 34, 10),  'W': (35, 34, 10),   # wrists
    'f': (7, 28, 11),  'F': (35, 28, 11),   # fingertips
    'o': (7, 46, 10),  'O': (35, 46, 10),   # elbows
    'c': (21, 58, 10),                      # chest
    's': (9, 61, 10),  'S': (33, 61, 10),   # shoulders
    'n': (21, 63, 9),                       # neck
    'd': (21, 78, 10),                      # head
}
BONES = [
    ('spine', 'p', 'c'), ('neck', 'c', 'n'), ('head', 'n', 'd'),
    ('clav_l', 'c', 's'), ('clav_r', 'c', 'S'),
    ('uarm_l', 's', 'o'), ('uarm_r', 'S', 'O'),
    ('farm_l', 'o', 'w'), ('farm_r', 'O', 'W'),
    ('hand_l', 'w', 'f'), ('hand_r', 'W', 'F'),
    ('hip_l', 'p', 'g'), ('hip_r', 'p', 'G'),
    ('thigh_l', 'g', 'k'), ('thigh_r', 'G', 'K'),
    ('shin_l', 'k', 'a'), ('shin_r', 'K', 'A'),
    ('foot_l', 'a', 'm'), ('foot_r', 'A', 'M'),
]
for ch, (jx, jy, jz) in JOINTS.items():
    rows = layers[jy]
    r0 = 0 if rows[0][jx] == '.' else len(rows) - 1
    assert rows[r0][jx] == '.', 'column marker %r blocked' % ch
    rows[r0] = rows[r0][:jx] + ch + rows[r0][jx + 1:]
    ci = 0 if jx < CX else W - 1
    assert rows[jz][ci] == '.', 'row marker %r blocked' % ch
    rows[jz] = (ch + rows[jz][1:]) if ci == 0 else (rows[jz][:-1] + ch)
layers = [tuple(rows) for rows in layers]

from collections import Counter
counts = Counter(layers)

out = []
out.append('# skeleton.fxl -- generated by make_skeleton.py, do not hand-edit.')
out.append('# %d x %d x %d voxels. Alpha mechanic (IMPL.md section 5):' % (W, H_used, D))
out.append("#   B bone 255, b soft bone 192, h halo 96 (sub-threshold shell,")
out.append("#   rounds joints/skull), t teeth, e dark socket walls, r red eyes.")
out.append('')
out.append('B = F0EAD6          # bone, full density')
out.append('b = F0EAD6C0        # soft bone, alpha 192')
out.append('h = F0EAD640        # halo shell 1, alpha 64 (sub-threshold)')
out.append('i = F0EAD61C        # halo shell 2, alpha 28')
out.append('j = F0EAD60C        # halo shell 3, alpha 12')
out.append('t = FBFBF2 hard     # teeth')
out.append('e = 16161CC8 hard   # socket back wall: dark, recessed')
out.append('r = FF2626 hard     # eye glow: red dots in the sockets')
out.append('')
out.append('# animation rig: joints are marked in the layers below with')
out.append('# sudoku border notation (LANG.md section 7)')
JOINT_NAMES = {
    'a': 'ankle_l', 'A': 'ankle_r', 'k': 'knee_l', 'K': 'knee_r',
    'm': 'toe_l', 'M': 'toe_r',
    'g': 'hip_l', 'G': 'hip_r', 'p': 'pelvis', 'w': 'wrist_l',
    'W': 'wrist_r', 'o': 'elbow_l', 'O': 'elbow_r', 'c': 'chest',
    'f': 'hand_l', 'F': 'hand_r',
    's': 'shoulder_l', 'S': 'shoulder_r', 'n': 'neck_top', 'd': 'head_top',
}
HINTS = {'k': '+z', 'K': '+z', 'o': '-x-y', 'O': '+x-y'}
for ch in JOINTS:
    out.append('%s = joint %s%s'
               % (ch, JOINT_NAMES[ch],
                  ' ' + HINTS[ch] if ch in HINTS else ''))
FACING = {'hand_l': '+x+z', 'hand_r': '-x+z'}
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

out.append('# animations: IK keyframes (LANG.md section 8)')
out.append('anim walk 1.0s loop:')
out.append('0%: chest +0 +0 +0')
out.append('25%: chest +1.5 +0 +0')
out.append('50%: chest +0 +0 +0')
out.append('75%: chest -1.5 +0 +0')
out.append('0%: pelvis +0 +0 +0')
out.append('25%: pelvis -2 -2 +0')
out.append('50%: pelvis +0 +0 +0')
out.append('75%: pelvis +2 -2 +0')
out.append('0%: head_top +0 +0 +0')
out.append('25%: head_top +1.5 -1 +0')
out.append('50%: head_top +0 +0 +0')
out.append('75%: head_top -1.5 -1 +0')
out.append('0%: ankle_l +0 +1 +7')
out.append('50%: ankle_l +0 +1 -7')
out.append('75%: ankle_l +0 +5 +0')
out.append('100%: ankle_l +0 +1 +7')
out.append('0%: ankle_r +0 +1 -7')
out.append('25%: ankle_r +0 +5 +0')
out.append('50%: ankle_r +0 +1 +7')
out.append('100%: ankle_r +0 +1 -7')
out.append('0%: elbow_l -1 +0.5 -4')
out.append('50%: elbow_l -1 +0.5 +4')
out.append('100%: elbow_l -1 +0.5 -4')
out.append('0%: elbow_r +1 +0.5 +4')
out.append('50%: elbow_r +1 +0.5 -4')
out.append('100%: elbow_r +1 +0.5 +4')
out.append('0%: wrist_l -1 +1 -8')
out.append('50%: wrist_l -1 +1 +8')
out.append('100%: wrist_l -1 +1 -8')
out.append('0%: wrist_r +1 +1 +8')
out.append('50%: wrist_r +1 +1 -8')
out.append('100%: wrist_r +1 +1 +8')
out.append('---')
out.append('anim wave 1.6s loop:')
out.append('0%: chest +0 +0 +0')
out.append('0%: wrist_r +0 +0 +0')
out.append('25%: wrist_r +6 +26 +4')
out.append('40%: wrist_r +11 +24 +4')
out.append('55%: wrist_r +6 +26 +4')
out.append('70%: wrist_r +11 +24 +4')
out.append('85%: wrist_r +6 +26 +4')
out.append('100%: wrist_r +0 +0 +0')
out.append('0%: hand_r +0 +0 +0')
out.append('25%: hand_r +6 +38 +3')
out.append('40%: hand_r +13 +36 +3')
out.append('55%: hand_r +6 +38 +3')
out.append('70%: hand_r +13 +36 +3')
out.append('85%: hand_r +6 +38 +3')
out.append('100%: hand_r +0 +0 +0')
out.append('---')
out.append('anim idle 3.0s loop:')
out.append('0%: ankle_l +0 +0 +0')
out.append('0%: ankle_r +0 +0 +0')
out.append('0%: toe_l +0 +0 +0')
out.append('0%: toe_r +0 +0 +0')
out.append('0%: pelvis +0 -1.5 +0')
out.append('50%: pelvis +0 -2.2 +0')
out.append('100%: pelvis +0 -1.5 +0')
out.append('0%: chest +0 -1 +0')
out.append('50%: chest +0 -0.2 +0')
out.append('100%: chest +0 -1 +0')
out.append('0%: head_top +0 -1 +0')
out.append('50%: head_top +0 -0.3 +0')
out.append('100%: head_top +0 -1 +0')
out.append('0%: wrist_l -1 -1.4 +1')
out.append('50%: wrist_l -1 -1.6 +1.5')
out.append('100%: wrist_l -1 -1.4 +1')
out.append('0%: wrist_r +1 -1.4 +1')
out.append('50%: wrist_r +1 -1.6 +1.5')
out.append('100%: wrist_r +1 -1.4 +1')

with open('skeleton.fxl', 'w') as f:
    f.write('\n'.join(out) + '\n')

n = int(np.isin(g, list(SOLID)).sum())
print('skeleton.fxl: %d solid voxels, %d layers (%d unique, %d shared defs)'
      % (n, H_used, len(counts), len(names)))

#!/usr/bin/env python3
"""Render an FXL voxel model (see LANG.md) to a PNG.

Meshing follows goxel's marching cubes as described in IMPL.md: the voxel
alpha channel is the density field sampled at voxel centers, corners are
inside at alpha >= 127, edge vertices interpolate to iso-level 0.5, and each
vertex takes the color of the higher-alpha edge endpoint. Smooth mode by
default; --flat snaps vertices to half-voxel increments (IMPL.md §6) but
does not reproduce goxel's polygon merge/re-split pass.

Usage: python3 render.py model.fxl [-o out.png] [--flat] [--yaw D] [--pitch D]
"""
import argparse
import math
import re
import struct
import sys
import zlib

import numpy as np

# macOS Accelerate-backed numpy emits spurious divide/overflow warnings from
# matmul on some shapes; all mesh data is verified finite before rendering.
np.seterr(all='ignore')

from mc_tables import MC_EDGE_TABLE, MC_TRI_TABLE

# Cube conventions from goxel/src/block_def.h (y-up, see IMPL.md §3).
VERTICES_POSITIONS = [
    (0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1),
    (0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1),
]
EDGES_VERTICES = [
    (0, 1), (1, 2), (2, 3), (3, 0),
    (4, 5), (5, 6), (6, 7), (7, 4),
    (0, 4), (1, 5), (2, 6), (3, 7),
]

NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
CHAR_RE = re.compile(r'^[A-Za-z0-9]$')
COLOR_RE = re.compile(r'^[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$')
HINT_RE = re.compile(r'^(?:[+-][xyz])+$')
ANIM_RE = re.compile(r'^anim\s+([A-Za-z_][A-Za-z0-9_]*)\s+'
                     r'(\d+(?:\.\d+)?)s(\s+loop)?\s*:$')
KEY_RE = re.compile(r'^(\d+(?:\.\d+)?)%\s*:\s*(\S+)'
                    r'\s+([+-]?\d+(?:\.\d+)?)'
                    r'\s+([+-]?\d+(?:\.\d+)?)'
                    r'\s+([+-]?\d+(?:\.\d+)?)'
                    r'(?:\s+(linear|ease|ease-in|ease-out))?$')


class FxlError(Exception):
    pass


def parse_fxl(path):
    """Parse an FXL file into (palette, layers, rig).

    palette: char -> (r, g, b, a)
    layers:  list (bottom to top) of lists of row strings.
    rig:     (joints, bones) where joints: char -> (x, y, z) voxel coords
             and bones: list of (name, char, char).
    """
    palette = {}
    joints = {}
    joint_names = {}
    bones = []
    bone_names = set()
    hints = {}
    anims = {}
    defs = {}
    layers = []
    cur_rows = []
    cur_def = None
    cur_ref = None
    cur_anim = None

    def err(lineno, msg):
        raise FxlError('%s:%d: %s' % (path, lineno, msg))

    def close_slot():
        nonlocal cur_rows, cur_def, cur_ref, cur_anim
        if cur_anim is not None:
            anims[cur_anim['name']] = cur_anim
        elif cur_def is not None:
            defs[cur_def] = cur_rows
        elif cur_ref is not None:
            name, count = cur_ref
            layers.extend(defs[name] for _ in range(count))
        else:
            layers.append(cur_rows)
        cur_rows, cur_def, cur_ref, cur_anim = [], None, None, None

    with open(path) as f:
        raw_lines = f.readlines()

    for lineno, raw in enumerate(raw_lines, 1):
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        if re.fullmatch(r'-{3,}', line):
            close_slot()
        elif line.startswith('anim ') and line.endswith(':'):
            if cur_rows or cur_ref or cur_def is not None \
                    or cur_anim is not None:
                err(lineno, 'anim must start its own slot')
            m = ANIM_RE.match(line)
            if not m:
                err(lineno, 'malformed anim header')
            if m.group(1) in anims:
                err(lineno, 'duplicate animation name %r' % m.group(1))
            cur_anim = {'name': m.group(1), 'duration': float(m.group(2)),
                        'loop': bool(m.group(3)), 'keys': []}
        elif cur_anim is not None:
            m = KEY_RE.match(line)
            if not m:
                err(lineno, 'malformed keyframe %r' % line)
            pct = float(m.group(1))
            if pct > 100:
                err(lineno, 'keyframe percent > 100')
            ref = m.group(2)
            ch = ref if (len(ref) == 1 and ref in joints) \
                else joint_names.get(ref)
            if ch is None:
                err(lineno, 'keyframe for unknown joint %r' % ref)
            delta = (float(m.group(3)), float(m.group(4)), float(m.group(5)))
            cur_anim['keys'].append((pct / 100.0, ch, delta,
                                     m.group(6) or 'ease'))
        elif line.endswith(':'):
            name = line[:-1].strip()
            if not NAME_RE.match(name):
                err(lineno, 'bad layer name %r' % name)
            if name in defs:
                err(lineno, 'duplicate layer name %r' % name)
            if cur_rows or cur_ref or cur_def:
                err(lineno, 'definition must start its own slot')
            cur_def = name
        elif line.startswith('*'):
            if cur_def is not None:
                err(lineno, 'reference inside a definition body')
            if cur_rows or cur_ref:
                err(lineno, 'reference must be the only content of its slot')
            parts = line[1:].split()
            if not parts or not NAME_RE.match(parts[0]) or len(parts) > 2:
                err(lineno, 'malformed reference %r' % line)
            name = parts[0]
            if name not in defs:
                err(lineno, 'reference to undefined layer %r' % name)
            count = 1
            if len(parts) == 2:
                if not parts[1].isdigit() or int(parts[1]) < 1:
                    err(lineno, 'repeat count must be a positive integer')
                count = int(parts[1])
            cur_ref = (name, count)
        elif '=' in line:
            lhs, rhs = (s.strip() for s in line.split('=', 1))
            if rhs.split() and rhs.split()[0] == 'joint':
                jparts = rhs.split()
                if not CHAR_RE.match(lhs):
                    err(lineno, 'bad joint character %r' % lhs)
                if lhs in palette or lhs in joints:
                    err(lineno, 'character %r already bound' % lhs)
                hv = [0.0, 0.0, 0.0]
                has_hint = False
                for tok in jparts[1:]:
                    if HINT_RE.match(tok):
                        has_hint = True
                        for sgn, ax in re.findall(r'([+-])([xyz])', tok):
                            hv[{'x': 0, 'y': 1, 'z': 2}[ax]] += \
                                1.0 if sgn == '+' else -1.0
                    elif NAME_RE.match(tok) and tok not in joint_names:
                        joint_names[tok] = lhs
                    else:
                        err(lineno, 'bad joint name or hint %r' % tok)
                if has_hint:
                    n = math.sqrt(sum(c * c for c in hv))
                    if n < 1e-9:
                        err(lineno, 'bend hint sums to zero')
                    hints[lhs] = [c / n for c in hv]
                joints[lhs] = None
            elif rhs.split() and rhs.split()[0] == 'bone':
                parts = rhs.split()
                if not NAME_RE.match(lhs):
                    err(lineno, 'bad bone name %r' % lhs)
                if lhs in bone_names:
                    err(lineno, 'duplicate bone name %r' % lhs)
                if len(parts) not in (3, 4):
                    err(lineno, 'malformed bone declaration')
                if len(parts) == 4 and HINT_RE.match(parts[3]):
                    fv = [0.0, 0.0, 0.0]
                    for sgn, ax in re.findall(r'([+-])([xyz])', parts[3]):
                        fv[{'x': 0, 'y': 1, 'z': 2}[ax]] += \
                            1.0 if sgn == '+' else -1.0
                    n = math.sqrt(sum(c * c for c in fv))
                    if n < 1e-9:
                        err(lineno, 'facing sums to zero')
                    facing = [c / n for c in fv]
                    parts = parts[:3]
                else:
                    facing = None
                c1, c2 = parts[1], parts[2]
                if c1 == c2:
                    err(lineno, 'bone joints must be distinct')
                if c1 not in joints or c2 not in joints:
                    err(lineno, 'bone references an undeclared joint')
                bone_names.add(lhs)
                bones.append((lhs, c1, c2, facing))
            else:
                if not CHAR_RE.match(lhs):
                    err(lineno, 'bad palette character %r' % lhs)
                if lhs in palette or lhs in joints:
                    err(lineno, 'duplicate palette binding %r' % lhs)
                if not COLOR_RE.match(rhs):
                    err(lineno, 'malformed color %r' % rhs)
                r, g, b = (int(rhs[i:i + 2], 16) for i in (0, 2, 4))
                a = int(rhs[6:8], 16) if len(rhs) == 8 else 255
                if a == 0:
                    err(lineno, "alpha of zero is not allowed, use '.'")
                palette[lhs] = (r, g, b, a)
        else:
            if cur_ref is not None:
                err(lineno, 'grid row after a reference in the same slot')
            if ' ' in line or '\t' in line:
                err(lineno, 'interior whitespace in row')
            for ch in line:
                if ch != '.' and ch not in palette and ch not in joints:
                    err(lineno, 'unbound voxel character %r' % ch)
            cur_rows.append(line)

    if cur_rows or cur_def is not None or cur_ref is not None \
            or cur_anim is not None:
        close_slot()  # no trailing separator

    # Resolve joint markers (sudoku border notation, LANG.md section 7).
    occ = {}
    for yi, rows in enumerate(layers):
        for zi, row in enumerate(rows):
            for xi, ch in enumerate(row):
                if ch in joints:
                    occ.setdefault(ch, []).append((yi, zi, xi))
    for ch in joints:
        o = occ.get(ch, [])
        if not o:
            raise FxlError('%s: joint %r declared but never marked'
                           % (path, ch))
        if len({t[0] for t in o}) > 1:
            raise FxlError('%s: joint %r marked in more than one layer'
                           % (path, ch))
        if len(o) != 2:
            raise FxlError('%s: joint %r needs exactly 2 markers, found %d'
                           % (path, ch, len(o)))
        yi = o[0][0]
        rows = layers[yi]
        colm = rowm = None
        for _, zi, xi in o:
            on_row = zi in (0, len(rows) - 1)
            on_col = xi in (0, len(rows[zi]) - 1)
            if on_row and on_col:
                raise FxlError('%s: joint %r marker on a corner cell'
                               % (path, ch))
            if on_row:
                colm = xi
            elif on_col:
                rowm = zi
            else:
                raise FxlError('%s: joint %r marker not on a border'
                               % (path, ch))
        if colm is None or rowm is None:
            raise FxlError('%s: joint %r needs one border-row and one '
                           'border-column marker' % (path, ch))
        joints[ch] = (colm, yi, rowm)

    return palette, layers, (joints, bones, anims, hints)


def build_grids(palette, layers):
    """Return (dens, col): uint8 arrays indexed [x, y, z], with a 1-voxel
    empty apron so surface closes at the model boundary."""
    h = len(layers)
    d = max((len(rows) for rows in layers), default=0)
    w = max((len(r) for rows in layers for r in rows), default=0)
    if w == 0:
        raise FxlError('model is empty')
    dens = np.zeros((w + 2, h + 2, d + 2), np.uint8)
    col = np.zeros((w + 2, h + 2, d + 2, 3), np.uint8)
    for y, rows in enumerate(layers):
        for z, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch in palette:
                    r, g, b, a = palette[ch]
                    dens[x + 1, y + 1, z + 1] = a
                    col[x + 1, y + 1, z + 1] = (r, g, b)
    return dens, col


def marching_cubes(dens, col, flat=False):
    """IMPL.md §5-7. Returns (tri_pos, tri_col): float arrays (n, 3, 3).
    Positions are in voxel units; densities sit at voxel centers, hence the
    +0.5 offset (IMPL.md §6). World origin matches FXL coordinates."""
    corner = np.array(VERTICES_POSITIONS, float)
    tris, cols = [], []
    nx, ny, nz = dens.shape
    for cx in range(nx - 1):
        for cy in range(ny - 1):
            for cz in range(nz - 1):
                d = [int(dens[cx + dx, cy + dy, cz + dz])
                     for dx, dy, dz in VERTICES_POSITIONS]
                cube_index = 0
                for i, v in enumerate(d):
                    if v >= 127:
                        cube_index |= 1 << i
                edges = MC_EDGE_TABLE[cube_index]
                if not edges:
                    continue
                vpos = [None] * 12
                vcol = [None] * 12
                for e in range(12):
                    if not (edges & (1 << e)):
                        continue
                    v0, v1 = EDGES_VERTICES[e]
                    f0, f1 = d[v0] / 255.0, d[v1] / 255.0
                    mu = (f0 - 0.5) / (f0 - f1)
                    p = corner[v0] * (1 - mu) + corner[v1] * mu
                    if flat:
                        p = np.round(p * 2) / 2
                    vpos[e] = p
                    src = v0 if d[v0] > d[v1] else v1
                    dx, dy, dz = VERTICES_POSITIONS[src]
                    vcol[e] = col[cx + dx, cy + dy, cz + dz]
                base = np.array([cx - 1 + 0.5, cy - 1 + 0.5, cz - 1 + 0.5])
                row = MC_TRI_TABLE[cube_index]
                for i in range(0, 16, 3):
                    if row[i] == -1:
                        break
                    tris.append([base + vpos[row[i + k]] for k in range(3)])
                    cols.append([vcol[row[i + k]] for k in range(3)])
    if not tris:
        raise FxlError('no surface generated (all voxels below iso?)')
    return np.array(tris), np.array(cols, float)


# ---------------------------------------------------------------------------
# Minimal software renderer: perspective camera, z-buffer, flat shading.

def rotmat(yaw_deg, pitch_deg):
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    ry = np.array([[math.cos(yaw), 0, math.sin(yaw)],
                   [0, 1, 0],
                   [-math.sin(yaw), 0, math.cos(yaw)]])
    rx = np.array([[1, 0, 0],
                   [0, math.cos(pitch), -math.sin(pitch)],
                   [0, math.sin(pitch), math.cos(pitch)]])
    return rx @ ry


def make_cam(tri_pos, width, height, yaw_deg, pitch_deg, ss=2):
    """Fit a camera to a mesh; reuse across animation frames."""
    w, h = width * ss, height * ss
    rot = rotmat(yaw_deg, pitch_deg)
    verts = tri_pos.reshape(-1, 3)
    center = (verts.min(0) + verts.max(0)) / 2
    vcam = (verts - center) @ rot.T
    radius = np.linalg.norm(vcam, axis=1).max()
    dist = radius * 3.2
    depth = dist - vcam[:, 2]
    px_ratio = np.abs(vcam[:, :2]) / depth[:, None]
    focal = 0.44 * min(w, h) / px_ratio.max()
    return center, dist, focal


def render(tri_pos, tri_col, width, height, yaw_deg, pitch_deg, ss=2,
           rig=None, cam=None):
    w, h = width * ss, height * ss
    rot = rotmat(yaw_deg, pitch_deg)
    if cam is None:
        cam = make_cam(tri_pos, width, height, yaw_deg, pitch_deg, ss)
    center, dist, focal = cam

    verts = tri_pos.reshape(-1, 3)
    vcam = (verts - center) @ rot.T
    depth = dist - vcam[:, 2]
    sx = vcam[:, 0] * focal / depth + w / 2
    sy = h / 2 - vcam[:, 1] * focal / depth  # image y grows downward
    pts = np.stack([sx, sy], 1).reshape(-1, 3, 2)
    depth = depth.reshape(-1, 3)

    # Flat shading: per-triangle world normal, two-sided lambert.
    e1 = tri_pos[:, 1] - tri_pos[:, 0]
    e2 = tri_pos[:, 2] - tri_pos[:, 0]
    n = np.cross(e1, e2)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    light = np.array([-0.45, 0.8, 0.5])
    light /= np.linalg.norm(light)
    shade = 0.25 + 0.75 * np.abs(n @ light)
    base = tri_col.mean(1) / 255.0
    tcol = np.clip(base * shade[:, None], 0, 1)

    # Background: vertical gradient.
    img = np.zeros((h, w, 3))
    t = np.linspace(0, 1, h)[:, None]
    img[:] = (np.array([0.10, 0.09, 0.13]) * (1 - t)
              + np.array([0.22, 0.20, 0.28]) * t)[:, None, :]
    zbuf = np.full((h, w), np.inf)

    order = np.argsort(-depth.mean(1))  # far first (z-buffer makes it exact)
    for ti in order:
        p = pts[ti]
        x0 = max(int(np.floor(p[:, 0].min())), 0)
        x1 = min(int(np.ceil(p[:, 0].max())) + 1, w)
        y0 = max(int(np.floor(p[:, 1].min())), 0)
        y1 = min(int(np.ceil(p[:, 1].max())) + 1, h)
        if x0 >= x1 or y0 >= y1:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1) + 0.5,
                             np.arange(y0, y1) + 0.5)
        (ax, ay), (bx, by), (cx, cy) = p
        area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        if abs(area) < 1e-9:
            continue
        w0 = ((cx - bx) * (ys - by) - (cy - by) * (xs - bx)) / area
        w1 = ((ax - cx) * (ys - cy) - (ay - cy) * (xs - cx)) / area
        w2 = 1 - w0 - w1
        mask = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not mask.any():
            continue
        zi = w0 * depth[ti, 0] + w1 * depth[ti, 1] + w2 * depth[ti, 2]
        zwin = zbuf[y0:y1, x0:x1]
        mask &= zi < zwin
        zwin[mask] = zi[mask]
        img[y0:y1, x0:x1][mask] = tcol[ti]

    img = img.reshape(height, ss, width, ss, 3).mean((1, 3))

    if rig is not None:
        jpts, segs = rig
        BONE_C = np.array([1.0, 0.65, 0.1])
        JOINT_C = np.array([0.15, 0.9, 1.0])

        def project(p):
            v = (np.asarray(p, float) - center) @ rot.T
            dd = dist - v[2]
            return (v[0] * focal / dd + w / 2) / ss, \
                   (h / 2 - v[1] * focal / dd) / ss

        def blend(yi, xi, color, a):
            if 0 <= yi < height and 0 <= xi < width:
                img[yi, xi] = img[yi, xi] * (1 - a) + color * a

        for p0, p1 in segs:
            (x0, y0), (x1, y1) = project(p0), project(p1)
            n = int(max(abs(x1 - x0), abs(y1 - y0)) * 2) + 2
            for t in np.linspace(0, 1, n):
                xi = int(x0 + (x1 - x0) * t)
                yi = int(y0 + (y1 - y0) * t)
                for oy in (-1, 0):
                    for ox in (-1, 0):
                        blend(yi + oy, xi + ox, BONE_C, 0.8)
        for p in jpts:
            xc, yc = project(p)
            for oy in range(-3, 4):
                for ox in range(-3, 4):
                    if ox * ox + oy * oy <= 9:
                        blend(int(yc) + oy, int(xc) + ox, JOINT_C, 0.9)

    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def _chunk(tag, data):
    c = struct.pack('>I', len(data)) + tag + data
    return c + struct.pack('>I', zlib.crc32(tag + data))


def _scanlines(img):
    return b''.join(b'\x00' + img[y].tobytes() for y in range(img.shape[0]))


def write_png(path, img):
    h, w, _ = img.shape
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(_chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)))
        f.write(_chunk(b'IDAT', zlib.compress(_scanlines(img), 9)))
        f.write(_chunk(b'IEND', b''))


def write_apng(path, frames, fps):
    """Animated PNG: all frames full-size, looping forever."""
    h, w, _ = frames[0].shape
    seq = 0
    parts = [b'\x89PNG\r\n\x1a\n',
             _chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)),
             _chunk(b'acTL', struct.pack('>II', len(frames), 0))]
    for i, img in enumerate(frames):
        parts.append(_chunk(b'fcTL', struct.pack(
            '>IIIIIHHBB', seq, w, h, 0, 0, 1, fps, 0, 0)))
        seq += 1
        raw = zlib.compress(_scanlines(img), 9)
        if i == 0:
            parts.append(_chunk(b'IDAT', raw))
        else:
            parts.append(_chunk(b'fdAT', struct.pack('>I', seq) + raw))
            seq += 1
    parts.append(_chunk(b'IEND', b''))
    with open(path, 'wb') as f:
        f.write(b''.join(parts))


# ---------------------------------------------------------------------------
# Animation: IK-interpolated keyframes (LANG.md section 8).

def _norm(v):
    return v / max(np.linalg.norm(v), 1e-12)


def rot_between(d0, d1):
    """Minimal rotation matrix taking direction d0 to d1."""
    d0, d1 = _norm(np.asarray(d0, float)), _norm(np.asarray(d1, float))
    c = np.cross(d0, d1)
    s = np.linalg.norm(c)
    co = float(np.dot(d0, d1))
    if s < 1e-9:
        if co > 0:
            return np.eye(3)
        a = np.array([1., 0, 0]) if abs(d0[0]) < 0.9 else np.array([0, 1., 0])
        axis, ang = _norm(np.cross(d0, a)), math.pi
    else:
        axis, ang = c / s, math.atan2(s, co)
    K = np.array([[0, -axis[2], axis[1]],
                  [axis[2], 0, -axis[0]],
                  [-axis[1], axis[0], 0]])
    return np.eye(3) + math.sin(ang) * K + (1 - math.cos(ang)) * (K @ K)


def build_tree(joints, bones):
    parent, children = {}, {}
    for _, c1, c2, _f in bones:
        if c2 in parent:
            raise FxlError('joint %r has two parent bones' % c2)
        parent[c2] = c1
        children.setdefault(c1, []).append(c2)
    involved = set(parent) | set(children)
    roots = [c for c in involved if c not in parent]
    if len(roots) != 1:
        raise FxlError('rig must have exactly one root joint')
    return roots[0], parent, children


def _eased(f, kind):
    if kind == 'linear':
        return f
    if kind == 'ease-in':
        return f * f
    if kind == 'ease-out':
        return 1 - (1 - f) ** 2
    return f * f * (3 - 2 * f)          # ease (smoothstep)


def anim_targets(anim, rest, u):
    """Absolute target position per keyframed joint at time u in [0,1].
    Returns (targets dict, joint order of first appearance)."""
    per, order = {}, []
    for t, ch, d, e in anim['keys']:
        if ch not in per:
            per[ch] = []
            order.append(ch)
        per[ch].append((t, np.array(d, float), e))
    targets = {}
    for ch in order:
        keys = sorted(per[ch], key=lambda k: k[0])
        if anim['loop'] and len(keys) > 1:
            keys = ([(keys[-1][0] - 1.0, keys[-1][1], keys[-1][2])] + keys
                    + [(keys[0][0] + 1.0, keys[0][1], keys[0][2])])
        if u <= keys[0][0]:
            d = keys[0][1]
        elif u >= keys[-1][0]:
            d = keys[-1][1]
        else:
            for i in range(len(keys) - 1):
                if keys[i][0] <= u <= keys[i + 1][0]:
                    t0, d0, _ = keys[i]
                    t1, d1, e1 = keys[i + 1]
                    f = 0.0 if t1 == t0 else (u - t0) / (t1 - t0)
                    d = d0 + (d1 - d0) * _eased(f, e1)
                    break
        targets[ch] = np.array(rest[ch], float) + d
    return targets, order


def solve_pose(rest, root, parent, children, targets, order,
               hints={}):
    """FABRIK IK toward targets; other joints follow rigidly."""
    pose = {c: np.array(rest[c], float) for c in rest}
    rot = {c: np.eye(3) for c in rest}
    if root in targets:
        shift = targets[root] - np.array(rest[root], float)
        for c in pose:
            pose[c] = pose[c] + shift
    done = {root}
    for eff in order:
        if eff == root:
            continue
        chain = [eff]
        a = parent.get(eff)
        while a is not None and a not in done:
            chain.append(a)
            a = parent.get(a)
        if a is None:
            continue                    # effector not connected to root
        chain.append(a)
        chain.reverse()
        # The first bone of a chain is RIGID: the socket (chain[1]) rides
        # its base's body -- the pelvis->hip and chest->shoulder bones
        # never hinge, so sockets cannot dislocate. IK bends only from
        # the socket outward.
        if len(chain) >= 3:
            b0 = np.array(rest[chain[0]], float)
            s0 = np.array(rest[chain[1]], float)
            pose[chain[1]] = pose[chain[0]] + rot[chain[0]] @ (s0 - b0)
            rot[chain[1]] = rot[chain[0]]
            sub = chain[1:]
        else:
            sub = chain
        pts = [pose[c].copy() for c in sub]
        rl = [np.linalg.norm(np.array(rest[sub[i + 1]], float)
                             - np.array(rest[sub[i]], float))
              for i in range(len(sub) - 1)]
        tgt = targets[eff]
        base = pts[0].copy()
        # Pre-rotate the limb rigidly about the socket toward the target
        # so the swing is carried by the proximal joint (FABRIK alone
        # favors distal joints: shin swings, thigh freezes).
        if len(pts) >= 3:
            v0, v1 = pts[-1] - base, tgt - base
            if np.linalg.norm(v0) > 1e-6 and np.linalg.norm(v1) > 1e-6:
                rpre = rot_between(v0, v1)
                for i in range(1, len(pts)):
                    pts[i] = base + rpre @ (pts[i] - base)
        # Bend hints break FABRIK's straight-chain degeneracy: a knee
        # marked '+z' buckles forward, an elbow '-z' backward.
        for i in range(1, len(pts) - 1):
            hv = hints.get(sub[i])
            if hv is not None:
                pts[i] = pts[i] + rot[sub[0]] @ (np.array(hv) * 2.0)
        for _ in range(12):
            pts[-1] = tgt.copy()
            for i in range(len(pts) - 2, -1, -1):
                pts[i] = pts[i + 1] + _norm(pts[i] - pts[i + 1]) * rl[i]
            pts[0] = base.copy()
            for i in range(len(pts) - 1):
                pts[i + 1] = pts[i] + _norm(pts[i + 1] - pts[i]) * rl[i]
        for i, c in enumerate(sub):
            pose[c] = pts[i]
        # Compose rotations incrementally along the chain: each segment
        # rotates minimally relative to its already-rotated parent, which
        # keeps roll stable even for large total rotations.
        racc = rot[sub[0]]
        for i in range(len(sub) - 1):
            d0 = (np.array(rest[sub[i + 1]], float)
                  - np.array(rest[sub[i]], float))
            ri = rot_between(racc @ d0, pts[i + 1] - pts[i]) @ racc
            rot[sub[i + 1]] = ri
            racc = ri
        done.update(chain)

    def fk(c):
        for k in children.get(c, []):
            if k not in done:
                off = np.array(rest[k], float) - np.array(rest[c], float)
                pose[k] = pose[c] + rot[c] @ off
                rot[k] = rot[c]
                done.add(k)
            fk(k)
    fk(root)
    return pose, rot


def apply_facing(pose, rot, rest, bones):
    """Twist each facing-constrained bone about its own axis so that its
    rest-space facing direction stays pointing that way in world space
    (e.g. a palm keeps facing forward). Position targets cannot control
    this roll, so it is declared on the bone (LANG.md section 7)."""
    for _, c1, c2, facing in bones:
        if facing is None:
            continue
        up = np.array(facing, float)
        d1 = _norm(pose[c2] - pose[c1])
        a = rot[c2] @ up
        ap = a - d1 * (a @ d1)
        upp = up - d1 * (up @ d1)
        na, nu = np.linalg.norm(ap), np.linalg.norm(upp)
        if na < 1e-6 or nu < 1e-6:
            continue
        ap, upp = ap / na, upp / nu
        ang = math.atan2(float(np.cross(ap, upp) @ d1), float(ap @ upp))
        K = np.array([[0, -d1[2], d1[1]],
                      [d1[2], 0, -d1[0]],
                      [-d1[1], d1[0], 0]])
        tw = np.eye(3) + math.sin(ang) * K + (1 - math.cos(ang)) * (K @ K)
        rot[c2] = tw @ rot[c2]


def skin_bind(tri_pos, dens, rest, bones):
    """Part-coherent rigid binding. Bones seed the solid voxels they pass
    through; labels flood outward THROUGH the body (6-connected BFS over
    solid voxels), so parts bind by anatomy, not by straight-line
    proximity -- a fingertip near the thigh still belongs to the hand.
    Triangles take the label of the nearest labeled voxel."""
    from collections import deque
    solid = dens >= 127
    label = np.full(solid.shape, -1, int)
    dq = deque()
    for bi, (_, c1, c2, _f) in enumerate(bones):
        a = np.array(rest[c1], float)
        b = np.array(rest[c2], float)
        n = int(np.linalg.norm(b - a) * 2) + 2
        for t in np.linspace(0, 1, n):
            p = a + (b - a) * t
            ix = int(round(p[0] - 0.5)) + 1
            iy = int(round(p[1] - 0.5)) + 1
            iz = int(round(p[2] - 0.5)) + 1
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        x, y, z = ix + dx, iy + dy, iz + dz
                        if 0 <= x < solid.shape[0] \
                                and 0 <= y < solid.shape[1] \
                                and 0 <= z < solid.shape[2] \
                                and solid[x, y, z] and label[x, y, z] < 0:
                            label[x, y, z] = bi
                            dq.append((x, y, z))
    while dq:
        x, y, z = dq.popleft()
        for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0),
                           (0, -1, 0), (0, 0, 1), (0, 0, -1)):
            nx, ny, nz = x + dx, y + dy, z + dz
            if 0 <= nx < solid.shape[0] and 0 <= ny < solid.shape[1] \
                    and 0 <= nz < solid.shape[2] \
                    and solid[nx, ny, nz] and label[nx, ny, nz] < 0:
                label[nx, ny, nz] = label[x, y, z]
                dq.append((nx, ny, nz))

    lx, ly, lz = np.nonzero(label >= 0)
    lpos = np.stack([lx - 0.5, ly - 0.5, lz - 0.5], axis=1)  # world coords
    lval = label[lx, ly, lz]
    cents = tri_pos.mean(axis=1)
    bind = np.zeros(len(cents), int)
    # Nearest labeled voxel per triangle centroid (chunked for memory).
    for i in range(0, len(cents), 2048):
        c = cents[i:i + 2048]
        d2 = ((c[:, None, :] - lpos[None, :, :]) ** 2).sum(2)
        bind[i:i + 2048] = lval[np.argmin(d2, axis=1)]
    return bind


def skin_apply(tri_pos, bind, rest, pose, rots, bones):
    """Rigidly transform each triangle by its bone (rotation from the IK
    solve, so roll is consistent along chains)."""
    out = tri_pos.copy()
    for bi, (_, c1, c2, _f) in enumerate(bones):
        m = bind == bi
        if not m.any():
            continue
        a0 = np.array(rest[c1], float)
        rb = rots[c2]
        out[m] = (tri_pos[m] - a0) @ rb.T + pose[c1]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('input')
    ap.add_argument('-o', '--output')
    ap.add_argument('--flat', action='store_true',
                    help='snap vertices to half-voxel increments (IMPL.md §6)')
    ap.add_argument('--rig', action='store_true',
                    help='overlay the animation rig (joints and bones)')
    ap.add_argument('--anim', metavar='NAME',
                    help='render an animation to an animated PNG')
    ap.add_argument('--fps', type=int, default=12)
    ap.add_argument('--yaw', type=float, default=25.0)
    ap.add_argument('--pitch', type=float, default=-12.0)
    ap.add_argument('--width', type=int, default=720)
    ap.add_argument('--height', type=int, default=900)
    args = ap.parse_args()
    out = args.output or re.sub(r'\.fxl$', '', args.input) + '.png'

    try:
        palette, layers, (joints, bones, anims, hints) = \
            parse_fxl(args.input)
        dens, col = build_grids(palette, layers)
        tri_pos, tri_col = marching_cubes(dens, col, flat=args.flat)
    except FxlError as e:
        sys.exit('error: %s' % e)

    nvox = int(np.count_nonzero(dens))
    print('%s: %d voxels, %d layers -> %d triangles'
          % (args.input, nvox, len(layers), len(tri_pos)))
    if joints:
        print('rig: %d joints, %d bones, %d animations'
              % (len(joints), len(bones), len(anims)))

    if args.anim:
        if args.anim not in anims:
            sys.exit('error: no animation %r (have: %s)'
                     % (args.anim, ', '.join(anims) or 'none'))
        anim = anims[args.anim]
        try:
            root, parent, children = build_tree(joints, bones)
        except FxlError as e:
            sys.exit('error: %s' % e)
        rest = {c: (p[0] + 0.5, p[1] + 0.5, p[2] + 0.5)
                for c, p in joints.items()}
        bind = skin_bind(tri_pos, dens, rest, bones)
        cam = make_cam(tri_pos, args.width, args.height,
                       args.yaw, args.pitch)
        n = max(2, int(round(anim['duration'] * args.fps)))
        frames = []
        for i in range(n):
            u = i / n if anim['loop'] else i / (n - 1)
            targets, order = anim_targets(anim, rest, u)
            pose, rots = solve_pose(rest, root, parent, children,
                                    targets, order, hints)
            apply_facing(pose, rots, rest, bones)
            fpos = skin_apply(tri_pos, bind, rest, pose, rots, bones)
            frames.append(render(fpos, tri_col,
                                 args.width, args.height,
                                 args.yaw, args.pitch, cam=cam))
            print('frame %d/%d' % (i + 1, n))
        out = args.output or re.sub(r'\.fxl$', '', args.input) \
            + '_%s.png' % args.anim
        write_apng(out, frames, args.fps)
        print('wrote %s (%d frames @ %d fps, %s)'
              % (out, n, args.fps, 'loop' if anim['loop'] else 'once'))
        return

    rig = None
    if args.rig and joints:
        jw = {c: (p[0] + 0.5, p[1] + 0.5, p[2] + 0.5)
              for c, p in joints.items()}
        rig = (list(jw.values()),
               [(jw[c1], jw[c2]) for _, c1, c2, _f in bones])
    img = render(tri_pos, tri_col, args.width, args.height,
                 args.yaw, args.pitch, rig=rig)
    write_png(out, img)
    print('wrote %s (%dx%d)' % (out, args.width, args.height))


if __name__ == '__main__':
    main()

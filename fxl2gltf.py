#!/usr/bin/env python3
"""Export an FXL model (LANG.md) to glTF binary (.glb) for Godot & co.

Exports the marching-cubes mesh with vertex colors, the rig as a glTF
skeleton (rigid per-triangle skinning), and every animation baked by
sampling the IK solver at --fps. Godot imports the .glb natively; set
looping per animation in the Import dock (or play with loop enabled).

Usage: python3 fxl2gltf.py skeleton.fxl [-o skeleton.glb]
                           [--fps 30] [--scale 0.02]
"""
import argparse
import json
import math
import re
import struct
import sys

import numpy as np

import render

CT_FLOAT, CT_UBYTE = 5126, 5121
NCOMP = {'SCALAR': 1, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


class Glb:
    def __init__(self):
        self.bin = bytearray()
        self.views = []
        self.accessors = []

    def accessor(self, arr, gtype, ctype, minmax=False):
        data = arr.tobytes()
        while len(self.bin) % 4:
            self.bin += b'\x00'
        self.views.append({'buffer': 0, 'byteOffset': len(self.bin),
                           'byteLength': len(data)})
        self.bin += data
        acc = {'bufferView': len(self.views) - 1, 'componentType': ctype,
               'count': len(arr), 'type': gtype}
        if ctype == CT_UBYTE:
            pass
        if minmax:
            acc['min'] = [float(v) for v in np.min(arr, axis=0).ravel()]
            acc['max'] = [float(v) for v in np.max(arr, axis=0).ravel()]
        self.accessors.append(acc)
        return len(self.accessors) - 1


def mat_to_quat(m):
    """3x3 rotation matrix -> (x, y, z, w) quaternion."""
    t = m[0, 0] + m[1, 1] + m[2, 2]
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        return ((m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s,
                (m[1, 0] - m[0, 1]) / s, 0.25 * s)
    i = int(np.argmax([m[0, 0], m[1, 1], m[2, 2]]))
    if i == 0:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        return (0.25 * s, (m[0, 1] + m[1, 0]) / s,
                (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s)
    if i == 1:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        return ((m[0, 1] + m[1, 0]) / s, 0.25 * s,
                (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s)
    s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
    return ((m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s,
            0.25 * s, (m[1, 0] - m[0, 1]) / s)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('input')
    ap.add_argument('-o', '--output')
    ap.add_argument('--fps', type=int, default=30,
                    help='animation bake rate (default 30)')
    ap.add_argument('--scale', type=float, default=0.02,
                    help='voxel size in meters (default 0.02)')
    args = ap.parse_args()
    out = args.output or re.sub(r'\.fxl$', '', args.input) + '.glb'
    s = args.scale

    try:
        palette, scene, (joints, bones, anims, hints, skin_mode) = \
            render.parse_fxl(args.input)
        tri_pos, tri_col, tri_hard, dens = render.mesh_scene(palette,
                                                             scene)
    except render.FxlError as e:
        sys.exit('error: %s' % e)

    print('%s: %d triangles, %d joints, %d bones, %d animations'
          % (args.input, len(tri_pos), len(joints), len(bones), len(anims)))

    glb = Glb()
    verts = tri_pos.reshape(-1, 3).astype(np.float32) * s
    normals = render.smooth_normals(tri_pos, tri_hard=tri_hard) \
        .reshape(-1, 3).astype(np.float32)
    colors = np.repeat(render.base_colors(tri_col, tri_hard), 3,
                       axis=0).astype(np.float32)

    attributes = {
        'POSITION': glb.accessor(verts, 'VEC3', CT_FLOAT, minmax=True),
        'NORMAL': glb.accessor(normals, 'VEC3', CT_FLOAT),
        'COLOR_0': glb.accessor(colors, 'VEC3', CT_FLOAT),
    }

    nodes = []
    skins = []
    animations = []
    scene_nodes = []
    rigged = bool(bones)

    if rigged:
        rest = {c: np.array([p[0] + .5, p[1] + .5, p[2] + .5])
                for c, p in joints.items()}
        root, parent, children = render.build_tree(joints, bones)
        jattr = np.zeros((len(verts), 4), np.uint8)
        wattr = np.zeros((len(verts), 4), np.float32)
        if skin_mode == 'elastic':
            eidx, ewts = render.skin_bind_elastic(tri_pos, dens, rest,
                                                  bones)
            jattr[:, 0] = eidx[:, 0]
            jattr[:, 1] = eidx[:, 1]
            wattr[:, 0] = ewts[:, 0]
            wattr[:, 1] = ewts[:, 1]
        else:
            bind = render.skin_bind(tri_pos, dens, rest, bones)
            jattr[:, 0] = np.repeat(bind, 3)
            wattr[:, 0] = 1.0
        attributes['JOINTS_0'] = glb.accessor(jattr, 'VEC4', CT_UBYTE)
        glb.accessors[-1]['normalized'] = False
        attributes['WEIGHTS_0'] = glb.accessor(wattr, 'VEC4', CT_FLOAT)

        # Node 0: armature root at the root joint. Node 1+i: bone i,
        # positioned at its parent joint (c1); its rotation carries the
        # bone, matching render.py's skinning exactly.
        bone_of_child = {c2: i for i, (_, c1, c2, _f) in enumerate(bones)}
        nodes.append({'name': 'root',
                      'translation': [float(v) for v in rest[root] * s],
                      'children': []})
        for i, (name, c1, c2, _f) in enumerate(bones):
            local = (rest[c1] - rest[root] if c1 == root
                     else rest[c1] - rest[bones[bone_of_child[c1]][1]])
            nodes.append({'name': name,
                          'translation': [float(v) for v in local * s]})
            pn = 0 if c1 == root else 1 + bone_of_child[c1]
            nodes[pn].setdefault('children', []).append(1 + i)

        ibms = np.zeros((len(bones), 16), np.float32)
        for i, (_, c1, c2, _f) in enumerate(bones):
            m = np.eye(4)
            m[:3, 3] = -rest[c1] * s
            ibms[i] = m.T.ravel()          # column-major
        skins.append({'joints': list(range(1, 1 + len(bones))),
                      'skeleton': 0,
                      'inverseBindMatrices':
                          glb.accessor(ibms, 'MAT4', CT_FLOAT)})
        scene_nodes.append(0)

        for aname, anim in anims.items():
            nfr = max(2, int(round(anim['duration'] * args.fps)))
            steps = nfr + 1 if anim['loop'] else nfr
            times = np.array([i * anim['duration'] / nfr
                              for i in range(steps)], np.float32)
            trs = {ni: {'t': [], 'r': []} for ni in range(len(nodes))}
            prevq = {}
            for i in range(steps):
                u = (i % nfr) / nfr if anim['loop'] else i / (nfr - 1)
                targets, order = render.anim_targets(anim, rest, u)
                pose, rots = render.solve_pose(rest, root, parent, children,
                                               targets, order, hints)
                render.apply_facing(pose, rots, rest, bones)
                trs[0]['t'].append(pose[root] * s)
                trs[0]['r'].append((0, 0, 0, 1))
                for bi, (_, c1, c2, _f) in enumerate(bones):
                    if c1 == root:
                        pr, pt = np.eye(3), pose[root]
                    else:
                        pb = bones[bone_of_child[c1]]
                        pr, pt = rots[c1], pose[pb[1]]
                    lr = pr.T @ rots[c2]
                    lt = pr.T @ (pose[c1] - pt)
                    q = np.array(mat_to_quat(lr))
                    if (1 + bi) in prevq and float(q @ prevq[1 + bi]) < 0:
                        q = -q
                    prevq[1 + bi] = q
                    trs[1 + bi]['t'].append(lt * s)
                    trs[1 + bi]['r'].append(tuple(q))
            tacc = glb.accessor(times, 'SCALAR', CT_FLOAT, minmax=True)
            samplers, channels = [], []
            for ni in range(len(nodes)):
                ta = glb.accessor(np.array(trs[ni]['t'], np.float32),
                                  'VEC3', CT_FLOAT)
                ra = glb.accessor(np.array(trs[ni]['r'], np.float32),
                                  'VEC4', CT_FLOAT)
                samplers.append({'input': tacc, 'output': ta,
                                 'interpolation': 'LINEAR'})
                channels.append({'sampler': len(samplers) - 1,
                                 'target': {'node': ni,
                                            'path': 'translation'}})
                samplers.append({'input': tacc, 'output': ra,
                                 'interpolation': 'LINEAR'})
                channels.append({'sampler': len(samplers) - 1,
                                 'target': {'node': ni, 'path': 'rotation'}})
            animations.append({'name': aname, 'samplers': samplers,
                               'channels': channels})
            print('baked %r: %d frames' % (aname, steps))

    mesh_node = {'name': 'model', 'mesh': 0}
    if rigged:
        mesh_node['skin'] = 0
    nodes.append(mesh_node)
    scene_nodes.append(len(nodes) - 1)

    gltf = {
        'asset': {'version': '2.0', 'generator': 'fxl2gltf'},
        'scene': 0,
        'scenes': [{'nodes': scene_nodes}],
        'nodes': nodes,
        'meshes': [{'primitives': [{'attributes': attributes,
                                    'material': 0, 'mode': 4}]}],
        'materials': [{'name': 'voxel',
                       'pbrMetallicRoughness': {
                           'baseColorFactor': [1, 1, 1, 1],
                           'metallicFactor': 0.0,
                           'roughnessFactor': 0.9}}],
        'bufferViews': glb.views,
        'accessors': glb.accessors,
        'buffers': [{'byteLength': len(glb.bin)}],
    }
    if skins:
        gltf['skins'] = skins
    if animations:
        gltf['animations'] = animations

    js = json.dumps(gltf, separators=(',', ':')).encode()
    js += b' ' * (-len(js) % 4)
    bb = bytes(glb.bin) + b'\x00' * (-len(glb.bin) % 4)
    total = 12 + 8 + len(js) + 8 + len(bb)
    with open(out, 'wb') as f:
        f.write(struct.pack('<III', 0x46546C67, 2, total))
        f.write(struct.pack('<II', len(js), 0x4E4F534A) + js)
        f.write(struct.pack('<II', len(bb), 0x004E4942) + bb)
    print('wrote %s (%.1f KB, scale %g m/voxel)'
          % (out, total / 1024, s))


if __name__ == '__main__':
    main()

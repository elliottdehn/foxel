# AGENTS.md — working on foxel

Guidance for AI agents working in this repo. Read this first; it encodes
lessons that took many iterations to learn.

## What this is

FXL is a plain-text language for colored voxel models: ASCII layers
(bottom to top), one character per voxel, plus an animation rig and
IK-keyframed animations — all in one file. The renderer meshes voxels
with goxel-style marching cubes, where **the alpha channel is a density
field** and sub-threshold voxels sculpt smooth surfaces.

## File map

| File | Role |
|---|---|
| `LANG.md` | The FXL spec. Normative. Update it whenever the language changes. |
| `IMPL.md` | How goxel's marching cubes works; the renderer replicates it. |
| `render.py` | Parser, MC mesher, IK solver, skinning, software rasterizer, PNG/APNG writer. The reference implementation. |
| `mc_tables.py` | MC lookup tables, extracted verbatim from `goxel/src/marchingcube.c`. Never edit. |
| `make_skeleton.py` | Generates `skeleton.fxl`. Body = parameterized loops; skull = hand-drawn ASCII layers; rig + animations emitted at the end. |
| `skeleton.fxl` | GENERATED — never hand-edit. Change `make_skeleton.py` and rerun. |
| `png2mp4.py` | APNG → H.264 MP4 via macOS AVFoundation (embedded Swift helper). No ffmpeg on this machine. |
| `fxl2gltf.py` | FXL → .glb (mesh + skeleton + baked animations) for Godot etc. |
| `goxel/` | Upstream goxel checkout, reference only. |

## Command cheat sheet

```sh
python3 make_skeleton.py                       # regenerate skeleton.fxl
python3 render.py skeleton.fxl                 # still render -> skeleton.png
python3 render.py skeleton.fxl --yaw 80        # side view
python3 render.py skeleton.fxl --rig           # overlay joints/bones
python3 render.py skeleton.fxl --anim walk --fps 14   # -> APNG
python3 png2mp4.py skeleton_walk.png           # -> MP4 (loops 4x)
python3 fxl2gltf.py skeleton.fxl               # -> skeleton.glb
```

## The one workflow rule

**Always render and LOOK at the image after any change.** Every visual
judgment in this project (skull shape, gait, hand roll) was made by
rendering a PNG and reading it. Render close-ups by cropping the density
grid before meshing:

```python
import render
palette, layers, (joints, bones, anims, hints) = render.parse_fxl('skeleton.fxl')
dens, col = render.build_grids(palette, layers)
dens = dens[:, 64:, :].copy(); col = col[:, 64:, :].copy()  # head only
dens[:, 0, :] = 0                                # cap the cut cleanly
tp, tc = render.marching_cubes(dens, col)
render.write_png('head.png', render.render(tp, tc, 800, 800, 16, -4))
```

To render a single animation pose, copy the loop body from `render.py`
main(): `anim_targets` → `solve_pose` → `apply_facing` → `skin_apply` →
`render` (pass `cam=make_cam(rest_mesh, ...)` so the camera doesn't
drift between frames).

## Modeling: how to use the alpha mechanic

- Iso threshold is alpha 127 (`>= 127` = solid). Surface position along
  each edge interpolates to iso 0.5, so intermediate alphas *move* the
  surface: high alpha fattens, low slims (see IMPL.md §5–7).
- The generator's halo pass wraps halo-eligible bone in a graded 3-shell
  falloff (alpha 64/28/12). Shell 1 at ~64 puts the crossing near
  half-voxel → steps render as 45° chamfers. Alpha ~96+ bulges 0.8 of a
  voxel and looks inflated; tune with the mu formula, not by guessing.
- Things that must stay CRISP opt OUT of the halo (`halo=False`): ribs,
  spine, teeth, fingers. One voxel of gap survives only without shells.
- Cavities (eye sockets, mouth, nose) are carved AFTER the halo pass
  ('x' cells in the skull art) so shells can't fog them; dark back-wall
  voxels ('e') make them read black. 1-voxel features get color-averaged
  into invisibility — make dark features 2+ voxels or use carved holes.
- Sub-threshold halo carries NO connectivity: a limb "attached" only
  through halo voxels is visually detached. Solid paths only.

## Modeling: shape lessons (hard-won)

- **Icon beats anatomy** at this resolution. The skull works because it
  is four bold reads: huge dark sockets, nose triangle, picket-fence
  grin, smooth dome. Detail that competes with silhouette hurts.
- **Silhouette from every side.** Check `--yaw 80` side views; the head
  was a "peanut" until the occiput got depth and the face tucked under
  the cranium. Taper widths through a form (jaw 5 → grin 9 → eyes 11 →
  dome 13) and step front planes back in z to avoid flat "mask" faces.
- Dome/round forms: change plan width by 2 per single layer (staircase),
  never repeat-then-jump-4 (brick terraces).
- At higher resolution the halo smooths *less* (fixed 1–2 voxel radius),
  so curves must come from the art: more, finer steps.

## Rig & animation principles

The animation layer is positions-only by design — authors (human or AI)
never write a rotation. Controls, in order of preference:

1. **Keyframe a joint** to place it — and to PIN it: IK chains stop at
   the nearest keyframed ancestor. Pin `chest` so arm gestures don't
   bend the spine; keyframe elbows to keep walk arms hugging the ribs.
2. **Bend hints** on joint decls (`k = joint knee_l +z`, elbows
   `+x-y`) pick which way a straight chain buckles. Compound axes sum.
3. **Facing** on bone decls (`hand_r = bone W F -x+z`) fixes roll about
   the bone's own axis — the one DOF no position target can reach.
   Aim a leaf joint (fingertip) to control direction; facing for twist.
4. Solver invariants (in `render.py`, don't regress): the first bone of
   every chain is rigid (sockets never dislocate); chains pre-rotate
   about the socket so hips/shoulders carry the swing (FABRIK alone
   freezes proximal joints); chain rotations compose incrementally
   (stable roll at large angles).

Skinning is per-triangle rigid with **geodesic** binding (flood-fill
through solid voxels from each bone). Never bind by straight-line
distance: fingertips sit nearer the thigh bone than the hand bone.
Parts that must move independently need their own bone — feet tilted
with the shins until foot bones (ankle→toe) existed; pinning toes is
what keeps feet flat in the idle.

Animation feel: walks need pelvis sway + chest counter-sway + head nod,
not just leg targets; place stride extremes at the edge of reach so
planted legs straighten while swinging legs bend. Keep flare offsets
uniform along a limb (elbow AND wrist), or the forearm kinks.

## Gotchas

- `np.seterr(all='ignore')` in render.py silences *spurious* macOS
  Accelerate matmul warnings. Mesh data is verified finite; don't
  "fix" this by removing it, and don't trust new NaNs to warn.
- Joint markers use sudoku border notation (LANG.md §7); the generator
  injects them into emitted layers and asserts the cells are blank.
  Two joints in one layer must use opposite borders.
- The FXL emitter dedupes identical layers into defs/refs automatically;
  marked (jointed) layers become unique. That is expected.
- `png2mp4.py` decodes only the APNG dialect `render.py` writes
  (8-bit RGB, filter 0, full frames).
- glTF export BAKES the IK (glTF has no IK) by sampling the solver;
  the round-trip skinning check in the git/session history matched the
  renderer to 0.000000 m — keep that property when touching either side.
- Layer rows must be exactly W chars; generator asserts catch mistakes.
  When writing skull art, count dots: side padding = (43 - width) / 2.

## When extending the language

Update in lockstep: `LANG.md` (spec §s + grammar + error table) →
`render.py` (parse + validate + semantics) → `make_skeleton.py`
(emit it) → regenerate → render → LOOK. New syntax should follow the
house style: line-based, `=` declarations with the palette, slots
delimited by `---`, and semantics that never require the author to do
rotation math or per-frame arithmetic.

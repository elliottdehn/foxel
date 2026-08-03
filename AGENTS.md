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
| `make_goblin.py` | Generates `goblin.fxl`. Demonstrates the newer analytic-density techniques: soft ellipsoids/cones, 10-grade shells, sharp zones, dark-liner color isolation. |
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
palette, scene, (joints, bones, anims, hints, skin_mode) = \
    render.parse_fxl('skeleton.fxl')
# scene is a list of (layers, offset) parts; classic files have one.
layers, _ = scene[0]
dens, col, hard = render.build_grids(palette, layers)
dens = dens[:, 64:, :].copy(); col = col[:, 64:, :].copy()  # head only
hard = hard[:, 64:, :].copy()
dens[:, 0, :] = 0                                # cap the cut cleanly
tp, tc, th = render.marching_cubes(dens, col, hard=hard)
tn = render.smooth_normals(tp, tri_hard=th)
render.write_png('head.png',
    render.render(tp, tc, 800, 800, 16, -4, tri_norm=tn, tri_hard=th))
# whole composed scenes: tp, tc, th, dens = render.mesh_scene(palette, scene)
```

To render a single animation pose, copy the loop body from `render.py`
main(): `anim_targets` → `solve_pose` → `apply_facing` → `skin_apply` →
`render` (pass `cam=make_cam(rest_mesh, ...)` so the camera doesn't
drift between frames).

## Modeling: how to use the alpha mechanic

- Iso threshold is alpha 127 (`>= 127` = solid). Surface position along
  each edge interpolates to iso 0.5, so intermediate alphas *move* the
  surface: high alpha fattens, low slims (see IMPL.md §5–7).
- Shells around a HARD solid can only chamfer its steps — the surface
  still hugs the stepped solid boundary. For truly smooth organic
  masses, make the solid itself soft: **analytic densities**
  (`soft_ellipsoid`, `soft_cone` in make_goblin.py) compute each cell's
  alpha from the shape's implicit function and quantize it down a
  ladder (255, 192, 158, 131, then ten sub-threshold grades 104→5,
  chars '0'–'9'), ramping ~1.5 voxels either side of the surface.
  Marching cubes then reconstructs a near-smooth shape.
- For everything else, the generators run a distance-transform shell
  pass with the SAME slope (alpha ≈ 127.5 − (d − 0.5)·80) so analytic
  and shell surfaces meet consistently. The older 3-shell halo
  (64/28/12) in make_skeleton.py is the cruder ancestor of this.
- Things that must stay CRISP opt OUT of shells (`halo=False`): ribs,
  teeth, claws, fingers. One voxel of gap survives only without shells.
- **Sharp zones**: strip all sub-threshold cells in boxes around
  features (eyes, mouth, nose rims) after the shell pass — solid meets
  air directly and crease-aware shading keeps the edge hard. This is
  how a soft head gets a crisp face.
- Cavities (eye sockets, mouth) are carved AFTER the shell pass so
  shells can't fog them; dark back-wall voxels make them read black.
  1-voxel features get color-averaged into invisibility — make dark
  features 2+ voxels or use carved holes.
- **Separate models for separate things** (LANG.md §7): declare
  accessories and features (kilt, teeth, eyes) as their own `model`
  sections and `place` them — each part is materialized with its own
  marching-cubes pass, so parts can share space without their density
  fields blending and cross-part color bleed is impossible. Use this
  when a feature fights the body's smoothing; use hard materials when
  a single mesh is fine but needs crisp lines.
- **Hard materials are the paradigm for hard lines** (LANG.md §3):
  `t = F5EFD8 hard` in the palette. Hard-sourced vertices snap to the
  half-voxel grid, triangles touching a hard voxel take its exact
  color (no blending — this is what stops eye/tooth color bleed), and
  hard surfaces shade flat. Use for teeth, eyes, cloth hems, dark
  cavity walls. Generators should also build hard materials with
  `halo=False` and strip shells adjacent to hard voxels (see
  make_goblin.py). Dark liner cells remain useful when you WANT an
  outline (eyeliner, gums) rather than a raw color border.
- Sub-threshold shells carry NO connectivity: a limb "attached" only
  through shell voxels is visually detached. Solid paths only. The
  inverse also bites: solids closer than ~3 voxels visually WELD as
  their density bulges meet (the goblin's arms webbed to its ribs at a
  1-voxel gap). Give separate parts real clearance.
- Reserve the 1-cell border ring of every layer for joint markers —
  never let geometry or shells write there (soft fields reach further
  than you think).

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
uniform along a limb (elbow AND wrist), or the forearm kinks. And keep
sway consistent with pinning: if the chest sways in x while elbow and
wrist targets are world-fixed, the arms flail sideways relative to the
body — either pin the chest and put the sway in the pelvis/head, or
make the arm keys track the sway.

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
- Test analytic primitives on non-axis-aligned cases: the first
  soft_cone silently only worked for x-aligned axes (the ears) and
  painted an infinite slab for the y/z-axis nose. The fix is a proper
  orthonormal frame perpendicular to the axis.

## When extending the language

Update in lockstep: `LANG.md` (spec §s + grammar + error table) →
`render.py` (parse + validate + semantics) → `make_skeleton.py`
(emit it) → regenerate → render → LOOK. New syntax should follow the
house style: line-based, `=` declarations with the palette, slots
delimited by `---`, and semantics that never require the author to do
rotation math or per-frame arithmetic.

# I created a language for 3D design that agents can work with.

Repo: https://github.com/elliottdehn/foxel

## Try it

If you use Claude Code, two commands install it as a skill:

```
/plugin marketplace add elliottdehn/foxel
/plugin install foxel@foxel
```

After that, just ask for a voxel asset ("make me a rigged goblin with
a walk cycle") and the agent clones the toolchain and gets to work.
Not on Claude Code? Everything is plain Python: clone the repo and
point your agent at `AGENTS.md`.

## Background

Doing 3D modeling, rigging, texturing and animation with agents is
extremely frustrating and difficult right now. You're typically lead to
create assets procedurally using primitives, which has a distinctive
"look" nobody truly likes. It can be endearing for some games but
seriously hurts as a style when you're trying to do something stylish.

I've created a little language for modeling, rigging and animation that
agents can actually work with and iterate usefully on with a human in
the loop. While they're not one-shotting assets completely right now,
you can use **Foxel** to build assets iteratively and make progress over
time. This beats usual 3D development with agents which makes little
progress over iterations.

## How It Works

A model is a plain text file (`.fxl`). You write it as a stack of ASCII
layers, bottom to top. Each layer is a floor plan, each character is a
voxel, `.` is empty:

```
t = 8B4513          # trunk, brown
l = 22CC22          # leaves, green

trunk:
.....
..t..
.....
---
*trunk 2            # stamp the named layer twice
---
.lll.
lllll
.lll.
---
..l..
.lll.
..l..
```

That's a whole tree. Layers can be named and repeated, and the palette
maps characters to colors.

The trick that makes it look good instead of like Minecraft: the alpha
channel of each palette color is a **density field**, and the renderer
meshes it with marching cubes (I ported goxel's approach). A voxel with
alpha 255 is a hard cube; alpha 192 is slightly slimmer; alpha 96 never
becomes surface on its own but *pulls the surface of its neighbors
outward*. So you paint sub-threshold "halo" voxels around a shape and it
comes out rounded and organic, or you skip them and get crisp edges.
Same language, both looks: my skeleton's skull is smooth while its
ribs and teeth stay sharp, and that's just alpha values.

**Rigging** happens in the same file. Joints are declared with the
palette and placed with battleship-style border notation: one marker in
a layer's edge row gives x, one at a row's edge gives z, the layer gives
y. Bones connect joints, parent-first:

```
k = joint knee_l +z     # +z: knees prefer bending forward
a = joint ankle_l
shin_l = bone k a
```

**Animation** is the part I designed hardest around agents: it's
CSS-keyframes-shaped, and you only ever write *positions*. Never a
rotation, never an angle. You say where the hand or foot should be,
sparsely, and IK (FABRIK) fills in every joint at every in-between
frame with bone lengths preserved:

```
anim wave 1.6s loop:
0%:   wrist_r +0 +0 +0
40%:  wrist_r +11 +24 +4
100%: wrist_r +0 +0 +0
```

Keyframing a joint also *pins* it: pin the chest and arm gestures stop
bending the spine. The residual degrees of freedom that positions can't
express became tiny declarative facts instead of math: joints get bend
hints (`+z` = knees buckle forward, `+x-y` = elbows out-and-down), bones
get a facing (`hand_r = bone W F -x+z` keeps the palm oriented). An
agent asked to make a walk "more of a swagger" edits ~10 keyframe lines
(pelvis sway, chest counter-sway, head nod) and the solver turns that
into hip roll and knee flex.

The toolchain is ~1,500 lines of dependency-free Python (numpy only):

- `render.py`: parses FXL, runs marching cubes, renders stills or
  animation loops (APNG) with its own tiny software rasterizer
- `fxl2gltf.py`: exports mesh + skeleton + baked animations to `.glb`,
  which **drops straight into Godot** with a Skeleton3D and an
  AnimationPlayer containing your named animations
- `png2mp4.py`: animation previews to MP4

## Why agents can do this

The whole loop is text in, image out. The agent edits a text file,
renders a PNG, *looks at it*, and self-critiques. Every failure mode is
visible and every fix is a small diff:

- "the face looks like a mask" → step the cheek layers back in z
- "the walk is stiff" → the knees needed a bend hint, one token
- "hand is rotated 90°" → one facing declaration on the hand bone
- "hips dislocating from the spine" → solver rule, fixed once for
  every animation

Nothing is hidden in a binary blob or a GUI state. Diffs are reviewable,
the human stays in the loop at the level of *art direction* ("more
swagger", "temples narrower", "give it red eyes") instead of debugging
quaternions.

## What I built

A ~7,400-voxel skeleton with a hand-drawn skull (30 ASCII layers), red
glowing eyes, a 20-joint/19-bone rig, and three animations: idle
(breathing, knees soft, feet planted flat), a swagger walk, and a wave.
The marching-cubes mesh comes out to 14,212 triangles across 7,102
vertices, smooth-shaded with crease detection, and every one of them
traces back to a diffable text file. All authored by an agent over an
afternoon of "render, look, adjust" with me only giving art direction.
Exported to `.glb` and playing in Godot with zero manual cleanup.

## Limitations

- It's voxel art. Stylized low-poly, not sculpting.
- Agents don't one-shot it. The value is that iteration *converges*:
  each critique produces a small, targeted, reviewable change.
- Roll is implicit unless you aim a leaf joint or declare a facing.
  That's the cost of a rotations-free language, and you hit it exactly
  where you'd expect (hands).
- The renderer is a preview tool, not a product renderer. The .glb is
  the real output.

Happy to share more details if people are interested.

https://github.com/elliottdehn/foxel

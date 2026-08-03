# FXL — an ASCII layer language for colored voxel models

FXL is a plain-text format for describing colored voxel models. A model
is written as a stack of ASCII **layers**, bottom to top. Each character
in a layer is one voxel: a letter that was bound to a color in the
palette, or `.` for blank (empty space).

Suggested file extension: `.fxl`. Encoding: UTF-8; each voxel is one
Unicode code point, so the palette is effectively unlimited (see §3).

## 1. Example

```
# A small tree.

t = 8B4513          # trunk, brown
l = 22CC22          # leaves, green

trunk:
.....
..t..
.....
---

*trunk 2
---
.lll.
lllll
.lll.
---
..l..
.lll.
..l..
```

Four layers: the `trunk` slice defined once and stamped twice at the
bottom, then a wide leaf slab, then a small leaf cap on top.

## 2. File structure

A file is a sequence of lines, processed in order:

1. **Comments** — everything from an unquoted `#` to the end of the
   line is discarded. A line that becomes empty is ignored.
2. **Blank lines** — ignored everywhere. They never separate layers.
3. **Palette lines** — any line containing `=` is a declaration: a
   color binding `<char> = <color>`, a joint `<char> = joint`, or a
   bone `<name> = bone <char> <char>` (see §8).
4. **Layer definitions** — a line ending with `:` names the layer that
   follows: `<name>:` (see §6).
5. **Layer references** — a line starting with `*` stamps a previously
   defined layer, optionally repeated: `*<name> [count]` (see §6).
6. **Layer separators** — a line consisting of three or more dashes
   (`---`) ends the current layer.
7. **Grid rows** — any other line is a row of voxels appended to the
   current layer.

Palette entries must appear before the first grid row that uses them.
By convention the whole palette goes at the top of the file. A trailing
`---` after the last layer is optional.

## 3. Palette

```
<char> = <RRGGBB>
<char> = <RRGGBB><AA>
```

- `<char>` is any single Unicode code point that is not reserved and
  not whitespace — letters, digits, Greek (`λ`), box drawing (`░`),
  accented letters, and so on. Case-sensitive: `t` and `T` are
  different voxel types. Between colors, alpha grades, and joint
  markers a complex model can exceed ASCII; Unicode makes the
  character budget effectively unlimited.
- Reserved, never definable: `.` (blank), `#` (comment), `=`, `-`,
  `:`, `*`, and whitespace.
- Practical note: pick single-width glyphs. Wide characters (CJK,
  emoji) and combining marks parse as one voxel each but will look
  misaligned in most editors, defeating the point of ASCII layers.
- `<color>` is 6 or 8 hex digits (case-insensitive): red, green, blue,
  and optional alpha. Alpha defaults to `FF` (255).
- A binding may end with the word **`hard`**: `t = F5EFD8 hard`. Hard
  materials render with crisp edges: their mesh vertices snap to
  half-voxel positions (IMPL.md §6 flat mode, applied per material),
  triangles touching a hard voxel take its exact color instead of
  blending across the boundary, and their surfaces shade flat. Use it
  for teeth, eyes, cloth hems, blades — anything that should read as a
  hard line against soft surroundings. Default is soft.
- Alpha is **density**, matching goxel's model (see IMPL.md §1): 255 is
  a full voxel; intermediate values produce softer surfaces under
  marching-cubes rendering. Alpha `00` is not allowed — use `.`.
- Redefining an already-bound character is an error.
- Using a character in a grid row that was never bound is an error.

## 4. Layers and coordinates

- Layers are separated by `---` lines and stack **bottom to top**: the
  first layer in the file is the lowest slice of the model.
- Coordinates are Y-up, matching the mesh convention in IMPL.md §3:
  - **x** — column within a row, increasing to the right. First
    character is x = 0.
  - **y** — layer index, increasing upward. First layer is y = 0.
  - **z** — row within a layer, increasing down the text. First line of
    a layer is z = 0.

  So each layer reads as a bird's-eye floor plan: the top line of the
  layer text is the far edge of the model, and each following line is
  one step toward the viewer.

## 5. Grid rows

- Each character of a row is one voxel at `(x, layer_y, row_z)`.
- `.` is blank: no voxel.
- Rows within a layer, and layers within a model, may have different
  sizes (**ragged**). Missing cells are blank. The model's bounding box
  is the max row length × layer count × max row count.
- Leading/trailing spaces and tabs are stripped from a row; interior
  whitespace is an error (use `.` to hold position).
- An empty layer (two adjacent `---` separators, or `---` at the start
  of the file) is a valid all-blank slice — usable as a spacer.

## 6. Named layers and repetition

A layer can be assigned to a variable and stamped any number of times.

**Definition** — a line of the form `<name>:` names the layer slot it
opens. The rows that follow, up to the next `---`, are the layer's
body. A definition is a *template only*: it does not emit a slice by
itself.

```
trunk:
.....
..t..
.....
---
```

- `<name>` matches `[A-Za-z_][A-Za-z0-9_]*`. Names live in their own
  namespace, separate from palette characters (`t` the voxel and
  `t:` the layer name may coexist).
- Redefining a name is an error.

**Reference** — a line of the form `*<name> [count]` emits `count`
copies of the named layer (one per y-slice), default 1:

```
*trunk        # one slice
---
*trunk 4      # four identical slices
```

- A reference must be the only content of its layer slot: it cannot be
  mixed with grid rows or other references between the same pair of
  `---` separators.
- The name must be defined earlier in the file (no forward references).
- `count` is a positive decimal integer.
- References inside a definition body are not allowed: definitions
  contain grid rows only.

A referenced layer is stamped verbatim — same size, same voxels. Edits
to the template after a reference are impossible by construction, since
definitions are immutable once closed.

## 7. Models and composition

A file may declare several **models** and compose them into one asset.
Each model is **materialized separately** — its own density field, its
own marching-cubes pass — and the resulting meshes are merged. Parts
therefore never blend into each other: a kilt can hug a body, teeth
can sit in a mouth, eyes in sockets, without their densities or colors
interacting. The single-model form remains fully supported; this is an
additional tool, not a replacement.

```
model kilt:
.bbb.
bbbbb
---
.bbb.
bbbbb

place kilt +0 +15 +0
place kilt +0 +25 +0     # placements are instances
```

- `model <name>:` starts a model section; every slot after it belongs
  to that model until the next `model` header. Root (unnamed) layers
  must appear before the first model header. Model names share the
  layer-definition namespace rules but are their own namespace.
- Layers inside a model stack from that model's local y = 0.
- `place <name> <dx> <dy> <dz>` materializes an instance at a voxel
  offset (non-negative integers). A model may be placed any number of
  times; a model that is never placed is simply unused.
- Layer definitions (`name:` / `*name`) are file-global and may be
  referenced from any model. The palette, rig declarations, and
  animations are file-global as well.
- Joint markers may appear inside a model's layers; the joint's
  position is the marker position plus the placement offset. A model
  containing joint markers must be placed exactly once.
- Skinning and animation apply to the merged result: parts bind to
  bones through the union of all placed solids, so an accessory
  follows the body it sits on.

## 8. Joints and bones (animation rig)

A model may declare an animation rig alongside the palette: named
**joints** (points in the voxel grid) connected by **bones** (two
joints each).

Declarations live with the palette and reuse its `=` syntax:

```
k = joint knee_l +z # 'k' is a joint marker character; the optional
a = joint ankle_l   # name can stand in for it in animations; the
shin_l = bone k a   # optional bend hint (+z) is used by IK (see 9)
hand_r = bone W F +z    # optional facing: this bone twists about its
```                     # own axis to keep its rest +z face forward

- Joint characters share the palette namespace: a character is either a
  color or a joint marker, never both. The same reserved characters
  apply.
- Bone names are identifiers (`[A-Za-z_][A-Za-z0-9_]*`) in their own
  namespace, separate from layer names. A bone's two joints must be
  distinct and declared before the bone.
- Bone declarations are ordered **parent first**: the rig is a tree,
  every joint has at most one parent bone, and exactly one joint (the
  **root**) has none.

**Marking a joint** uses sudoku-style border notation. The marker
character appears exactly twice, in exactly one layer of the file:

- once in the layer's **first or last row** — its column gives the
  joint's x;
- once as the **first or last character of a row** — its row gives the
  joint's z.

The joint sits at the intersection `(x, z)` of that layer, at that
layer's y:

```
.....k.................    <- column marker: x = 5
.......................
k......................    <- row marker: z = 2
.......................
```

Markers are annotations, not voxels: they must sit on cells that would
otherwise be blank, and a corner cell (border row AND border column) is
invalid because it is ambiguous.

**Semantics.** The rig adds a map of joints to voxel-center positions,
`joint -> (x + 0.5, y + 0.5, z + 0.5)`, and a list of named bones as
joint pairs. It does not affect the voxel data; how a consumer animates
the model (e.g. skinning voxels to the nearest bone) is out of scope
for the format.

## 9. Animations

Animations are keyframed **positions**, never rotations. This is a
deliberate choice for authors — human or LLM — who are good at saying
*where* a hand or foot should be and bad at computing elbow angles:
you keyframe end-effector targets in voxel units, targets interpolate
between keyframes, and inverse kinematics (IK) fills in every interior
joint at every frame, keeping all bone lengths intact. The block shape
mirrors CSS `@keyframes` on purpose.

An animation is its own slot (like a layer), started by a header line
and ended by `---`:

```
anim wave 1.6s loop:
0%:   chest   +0 +0 +0
0%:   wrist_r +0 +0 +0
40%:  wrist_r +11 +24 +4
70%:  wrist_r +11 +24 +4  ease-out
100%: wrist_r +0 +0 +0
```

**Header** — `anim <name> <seconds>s [loop]:`. With `loop`, time wraps
(frame at 100% ≡ 0%); without, the last keyframe holds.

**Keyframes** — `<percent>%: <joint> <dx> <dy> <dz> [easing]`, one per
line, in any order. The joint is a marker character or its declared
name. The deltas are voxel offsets **from the joint's rest position**
(the position marked in the layers). Easing applies to the segment
arriving at that keyframe: `ease` (default, smoothstep), `linear`,
`ease-in`, `ease-out`.

**Semantics.** At any time `t`, each keyframed joint has a target =
rest + interpolated delta. Then:

1. If the **root** is keyframed, the whole model translates by its
   delta first.
2. Each other keyframed joint is an IK **end effector**, solved in
   order of first appearance in the block. Its chain runs from the
   nearest ancestor that is the root or an already-solved effector —
   so *keyframing a joint pins it*, and chains through it stop there
   (pin `chest` at `+0 +0 +0` and arm chains will not bend the spine).
   The **first bone of a chain is rigid**: the socket joint rides its
   base's body (a pelvis→hip or chest→shoulder bone never hinges), and
   IK bends only from the socket outward. The rest of the chain is
   solved with FABRIK, preserving rest bone lengths; a target out of
   reach straightens the chain toward it. A joint's declared **bend
   hint** decides which way a straight chain buckles when it must
   shorten — without one, a chain collinear with its target may not
   bend at all. A hint is one or more signed axes summed into a
   direction and normalized: `+z` (knee bends forward), `+x-y` (elbow
   points outward and down).
3. Joints not on any chain follow their parent rigidly: they rotate
   with the bone that leads into their subtree.

A position target cannot control a bone's **roll** about its own
axis. Two tools cover it: aiming a leaf joint (keyframe a fingertip to
point the hand) fixes the bone's direction, and a bone's declared
**facing** (`hand_r = bone W F +z`) fixes the twist -- the bone rolls
so its rest-space facing direction keeps pointing that way in world
space (a palm keeps facing forward through an arm raise).

**Skinning** defaults to `rigid`: voxels bind to the nearest bone
(geodesically, through the body) and move rigidly with it — right for
articulated things like skeletons, but bent joints show seams. A file
may declare `skin elastic` (a bare line alongside the palette): each
vertex then blends the two geodesically-nearest bones, so joints
stretch smoothly like game-engine flesh. A renderer that cannot
animate may ignore `anim` slots and skin declarations entirely; they
add no voxels.

## 10. Semantics

An FXL file denotes a sparse map from integer coordinates to RGBA:

```
voxels : (x, y, z) -> (r, g, b, a)       # only for non-blank cells
```

That is exactly the voxel model consumed by the meshing pipeline in
IMPL.md: RGB is the voxel color, alpha is the density field. Named
layers are expanded at parse time — references are indistinguishable
from writing the layer out by hand, and the names do not survive into
the model. There is no other state: no transforms or macros. One file,
one model, origin at the first character of the first line of the
bottom layer.

## 11. Grammar (EBNF)

Applied after comment stripping and blank-line removal:

```ebnf
file      = { palette | jointdecl | bonedecl } ,
            [ slot , { "---" , slot } , [ "---" ] ] ;
palette   = char , "=" , color , [ "hard" ] ;
jointdecl = char , "=" , "joint" , [ name ] , [ bend ] ;
bonedecl  = name , "=" , "bone" , char , char , [ bend ] ;
animslot  = animhead , { keyframe } ;      (* a slot form, like def *)
animhead  = "anim" , name , number , "s" , [ "loop" ] , ":" ;
keyframe  = number , "%" , ":" , jointref ,
            delta , delta , delta , [ easing ] ;
jointref  = char | name ;
delta     = [ "+" | "-" ] , number ;
bend      = ( "+" | "-" ) , axis ,
            { ( "+" | "-" ) , axis } ;
axis      = "x" | "y" | "z" ;
easing    = "linear" | "ease" | "ease-in" | "ease-out" ;
slot      = def | ref | layer | animslot ;
modelhead = "model" , name , ":" ;
placedecl = "place" , name , delta , delta , delta ;
def       = name , ":" , { row } ;        (* template: emits nothing *)
layer     = { row } ;                     (* possibly empty *)
ref       = "*" , name , [ count ] ;
name      = ( letter | "_" ) , { letter | digit | "_" } ;
count     = digit , { digit } ;           (* >= 1 *)
char      = ? any single code point except
            reserved and whitespace ? ;
color     = 6 * hex | 8 * hex ;
row       = cell , { cell } ;
cell      = char | "." ;
```

A definition is simply a slot whose first line is `<name>:` — it is
delimited by `---` exactly like any other slot, but emits no slice.
Definitions may appear anywhere in the slot sequence, as long as each
name is defined before its first reference.

## 12. Errors

A conforming reader rejects the file (with line number) on:

| Error | Example |
|---|---|
| unbound voxel character | `x` in a grid with no `x = ...` |
| duplicate palette binding | two `t = ...` lines |
| reserved character bound | `. = FF0000` |
| malformed color | `t = FF00`, `t = GGHHII` |
| interior whitespace in a row | `.t .t.` |
| alpha of zero | `t = FF000000` |
| reference to an undefined name | `*trunk` before `trunk:` |
| duplicate layer name | two `trunk:` definitions |
| reference mixed with grid rows in one slot | `*trunk` followed by `.t.` |
| reference inside a definition body | `trunk:` then `*base` |
| non-positive repeat count | `*trunk 0` |
| character bound as both color and joint | `k = FF0000` and `k = joint` |
| bone with undeclared or duplicate joints | `x = bone k k` |
| duplicate bone name | two `shin_l = bone ...` lines |
| joint marked in more than one layer | markers in two layers |
| wrong marker count (exactly 2 required) | one or three `k` marks |
| marker not on a border, or on a corner cell | `k` in mid-grid |
| declared joint never marked | `k = joint` with no marks |
| joint with two parent bones, or no single root | cyclic/forest rig |
| duplicate animation name | two `anim walk ...` blocks |
| keyframe outside an anim slot | `50%: ...` after `---` |
| keyframe for an unknown joint | `0%: wing_l +0 +0 +0` |
| malformed keyframe or percent > 100 | `120%: ...` |
| anim slot mixed with grid rows | rows after `anim ...:` |
| place of an undefined model | `place hat ...` with no `model hat:` |
| duplicate model name | two `model kilt:` headers |
| negative place offset | `place kilt -1 +0 +0` |
| jointed model placed zero or multiple times | markers need one placement |

# Goxel Marching Cubes — Implementation Notes

A replication-grade description of how goxel turns a voxel volume into a
marching-cubes triangle mesh. Source of truth:

- `goxel/src/marchingcube.c` — the whole algorithm (~360 lines + tables)
- `goxel/src/block_def.h` — cube vertex/edge numbering conventions
- `goxel/src/volume_to_vertices.c` — dispatch + mesh-export consumer
- `goxel/src/render.c` — GPU consumer (per-tile caching, position scaling)

## 1. Data model

- A volume is a sparse set of **16³ tiles/blocks** (`BLOCK_SIZE == 16`,
  defined in `goxel.h:433`). Each voxel is RGBA (`uint8_t[4]`).
- **The alpha channel is the density field.** RGB is only the color.
  There is no signed distance field: alpha is 0 (empty) to 255 (full),
  and painting tools with "smoothness" produce intermediate alphas.
- Density samples live at **voxel centers**. A marching-cubes cell spans
  the 8 centers of a 2×2×2 voxel group, so the mesh is offset half a
  voxel from the voxel grid (see §6).

## 2. Pipeline

```
volume_generate_vertices(volume, block_pos, effects, out, &size, &subdivide)
    └─ if (effects & EFFECT_MARCHING_CUBES)
           volume_generate_vertices_mc(...)   // marchingcube.c
```

Called once per 16³ tile. Two flags matter (`render.h`):

- `EFFECT_MARCHING_CUBES` (1<<7) — use MC instead of cube/quad meshing.
- `EFFECT_MC_SMOOTH` (1<<9) — smooth mode. **Default (flag absent) is
  "flat" mode**, which snaps vertices and re-triangulates (see §8).

Outputs:
- return value = number of **triangles**
- `*size = 3` (triangles; the cube mesher returns 4 = quads)
- `*subdivide = MC_VOXEL_SUB_POS = 8` — vertex positions are written in
  1/8-voxel integer-ish units because the output `pos` is `uint8_t[3]`;
  consumers divide by `subdivide` to get voxel units.

Callers must provide an `out` buffer big enough for the worst case;
goxel allocates `16*16*16*6*4` vertices (`render.c:408`,
`volume_to_vertices.c:433`).

Per-tile flow (`volume_generate_vertices_mc`, `marchingcube.c:251`):

1. `volume_read` a padded **(N+2)³ RGBA snapshot** of the tile: voxels
   `[-1, N]` in each axis (1-voxel apron from neighboring tiles).
2. Compute the bounding rect of non-zero-alpha voxels (±2 margin),
   clamped to `[0, N)` — pure speed optimization, skip empty space.
3. For each cell `(x, y, z)` in that rect: gather 8 corner alphas, run
   the MC core (§5), assign colors (§7), (flat mode: merge/re-split,
   §8), compute per-triangle normals, emit vertices (§9).

## 3. Cube conventions (`block_def.h`)

Y is up. Vertex numbering (this is NOT Bourke's z-up numbering, but the
edge/tri tables are consistent with it):

```
          v4 +----------e4---------+ v5
            /.                    /|
           / .                   / |
         e7  .                 e5  |
         /   .                 /   |
        /    .                /    |
    v7 +----------e6---------+ v6  |
       |     .               |     e9
       |     e8              |     |
       |     .               |     |
       |  v0 . . . .e0 . . . | . . + v1
      e11   .                |    /
       |   .                e10  /
       |  e3                 |  e1
       | .                   | /
    v3 +---------e2----------+ v2
```

```c
// vertex index -> offset within the cell
static const int VERTICES_POSITIONS[8][3] = {
    {0,0,0}, {1,0,0}, {1,0,1}, {0,0,1},
    {0,1,0}, {1,1,0}, {1,1,1}, {0,1,1},
};
// edge index -> its two vertex indices
static const int EDGES_VERTICES[12][2] = {
    {0,1}, {1,2}, {2,3}, {3,0},
    {4,5}, {5,6}, {6,7}, {7,4},
    {0,4}, {1,5}, {2,6}, {3,7},
};
```

## 4. The lookup tables

`MC_EDGE_TABLE[256]` (12-bit mask of crossed edges per cube
configuration) and `MC_TRI_TABLE[256][16]` (edge-index triangle strips,
-1 terminated, ≤5 triangles per cell). These are the classic Paul
Bourke / Lorensen–Cline tables, verbatim — copy them from
`goxel/src/marchingcube.c:366` and `:401`. Winding in the tables plus
the vertex numbering above yields outward-facing triangles (normal
computed as `(v1-v0)×(v2-v0)` points out of the surface).

## 5. MC core (`mc_compute`, `marchingcube.c:43`)

Input: 8 corner densities as ints 0–255. Output: up to 5 triangles,
each vertex described as `(edge, v0, v1, mu)`.

```c
cube_index = 0;
for (i = 0; i < 8; i++)
    if (density[i] >= 127) cube_index |= 1 << i;   // "inside" test
edges = MC_EDGE_TABLE[cube_index];
if (!edges) return 0;                              // fully in/out

// For each crossed edge, interpolation factor toward v1:
f0 = density[v0] / 255.;
f1 = density[v1] / 255.;
mu = (f0 - 0.5) / (f0 - f1);      // iso-level is 0.5
```

Notes for replication:
- The inside test uses `>= 127` while interpolation targets iso 0.5
  (= 127.5/255). This tiny asymmetry is in the original; it means `mu`
  can slightly exceed [0,1] when a corner is exactly 127.
- `f0 - f1` can't be 0 on a crossed edge (corners are on opposite sides
  of the threshold), so the division is safe.
- Triangles are assembled by indexing the per-edge vertex array with
  `MC_TRI_TABLE[cube_index]` in groups of 3.

## 6. Positions and the sub-voxel integer grid

Vertex positions must fit `uint8_t`, so everything is expressed in
**1/8-voxel units** (`MC_VOXEL_SUB_POS == 8`, `marchingcube.c:24`).

Within a cell, `mc_interp_pos` (`marchingcube.c:74`) lerps the two
corner offsets and scales:

```c
p = lerp(VERTICES_POSITIONS[v0], VERTICES_POSITIONS[v1], mu);  // in [0,1]
// smooth mode:
pos = p * 8;
// flat mode: snap to half-voxel increments (0, 0.5, 1 -> 0, 4, 8)
pos = round(p * 8 / 4) * 4;
```

Final emitted position (`marchingcube.c:347`):

```c
out.pos[axis] = cell_pos + cell_index * 8 + 4 + 0.5;
```

- `+ 4` (= SUB/2) shifts by half a voxel: densities live at voxel
  centers, so cell corner (0,0,0) of cell x is world position x + 0.5.
- `+ 0.5` rounds on the implicit float→uint8 truncation.
- Consumers divide by `subdivide` (8): the GL shader gets
  `u_pos_scale = 1/subdivide` (`render.c:453`) and the model matrix is
  translated by the tile position; the mesh exporter computes
  `pos/subdivide + tile_pos` (`volume_to_vertices.c:329`).

Max value: 15*8 + 8 + 4 + 0.5 = 132.5 — fits uint8.

## 7. Color assignment (`marchingcube.c:324-338`)

Each MC vertex sits on an edge between two voxels. Its color is the RGBA
of **whichever endpoint voxel has the higher alpha** (i.e. the "solid"
side) — no color interpolation:

```c
color = (alpha(v0_voxel) > alpha(v1_voxel)) ? color(v0_voxel) : color(v1_voxel);
```

Alpha of the emitted vertex is forced to 255. Color equality elsewhere
in the code compares **RGB only** (`color_eq`, memcmp of 3 bytes).

## 8. Flat mode: polygon merge + color-aware re-split

This is goxel's distinctive addition. Without `EFFECT_MC_SMOOTH`, after
snapping positions to the half-voxel grid, coplanar MC triangles in a
cell are merged into polygons and re-cut so that (a) shading is flat and
(b) two-color cells get a straight color border. Entry:
`split_triangles` (`marchingcube.c:237`), applied per cell.

**Step 1 — greedy polygon build** (`get_poly` / `poly_attach_triangle`):
consume the cell's triangles in table order; attach a triangle to the
growing polygon iff its normal matches the polygon's (dot ≈ 1 within
0.01) and it shares a directed edge (matched by MC **edge indices**,
not positions): triangle edge `(tri[(j+2)%3], tri[(j+1)%3])` against
polygon edge `(poly[i], poly[i+1])`. On match, insert the third vertex
after position i. Stop at the first triangle that doesn't attach; it
starts the next polygon.

**Step 2 — recursive split** (`split_poly`, `marchingcube.c:168`), with
the polygon centroid computed once and threaded through recursion:

1. *Ear-clip uniform corners*: if vertex i and both its neighbors have
   equal color, emit ear `(poly[i], poly[i+1], poly[i-1])` as one
   triangle, drop vertex i, recurse on the rest.
2. *Two-color quad*: if adjacent vertices i, i+1 share a color (and
   nb < 6), insert midpoints on the two edges flanking the pair, emit
   the pair's side as two triangles, and recurse on the shrunk polygon
   with the midpoints re-colored to the far side. This produces the
   straight border between two colors.
3. *Fallback fan*: emit 2 triangles per vertex fanning around the
   centroid, each half-edge split at its midpoint, so every original
   vertex keeps its own color region.

Smooth mode skips all of this: raw interpolated MC triangles are used
directly.

## 9. Normals and output vertex format

Normals are always **per-triangle face normals** (no gradient/smoothed
normals): `normalize((v1-v0)×(v2-v0))`, quantized to `int8` by `* 64`
(`marchingcube.c:350`). Consumers renormalize after load. Smooth vs
flat differs only in geometry, not in normal computation.

Output struct (`volume_utils.h:62`), fields the MC path fills:

```c
typedef struct voxel_vertex {
    uint8_t  pos[3];      // sub-voxel units, see §6
    int8_t   normal[3];   // face normal * 64
    uint8_t  color[4];    // voxel color, alpha forced to 255
    // tangent/gradient/uv/occlusion_uv/bump_uv: zeroed for MC
} voxel_vertex_t;
```

## 10. Tiling, caching, export

- Because each tile reads a 1-voxel apron, the surface at a tile border
  is generated by the tile that owns the cell; iteration must include
  **empty tiles adjacent to filled ones**
  (`VOLUME_ITER_TILES | VOLUME_ITER_INCLUDES_NEIGHBORS`,
  `volume_to_vertices.c:434`), or border geometry is dropped.
- The renderer caches per-tile vertex buffers keyed by the content
  hashes of the tile **and its 26 neighbors** plus the effect bits
  (`get_item_for_tile`, `render.c:375`) — any neighbor edit correctly
  invalidates the mesh.
- For export, `volume_generate_mesh` concatenates all tiles' triangles
  (indices are trivial 0..n for size==3), then meshoptimizer welds
  duplicate vertices and optionally simplifies
  (`optimize_mesh`, `volume_to_vertices.c:371`).

## 11. Replication checklist

1. 16³ tiles, RGBA voxels, alpha = density, samples at voxel centers.
2. Standard Bourke edge/tri tables + goxel's y-up vertex numbering.
3. Inside test `alpha >= 127`, interpolation at iso 0.5.
4. Positions in 1/8-voxel integer units, +half-voxel offset, uint8.
5. Color from the higher-alpha edge endpoint; no blending.
6. Flat mode (default): snap to half-voxel grid, merge coplanar
   triangles per cell, color-aware re-split (§8).
7. Per-face normals, int8 ×64.
8. 1-voxel apron reads; process empty tiles next to filled ones.

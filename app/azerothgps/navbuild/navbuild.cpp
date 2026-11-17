// navbuild: Recast over a triangle soup, for AzerothGPS's dev tools (app/azerothgps/recastmesh.py). Not shipped.
// In (binary, little-endian): "AGNI", float cs, ch, agentHeight, agentRadius, agentClimb, maxEdgeLen,
//   float bmin[3], bmax[3], uint32 nverts, uint32 ntris, float verts[nverts*3], int32 tris[ntris*3],
//   uint8 areas[ntris] (63 walkable, 0 solid: the caller decides by slope, as the collision faces' winding can't be trusted).
// Out: "AGNO", uint32 nverts, npolys, nvp, float verts[nverts*3] (world, Recast's axes),
//   then per poly: uint16 verts[nvp], uint16 neis[nvp] (0xffff none), uint8 area.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <vector>
#include "Recast.h"

static bool readAll(FILE* f, void* p, size_t n) { return fread(p, 1, n, f) == n; }

int main(int argc, char** argv) {
  if (argc != 3) { fprintf(stderr, "usage: navbuild in.bin out.bin\n"); return 2; }
  FILE* f = fopen(argv[1], "rb");
  if (!f) { fprintf(stderr, "can't read %s\n", argv[1]); return 1; }
  char magic[4];
  float cs, ch, ah, ar, ac, mel, bmin[3], bmax[3];
  unsigned nv, nt;
  if (!readAll(f, magic, 4) || memcmp(magic, "AGNI", 4) || !readAll(f, &cs, 4) || !readAll(f, &ch, 4) ||
      !readAll(f, &ah, 4) || !readAll(f, &ar, 4) || !readAll(f, &ac, 4) || !readAll(f, &mel, 4) ||
      !readAll(f, bmin, 12) || !readAll(f, bmax, 12) || !readAll(f, &nv, 4) || !readAll(f, &nt, 4)) {
    fprintf(stderr, "bad header\n"); return 1;
  }
  std::vector<float> verts(nv * 3);
  std::vector<int> tris(nt * 3);
  std::vector<unsigned char> areas(nt);
  if (!readAll(f, verts.data(), verts.size() * 4) || !readAll(f, tris.data(), tris.size() * 4) ||
      !readAll(f, areas.data(), areas.size())) { fprintf(stderr, "short input\n"); return 1; }
  fclose(f);

  rcContext ctx(false);
  // (tiled: a city is over a single mesh's 65535 vertices; each tile with a border, its edges on the tile's sides portals)
  const float tileYd = 128.0f;
  const int ts = (int)(tileYd / cs);
  const int walkRadius = (int)ceilf(ar / cs);
  const int border = walkRadius + 3;
  int gw, gh;
  rcCalcGridSize(bmin, bmax, cs, &gw, &gh);
  const int tw = (gw + ts - 1) / ts, th = (gh + ts - 1) / ts;
  // each triangle's box (x, z)
  std::vector<float> tb(nt * 4);
  for (unsigned i = 0; i < nt; ++i) {
    float x0 = 1e30f, x1 = -1e30f, z0 = 1e30f, z1 = -1e30f;
    for (int k = 0; k < 3; ++k) {
      const float* v = &verts[tris[i * 3 + k] * 3];
      x0 = fminf(x0, v[0]); x1 = fmaxf(x1, v[0]); z0 = fminf(z0, v[2]); z1 = fmaxf(z1, v[2]);
    }
    tb[i * 4] = x0; tb[i * 4 + 1] = x1; tb[i * 4 + 2] = z0; tb[i * 4 + 3] = z1;
  }
  FILE* o = fopen(argv[2], "wb");
  if (!o) return 1;
  fwrite("AGNT", 1, 4, o);
  long countPos = ftell(o);
  unsigned ntiles = 0;
  fwrite(&ntiles, 4, 1, o);
  std::vector<int> ttris;
  std::vector<unsigned char> tareas;
  for (int ty = 0; ty < th; ++ty) for (int tx = 0; tx < tw; ++tx) {
    rcConfig cfg;
    memset(&cfg, 0, sizeof(cfg));
    cfg.cs = cs; cfg.ch = ch;
    cfg.walkableSlopeAngle = 89.0f;
    cfg.walkableHeight = (int)ceilf(ah / ch);
    cfg.walkableClimb = (int)floorf(ac / ch);
    cfg.walkableRadius = walkRadius;
    cfg.maxEdgeLen = (int)(mel / cs);
    cfg.maxSimplificationError = 1.1f;
    cfg.minRegionArea = 8 * 8;
    cfg.mergeRegionArea = 20 * 20;
    cfg.maxVertsPerPoly = 6;
    cfg.tileSize = ts;
    cfg.borderSize = border;
    cfg.width = ts + border * 2;
    cfg.height = ts + border * 2;
    cfg.bmin[0] = bmin[0] + tx * ts * cs - border * cs;
    cfg.bmin[1] = bmin[1];
    cfg.bmin[2] = bmin[2] + ty * ts * cs - border * cs;
    cfg.bmax[0] = bmin[0] + (tx + 1) * ts * cs + border * cs;
    cfg.bmax[1] = bmax[1];
    cfg.bmax[2] = bmin[2] + (ty + 1) * ts * cs + border * cs;
    ttris.clear(); tareas.clear();
    for (unsigned i = 0; i < nt; ++i) {
      if (tb[i * 4 + 1] < cfg.bmin[0] || tb[i * 4] > cfg.bmax[0] || tb[i * 4 + 3] < cfg.bmin[2] || tb[i * 4 + 2] > cfg.bmax[2]) continue;
      ttris.push_back(tris[i * 3]); ttris.push_back(tris[i * 3 + 1]); ttris.push_back(tris[i * 3 + 2]);
      tareas.push_back(areas[i]);
    }
    if (tareas.empty()) continue;
    rcHeightfield* hf = rcAllocHeightfield();
    if (!rcCreateHeightfield(&ctx, *hf, cfg.width, cfg.height, cfg.bmin, cfg.bmax, cfg.cs, cfg.ch)) return 3;
    if (!rcRasterizeTriangles(&ctx, verts.data(), (int)nv, ttris.data(), tareas.data(), (int)tareas.size(), *hf,
                              cfg.walkableClimb)) return 3;
    rcFilterLowHangingWalkableObstacles(&ctx, cfg.walkableClimb, *hf);
    rcFilterLedgeSpans(&ctx, cfg.walkableHeight, cfg.walkableClimb, *hf);
    rcFilterWalkableLowHeightSpans(&ctx, cfg.walkableHeight, *hf);
    rcCompactHeightfield* chf = rcAllocCompactHeightfield();
    if (!rcBuildCompactHeightfield(&ctx, cfg.walkableHeight, cfg.walkableClimb, *hf, *chf)) return 4;
    rcFreeHeightField(hf);
    if (!rcErodeWalkableArea(&ctx, cfg.walkableRadius, *chf)) return 4;
    if (!rcBuildDistanceField(&ctx, *chf)) return 5;
    if (!rcBuildRegions(&ctx, *chf, cfg.borderSize, cfg.minRegionArea, cfg.mergeRegionArea)) return 5;
    rcContourSet* cset = rcAllocContourSet();
    if (!rcBuildContours(&ctx, *chf, cfg.maxSimplificationError, cfg.maxEdgeLen, *cset)) return 6;
    rcPolyMesh* pm = rcAllocPolyMesh();
    if (!rcBuildPolyMesh(&ctx, *cset, cfg.maxVertsPerPoly, *pm)) { fprintf(stderr, "tile %d,%d: polymesh failed\n", tx, ty); return 7; }
    rcFreeCompactHeightfield(chf);
    rcFreeContourSet(cset);
    if (pm->npolys > 0) {
      ++ntiles;
      int ixy[2] = {tx, ty};
      fwrite(ixy, 4, 2, o);
      unsigned onv = pm->nverts, onp = pm->npolys, onvp = pm->nvp;
      fwrite(&onv, 4, 1, o); fwrite(&onp, 4, 1, o); fwrite(&onvp, 4, 1, o);
      for (int i = 0; i < pm->nverts; ++i) {
        const unsigned short* v = &pm->verts[i * 3];
        float w[3] = {pm->bmin[0] + v[0] * pm->cs, pm->bmin[1] + (v[1] + 1) * pm->ch, pm->bmin[2] + v[2] * pm->cs};
        fwrite(w, 4, 3, o);
      }
      for (int i = 0; i < pm->npolys; ++i) {
        fwrite(&pm->polys[i * pm->nvp * 2], 2, pm->nvp * 2, o);
        fwrite(&pm->areas[i], 1, 1, o);
      }
    }
    rcFreePolyMesh(pm);
  }
  fseek(o, countPos, SEEK_SET);
  fwrite(&ntiles, 4, 1, o);
  fclose(o);
  fprintf(stderr, "%d x %d tiles, %u with polys\n", tw, th, ntiles);
  return 0;
}

"""Roof level map: robust height raster -> level blocks (height-continuity components) -> polygons, planes, shared borders.
Usage: python -I levels.py <S>   (reads data/real_fp.npz, data/fp.pkl; writes data/levels.json)"""
import sys, json, pickle, numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree
from shapely import affinity, contains_xy
from shapely.geometry import box, Point, LineString
from shapely.ops import unary_union, snap
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
S = sys.argv[1]; sys.path.insert(0, S + "/scripts")
from planes import ransac_local, fit_ls, plane_z, plane_props
FT = 0.3048; CELL = 0.25; STEP = float(sys.argv[2]) if len(sys.argv) > 2 else 0.12; RAD = float(sys.argv[3]) if len(sys.argv) > 3 else 0.30
d = np.load(S + "/data/real_fp.npz"); fp = pickle.load(open(S + "/data/fp.pkl", "rb"))
ox, oy = fp.bounds[0], fp.bounds[1]
x, y, z, c, hag = d["x"] - ox, d["y"] - oy, d["z"], d["c"], d["hag"]
fpl = affinity.translate(fp, -ox, -oy)
nonground = c != 2
# ---------- 1. robust raster
minx, miny, maxx, maxy = fpl.bounds
nx, ny = int(np.ceil((maxx - minx) / CELL)), int(np.ceil((maxy - miny) / CELL))
xs = minx + (np.arange(nx) + .5) * CELL; ys = miny + (np.arange(ny) + .5) * CELL
GX, GY = np.meshgrid(xs, ys)
inside = contains_xy(fpl, GX, GY)
sel = nonground & contains_xy(fpl.buffer(1.0), x, y) & (hag > 1.5)
Pp = np.c_[x[sel], y[sel], z[sel]]
tree = cKDTree(Pp[:, :2])
val = np.full(GX.shape, np.nan); spread = np.full(GX.shape, np.nan); cnt = np.zeros(GX.shape, int)
jj, ii = np.nonzero(inside)
nbrs = tree.query_ball_point(np.c_[GX[jj, ii], GY[jj, ii]], RAD)
for j, i, nb in zip(jj, ii, nbrs):
    if len(nb) < 3: continue
    zz = np.sort(Pp[nb, 2]); k = max(2, int(0.5 * len(zz)))
    val[j, i] = np.median(zz[:k]); spread[j, i] = zz[-1] - zz[0]; cnt[j, i] = len(nb)
ok = np.isfinite(val)
print("cells inside", inside.sum(), "with data", ok.sum(), "spread>0.5 dropped", (ok & (spread > 0.5)).sum())
good = ok & (spread <= 0.5)
# ---------- 2. blocks = connected components of cells with the same surface class and continuous height
# surface class from the local gradient of a 5x5-smoothed height raster: flat (<4 deg), sloped (by 45-degree aspect sector), edge (>35 deg, dropped)
vf = val.copy(); nn = ndimage.distance_transform_edt(~np.isfinite(vf), return_indices=True)
vf = vf[tuple(nn[1])]
F = ndimage.uniform_filter(vf, 5, mode="nearest")
gx = np.zeros_like(F); gy = np.zeros_like(F)
gx[:, 2:-2] = (F[:, 4:] - F[:, :-4]) / (4 * CELL); gy[2:-2, :] = (F[4:, :] - F[:-4, :]) / (4 * CELL)
cell_tilt = np.degrees(np.arctan(np.hypot(gx, gy))); cell_asp = np.degrees(np.arctan2(-gx, -gy)) % 360
key = np.full(GX.shape, -9)
flatc = cell_tilt < 4.0; slopec = (cell_tilt >= 4.0) & (cell_tilt <= 35)
key[flatc] = -1
key[slopec] = (np.round(cell_asp[slopec] / 45.0).astype(int) % 8)
lab = np.full(GX.shape, -1); nid = 0
seen = np.zeros(GX.shape, bool)
for j0, i0 in np.argwhere(good & (key > -9)):
    if seen[j0, i0]: continue
    k0 = key[j0, i0]; stack = [(j0, i0)]; seen[j0, i0] = True; cells = []
    while stack:
        j, i = stack.pop(); cells.append((j, i))
        for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            jn, in_ = j + dj, i + di
            if 0 <= jn < ny and 0 <= in_ < nx and good[jn, in_] and not seen[jn, in_] and key[jn, in_] == k0 and abs(val[jn, in_] - val[j, i]) < STEP:
                seen[jn, in_] = True; stack.append((jn, in_))
    if len(cells) * CELL**2 >= 3.0:
        for j, i in cells: lab[j, i] = nid
        nid += 1
# close small holes / assign remaining cells inside the footprint to nearest block within 1 m (fills tree-dropped cells)
fillable = inside & (lab < 0)
dist, (fj, fi) = ndimage.distance_transform_edt(lab < 0, return_indices=True)
flab = lab.copy(); m = fillable & (dist * CELL <= 1.0); flab[m] = lab[fj[m], fi[m]]
# histogram of levels (for the report)
h, e = np.histogram(val[good], bins=np.arange(np.nanmin(val[good]), np.nanmax(val[good]) + 0.3, 0.3))
# ---------- 3. polygons + planes
blocks = []
for b in range(nid):
    mk = flab == b
    js, is_ = np.nonzero(mk)
    poly = unary_union([box(minx + i * CELL, miny + j * CELL, minx + (i + 1) * CELL, miny + (j + 1) * CELL) for j, i in zip(js, is_)])
    poly = poly.buffer(0.2).buffer(-0.2).intersection(fpl)   # smooth jaggies
    poly = poly.simplify(0.3)
    poly = snap(poly, fpl, 0.5)
    if poly.is_empty: continue
    core = (lab == b)
    pts = np.c_[GX[core], GY[core], val[core]]
    # robust plane with high-spread cells already removed; iterate trimming
    pl = fit_ls(pts)
    for _ in range(4):
        r = np.abs(pts[:, 2] - plane_z(pl, pts[:, 0], pts[:, 1])); k = r < max(0.08, 2 * np.median(r))
        if k.sum() > 10: pl = fit_ls(pts[k])
    r = np.abs(pts[:, 2] - plane_z(pl, pts[:, 0], pts[:, 1]))
    tilt, pitch, asp = plane_props(pl)
    subs = []
    if np.sqrt(np.mean(r**2)) > 0.07 and len(pts) > 200:
        sp = ransac_local(pts, thr=0.07, min_pts=40)
        for q in sp:
            rr = np.abs(pts[:, 2] - plane_z(q, pts[:, 0], pts[:, 1])) < 0.07
            t_, p_, a_ = plane_props(q); subs.append(dict(tilt=t_, pitch=p_, aspect=a_, frac=float(rr.mean())))
    blocks.append(dict(id=b, poly=poly, area_ft2=poly.area / FT**2, zmean=float(np.mean(pts[:, 2])), zmin=float(pts[:, 2].min()), zp95=float(np.percentile(pts[:, 2], 95)),
                       hag_mean=float(np.mean(hag[sel][np.isin(np.arange(sel.sum()), np.arange(sel.sum()))]) ) if False else None,
                       tilt=tilt, pitch=pitch, aspect=None if tilt < 2 else asp, flat=bool(tilt < 2), rms=float(np.sqrt(np.mean(r**2))), ncells=int(core.sum()), planes=subs))
for b in blocks:
    b["id"] = int(b["id"])
# ---------- 4. borders
byid = {b["id"]: b for b in blocks}
shared = []
ids = sorted(byid)
for a_ in range(len(ids)):
    for b_ in range(a_ + 1, len(ids)):
        A, B = byid[ids[a_]], byid[ids[b_]]
        ln = A["poly"].boundary.intersection(B["poly"].buffer(0.4))
        if ln.is_empty or ln.length < 1.0: continue
        la = (labcell := None)
        # height step: median value of A-cells and B-cells within 1 m of the shared line
        zone = ln.buffer(1.0)
        ma = (lab == A["id"]) & contains_xy(zone, GX, GY); mb = (lab == B["id"]) & contains_xy(zone, GX, GY)
        if ma.sum() < 3 or mb.sum() < 3: continue
        step = float(np.median(val[mb]) - np.median(val[ma]))
        shared.append(dict(a=A["id"], b=B["id"], len_ft=ln.length / FT, step_m=step, geom=ln))
outline = []
for b in blocks:
    ln = b["poly"].boundary.intersection(fpl.exterior.buffer(0.5))
    outline.append((b["id"], ln.length / FT, ln))
# ---------- print
print("\nLEVEL HISTOGRAM (cell z, 0.3 m bins):", [(round(e[i], 1), int(h[i])) for i in range(len(h)) if h[i] > 40])
print("\nBLOCKS")
print(f"{'id':>3} {'area ft2':>9} {'zmean':>6} {'zmin':>6} {'zp95':>6} {'tilt':>5} {'pitch/12':>8} {'aspect':>6} {'flat':>5} {'rms':>5} {'cells':>6}  sub-planes")
for b in blocks:
    sp = "; ".join(f"{s['pitch']:.1f}/12 az{round(s['aspect']) if s['aspect'] is not None else '-'} {100*s['frac']:.0f}%" for s in b["planes"])
    print(f"{b['id']:3d} {b['area_ft2']:9.0f} {b['zmean']:6.2f} {b['zmin']:6.2f} {b['zp95']:6.2f} {b['tilt']:5.1f} {b['pitch']:8.2f} {str(round(b['aspect'])) if b['aspect'] is not None else '-':>6} {str(b['flat']):>5} {b['rms']:5.3f} {b['ncells']:6d}  {sp}")
print("\nSHARED BORDERS (ft, step m = B minus A)")
for s in shared: print(f"  {s['a']}-{s['b']}: {s['len_ft']:.1f} ft step {s['step_m']:+.2f} m")
print("\nOUTLINE LENGTH PER BLOCK (ft)")
for i_, L_, _ in outline: print(f"  block {i_}: {L_:.1f}")
print("total footprint outline ft:", round(fpl.exterior.length / FT, 1), " blocks cover ft2:", round(sum(b['area_ft2'] for b in blocks)), "of", round(fpl.area / FT**2))
# ---------- 5a NW hip block
hb = [b for b in blocks if b["poly"].contains(Point(9, 13))]
if hb:
    hb = hb[0]; rr = hb["poly"].minimum_rotated_rectangle; cs = np.array(rr.exterior.coords)
    sides = sorted([np.linalg.norm(cs[i + 1] - cs[i]) / FT for i in range(2)])
    mk = (flab == hb["id"]) & np.isfinite(val)
    zs = val[mk]
    # eave height: median of cells within 0.6 m of the block outline; ridge: p95
    edge = np.array([hb["poly"].boundary.distance(Point(a, b)) for a, b in zip(GX[mk], GY[mk])]) < 0.6
    print(f"\nNW HIP BLOCK id {hb['id']}: area {hb['area_ft2']:.0f} ft2, min-rect {sides[0]:.1f} x {sides[1]:.1f} ft, eave z (cells within 0.6 m of outline, median) {np.median(zs[edge]):.2f}, ridge z (p95) {np.percentile(zs,95):.2f}, rise {np.percentile(zs,95)-np.median(zs[edge]):.2f} m")
    print("   dominant plane pitch", round(hb["pitch"], 2), "/12 ; sub-planes:", hb["planes"])
else:
    print("NW hip block not found at (9,13)")
# ---------- 5b south awnings
print("\nSOUTH EDGE WINDOWS (points not ground, within band from 1 m inside to 3 m south of footprint south boundary), local metres")
coords = np.array(fpl.exterior.coords)
south = LineString([(0, -50), (60, -50)])
allP = np.c_[x, y, z, hag]
for (xa, xb) in [(14, 18), (22, 26), (26, 30), (30, 34), (34, 38), (40, 44)]:
    # south boundary y at x-centre: lowest footprint boundary y at that x
    xc = (xa + xb) / 2; ln = LineString([(xc, -30), (xc, 40)]).intersection(fpl)
    ymin = ln.bounds[1] if not ln.is_empty else np.nan
    for name, (y0, y1) in (("inside 0-1 m", (0, 1)), ("outside 0-3 m", (-3, 0))):
        m = (allP[:, 0] >= xa) & (allP[:, 0] < xb) & (allP[:, 1] >= ymin + y0 - (1 if y0 == 0 else 0) * 0 + (0 if y0 else 0)) & (allP[:, 1] < ymin + y1) if name.startswith("inside") else (allP[:, 0] >= xa) & (allP[:, 0] < xb) & (allP[:, 1] >= ymin - 3) & (allP[:, 1] < ymin)
        if name.startswith("inside"): m = (allP[:, 0] >= xa) & (allP[:, 0] < xb) & (allP[:, 1] >= ymin) & (allP[:, 1] < ymin + 1)
        m &= nonground
        if m.sum() < 5: print(f"  x {xa}-{xb} ({name}): n={m.sum()}"); continue
        Q = allP[m]
        bp = ransac_local(Q[:, :3], thr=0.06, min_pts=12)
        if bp:
            pl = bp[0]; rr = np.abs(Q[:, 2] - plane_z(pl, Q[:, 0], Q[:, 1])) < 0.06; t_, p_, a_ = plane_props(pl)
            best = f"best plane {rr.sum()}/{len(Q)} pts ({100*rr.mean():.0f}%) at z {np.median(Q[rr,2]):.2f} tilt {t_:.1f} deg pitch {p_:.1f}/12 aspect {a_:.0f}"
        else: best = "no plane >=12 pts"
        print(f"  x {xa}-{xb} ({name}): n={m.sum():3d} z min/med/max {Q[:,2].min():.2f}/{np.median(Q[:,2]):.2f}/{np.median(Q[:,2])*0+Q[:,2].max():.2f} sd {Q[:,2].std():.2f} hag med {np.median(Q[:,3]):.1f}; {best}")
# ---------- ground check (are the HAG 'levels' terrain?)
ring = nonground == False
gm = (c == 2) & contains_xy(fpl.buffer(8), x, y) & ~contains_xy(fpl.buffer(0.5), x, y)
cy = fpl.centroid.y; cx = fpl.centroid.x
for nm, mm in (("north half", y > cy), ("south half", y <= cy), ("west third", x < 17), ("east third", x > 33)):
    q = gm & mm
    print(f"ground (class 2) within 8 m of outline, {nm}: n={q.sum()} z median {np.median(z[q]):.2f} (p10 {np.percentile(z[q],10):.2f}, p90 {np.percentile(z[q],90):.2f})")
# ---------- 6 plot
fig, ax = plt.subplots(figsize=(18, 8))
cmn = plt.get_cmap("viridis"); zr = (min(b["zmean"] for b in blocks), max(b["zmean"] for b in blocks))
for b in blocks:
    g = b["poly"]; gs = g.geoms if hasattr(g, "geoms") else [g]
    for gg in gs: ax.fill(*gg.exterior.xy, color=cmn((b["zmean"] - zr[0]) / (zr[1] - zr[0] + 1e-9)), alpha=.55, ec="k", lw=.6)
    cc = g.representative_point()
    ax.text(cc.x, cc.y, f"#{b['id']}\n{b['area_ft2']:.0f} ft²\nz {b['zmean']:.2f}\n{'flat' if b['flat'] else str(round(b['pitch'],1))+'/12'}", ha="center", va="center", fontsize=7)
for s in shared:
    g = s["geom"]; gs = g.geoms if hasattr(g, "geoms") else [g]
    for gg in gs: ax.plot(*gg.xy, color="red" if abs(s["step_m"]) > 0.3 else "orange", lw=2.5)
    cc = g.representative_point(); ax.text(cc.x, cc.y, f"{s['len_ft']:.0f}ft\n{s['step_m']:+.2f}m", fontsize=6, color="darkred", ha="center")
ax.scatter(Pp[:, 0], Pp[:, 1], s=.3, c="k", alpha=.15)
ax.plot(*fpl.exterior.xy, "k-", lw=1.2); ax.set_aspect("equal")
ax.set_title("site 1 roof levels (height-continuity blocks; red = step > 0.3 m, orange = smaller step); labels: area, mean z (absolute m), flat/pitch")
plt.tight_layout(); plt.savefig(S + "/data/levels_plot.png", dpi=65)
json.dump(dict(blocks=[{k: v for k, v in b.items() if k != "poly"} for b in blocks], shared=[{k: v for k, v in s.items() if k != "geom"} for s in shared]), open(S + "/data/levels.json", "w"), indent=1, default=float)
# ---------- hip block as a whole (blocks whose centroid lies in local x 4-15, y 8-19 and are sloped)
hips = [b for b in blocks if not b["flat"] and 4 <= b["poly"].centroid.x <= 15 and 8 <= b["poly"].centroid.y <= 19]
U = unary_union([b["poly"] for b in hips]); rr = U.minimum_rotated_rectangle; cs = np.array(rr.exterior.coords)
sd = sorted([np.linalg.norm(cs[i + 1] - cs[i]) / FT for i in range(2)])
print(f"\nHIP BLOCK (union of {len(hips)} sloped faces): bounds {tuple(round(v,1) for v in U.bounds)} m, min-rect {sd[0]:.1f} x {sd[1]:.1f} ft, plan area {U.area/FT**2:.0f} ft2, true area {sum(b['area_ft2']/np.cos(np.radians(b['tilt'])) for b in hips):.0f} ft2")
for b in hips: print(f"   face #{b['id']}: aspect {b['aspect']:.0f} pitch {b['pitch']:.2f}/12 plan {b['area_ft2']:.0f} true {b['area_ft2']/np.cos(np.radians(b['tilt'])):.0f} ft2 z {b['zmin']:.2f}-{b['zp95']:.2f} rms {b['rms']:.3f}")
zz = np.concatenate([val[(flab == b['id']) & np.isfinite(val)] for b in hips])
print(f"   ridge z (p98) {np.percentile(zz,98):.2f}  lowest cells (p2) {np.percentile(zz,2):.2f}  rise {np.percentile(zz,98)-np.percentile(zz,2):.2f} m; mean pitch {np.mean([b['pitch'] for b in hips]):.2f}/12")

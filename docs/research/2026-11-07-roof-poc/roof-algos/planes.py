"""DIY roof plane extraction + edge classification (prototype).

Input : roof points (N,3) in a metric CRS (x east, y north, z up, metres) + footprint (shapely Polygon, same CRS)
Output: dict(planes=[...], edges=[...], totals={...}) in feet / sq ft, JSON-serialisable.

Steps: (a) 0.25 m grid + KD-tree of points, (b) iterative RANSAC (Open3D) + LS refit + reassignment,
(c) per-cell plane labels -> connected components -> polygons clipped to footprint, tilt/pitch/aspect/true area,
(d) edge classification: footprint-boundary edges (eave/rake/parapet/high-edge) via inward sampling,
    interior edges between planes (ridge/hip/valley/transition/step flashing/wall flashing) via plane intersection.
"""
import numpy as np
import open3d as o3d
from scipy import ndimage
from scipy.spatial import cKDTree
from shapely.geometry import Polygon, LineString, Point, box, MultiPolygon
from shapely.ops import unary_union
from shapely import contains_xy

FT = 0.3048
CELL = 0.25


# ---------------------------------------------------------------- plane helpers
def fit_ls(P):
    """Least-squares plane z = a x + b y + c (no vertical planes)."""
    A = np.column_stack([P[:, 0], P[:, 1], np.ones(len(P))])
    sol, *_ = np.linalg.lstsq(A, P[:, 2], rcond=None)
    return sol


def plane_z(pl, x, y):
    return pl[0] * x + pl[1] * y + pl[2]


def plane_props(pl):
    g = np.hypot(pl[0], pl[1])
    tilt = np.degrees(np.arctan(g))
    pitch = g * 12.0
    aspect = (np.degrees(np.arctan2(-pl[0], -pl[1]))) % 360 if g > 1e-6 else None  # downslope compass bearing
    return tilt, pitch, aspect


def ransac_planes(P, thr=0.10, min_pts=25, max_tilt=60, iters=3000, seed=1):
    """Sequential RANSAC with Open3D; returns list of plane params (a,b,c)."""
    o3d.utility.random.seed(seed)
    remaining = np.arange(len(P))
    planes = []
    for _ in range(12):
        if len(remaining) < min_pts:
            break
        pcd = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(P[remaining]))
        m, inl = pcd.segment_plane(distance_threshold=thr, ransac_n=3, num_iterations=iters)
        if len(inl) < min_pts:
            break
        a, b, c, d = m
        if abs(c) < 1e-6:
            remaining = np.delete(remaining, inl)
            continue
        pl = fit_ls(P[remaining[inl]])
        if np.degrees(np.arctan(np.hypot(pl[0], pl[1]))) > max_tilt:
            remaining = np.delete(remaining, inl)
            continue
        planes.append(pl)
        # remove all remaining points within thr of the refit plane
        res = np.abs(P[remaining, 2] - plane_z(pl, P[remaining, 0], P[remaining, 1]))
        remaining = remaining[res > thr]
    return planes


def ransac_local(P, thr=0.12, min_pts=25, max_tilt=60, iters=1500, radius=1.0, seed=1):
    """Sequential RANSAC whose 3-point samples come from one point's 1 m neighbourhood (avoids planes spanning facets);
    inliers must also form one connected blob (kNN graph, 1.0 m)."""
    rng = np.random.default_rng(seed)
    remaining = np.arange(len(P))
    planes = []
    for _ in range(14):
        if len(remaining) < min_pts:
            break
        Q = P[remaining]
        tree = cKDTree(Q[:, :2])
        nb = tree.query_ball_point(Q[:, :2], radius)
        best, best_n = None, 0
        for _i in range(iters):
            i = rng.integers(len(Q))
            if len(nb[i]) < 3:
                continue
            j, k = rng.choice(nb[i], 2, replace=False)
            if j == i or k == i or j == k:
                continue
            A = np.array([[Q[i, 0], Q[i, 1], 1], [Q[j, 0], Q[j, 1], 1], [Q[k, 0], Q[k, 1], 1]])
            if abs(np.linalg.det(A)) < 0.05:  # near-collinear in plan
                continue
            pl = np.linalg.solve(A, Q[[i, j, k], 2])
            if np.hypot(pl[0], pl[1]) > np.tan(np.radians(max_tilt)):
                continue
            n = int((np.abs(Q[:, 2] - plane_z(pl, Q[:, 0], Q[:, 1])) < thr).sum())
            if n > best_n:
                best, best_n = pl, n
        if best is None or best_n < min_pts:
            break
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        pl = best
        sel = np.array([], int)
        for _ in range(4):  # refit on the largest connected inlier blob, re-collect inliers, repeat
            inl = np.abs(Q[:, 2] - plane_z(pl, Q[:, 0], Q[:, 1])) < thr
            idx = np.nonzero(inl)[0]
            if len(idx) < 3:
                break
            t2 = cKDTree(Q[idx, :2])
            pairs = t2.query_pairs(0.9, output_type="ndarray")
            g = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(idx), len(idx)))
            nc, cl = connected_components(g, directed=False)
            big = np.bincount(cl).argmax()
            sel = idx[cl == big]
            if len(sel) < 3:
                break
            pl = fit_ls(Q[sel])
        if len(sel) < min_pts:
            remaining = np.delete(remaining, idx) if len(idx) else remaining
            continue
        planes.append(pl)
        res = np.abs(Q[:, 2] - plane_z(pl, Q[:, 0], Q[:, 1]))
        keepm = np.ones(len(Q), bool); keepm[sel] = False
        remaining = remaining[keepm]
    return planes


def merge_planes(P, planes, thr, max_deg=3.0, max_dz=0.10):
    """Merge near-coplanar planes (angle < max_deg and mean |dz| over their inliers < max_dz)."""
    planes = list(planes)
    changed = True
    while changed:
        changed = False
        inl = [np.abs(P[:, 2] - plane_z(p, P[:, 0], P[:, 1])) < thr for p in planes]
        for i in range(len(planes)):
            for j in range(i + 1, len(planes)):
                ni = np.array([-planes[i][0], -planes[i][1], 1.0]); nj = np.array([-planes[j][0], -planes[j][1], 1.0])
                ang = np.degrees(np.arccos(np.clip(ni @ nj / np.linalg.norm(ni) / np.linalg.norm(nj), -1, 1)))
                if ang > max_deg:
                    continue
                sel = inl[i] | inl[j]
                dz = np.abs(plane_z(planes[i], P[sel, 0], P[sel, 1]) - plane_z(planes[j], P[sel, 0], P[sel, 1])).mean()
                if dz < max_dz:
                    planes[i] = fit_ls(P[sel])
                    del planes[j]
                    changed = True
                    break
            if changed:
                break
    return planes


def refine(P, planes, thr=0.12, iters=4, min_pts=20):
    for _ in range(iters):
        R = np.column_stack([np.abs(P[:, 2] - plane_z(pl, P[:, 0], P[:, 1])) for pl in planes])
        lab = R.argmin(1)
        lab[R.min(1) > thr] = -1
        new = []
        for i in range(len(planes)):
            sel = lab == i
            new.append(fit_ls(P[sel]) if sel.sum() >= min_pts else planes[i])
        planes = new
    R = np.column_stack([np.abs(P[:, 2] - plane_z(pl, P[:, 0], P[:, 1])) for pl in planes])
    lab = R.argmin(1)
    lab[R.min(1) > thr] = -1
    return planes, lab


# ---------------------------------------------------------------- main
def analyse(P, fp, thr=0.12, flat_deg=2.0, min_area_m2=3.0, wall_dz=0.30, method='local', verbose=False):
    P = np.asarray(P, float)
    fp_in = fp.buffer(0.3)  # tolerate footprint misregistration
    keep = contains_xy(fp_in, P[:, 0], P[:, 1])
    P = P[keep]
    minx, miny, maxx, maxy = fp.bounds
    nx, ny = int(np.ceil((maxx - minx) / CELL)) + 1, int(np.ceil((maxy - miny) / CELL)) + 1
    # (a) grid (cell centres) + DSM(max) used for wall evidence
    xs = minx + (np.arange(nx) + 0.5) * CELL
    ys = miny + (np.arange(ny) + 0.5) * CELL
    GX, GY = np.meshgrid(xs, ys)
    inside = contains_xy(fp, GX, GY)
    dsm = np.full((ny, nx), np.nan)
    ci = np.clip(((P[:, 0] - minx) / CELL).astype(int), 0, nx - 1)
    cj = np.clip(((P[:, 1] - miny) / CELL).astype(int), 0, ny - 1)
    np.fmax.at(dsm, (cj, ci), P[:, 2])
    # (b) plane segmentation
    planes = ransac_local(P, thr=thr) if method == 'local' else ransac_planes(P, thr=thr)
    planes = merge_planes(P, planes, thr)
    planes, plab = refine(P, planes, thr=thr)
    # (c) label grid cells by nearest classified point (<=0.6 m), -1 = non-plane point (wall top, clutter)
    tree = cKDTree(P[:, :2])
    d, idx = tree.query(np.column_stack([GX.ravel(), GY.ravel()]), distance_upper_bound=0.7)
    lab = np.full(GX.size, -2)
    ok = np.isfinite(d)
    lab[ok] = plab[idx[ok]]
    lab = lab.reshape(ny, nx)
    lab[~inside] = -3
    # split each plane label into connected components; drop small / thin ones (wall-top strips, clutter)
    out = np.full_like(lab, -1)
    comps = []  # (plane_idx, mask)
    for i in range(len(planes)):
        cc, n = ndimage.label(lab == i)
        for c in range(1, n + 1):
            m = cc == c
            area = m.sum() * CELL**2
            # width test: max of distance transform ~ half the smallest width
            width = 2 * ndimage.distance_transform_edt(m).max() * CELL
            if area < min_area_m2 or width < 0.9:
                continue
            comps.append((i, m))
    cid = 0
    for (i, m) in comps:
        out[m] = cid
        cid += 1
    # fill gaps (-1/-2) inside the footprint with the nearest component (parapet rim, ridge seams, eaves)
    fillmask = inside & (out < 0)
    if fillmask.any() and cid > 0:
        _, (fi, fj) = ndimage.distance_transform_edt(~(out >= 0), return_indices=True)
        out[fillmask] = out[fi[fillmask], fj[fillmask]]
    lab = out
    # modal smoothing (3x3) to de-jag borders
    sm = lab.copy()
    for j in range(1, ny - 1):
        for i in range(1, nx - 1):
            if lab[j, i] < 0:
                continue
            w = lab[j - 1:j + 2, i - 1:i + 2].ravel()
            w = w[w >= 0]
            sm[j, i] = np.bincount(w).argmax()
    lab = sm
    # polygons
    result_planes = []
    for c, (pi, _) in enumerate(comps):
        m = lab == c
        if not m.any():
            continue
        js, is_ = np.nonzero(m)
        polys = [box(minx + i * CELL, miny + j * CELL, minx + (i + 1) * CELL, miny + (j + 1) * CELL) for j, i in zip(js, is_)]
        poly = unary_union(polys).intersection(fp)
        if poly.is_empty:
            continue
        pl = planes[pi]
        tilt, pitch, aspect = plane_props(pl)
        proj = poly.area
        true_area = proj / np.cos(np.radians(tilt))
        is_flat = tilt < flat_deg
        result_planes.append(dict(id=c, plane=pl, poly=poly, tilt=tilt, pitch=pitch, aspect=None if is_flat else aspect,
                                  flat=is_flat, proj_area_m2=proj, area_ft2=true_area / FT**2, npts=int((plab == pi).sum())))
    # merge coplanar neighbours produced by the same RANSAC plane? (kept separate if disconnected)
    # (d) edges
    edges = []
    labcell = lambda x, y: (lab[int((y - miny) / CELL), int((x - minx) / CELL)]
                            if 0 <= (x - minx) / CELL < nx and 0 <= (y - miny) / CELL < ny else -1)
    by_id = {p["id"]: p for p in result_planes}
    treeP = cKDTree(P[:, :2])

    def wall_evidence(pts_xy, pl):
        """Fraction of sample points (on footprint edge) with points rising >wall_dz above plane within 0.6 m inside."""
        hits = 0
        for (x, y) in pts_xy:
            ii = treeP.query_ball_point([x, y], 0.6)
            if not ii:
                continue
            ex = P[ii, 2] - plane_z(pl, P[ii, 0], P[ii, 1])
            hits += ex.max() > wall_dz
        return hits / max(len(pts_xy), 1)

    rings = [(fp.exterior, True)] + [(r_, False) for r_ in fp.interiors]
    step = 0.05
    for ring, is_ext in rings:
        coords = np.array(ring.coords)
        ccw = ring.is_ccw
        for k in range(len(coords) - 1):
            a, b = coords[k], coords[k + 1]
            L = np.linalg.norm(b - a)
            if L < 0.05:
                continue
            dvec = (b - a) / L
            inward = np.array([-dvec[1], dvec[0]]) if ccw == is_ext else np.array([dvec[1], -dvec[0]])
            n = max(int(L / step), 1)
            runs = []
            for s in range(n):
                t = (s + 0.5) * L / n
                p = a + dvec * t
                q = p + inward * 0.2
                l = labcell(*q)
                runs.append((l, p))
            # group consecutive samples with same plane label
            g0 = 0
            for s in range(1, n + 1):
                if s == n or runs[s][0] != runs[g0][0]:
                    l = runs[g0][0]
                    seg = runs[g0:s]
                    plan_len = len(seg) * L / n
                    g0 = s
                    if l < 0 or l not in by_id:
                        continue
                    pr = by_id[l]
                    pl = pr["plane"]
                    pts = [p for _, p in seg]
                    sub = wall_evidence(pts[::4], pl) > 0.5
                    phi_cos = abs(float(np.dot(dvec, np.array([-pl[0], -pl[1]]) / max(np.hypot(pl[0], pl[1]), 1e-9))))
                    if pr["flat"]:
                        kind = "parapet" if sub else "eave"
                        len3 = plan_len
                    else:
                        down = np.array([-pl[0], -pl[1]])
                        down /= np.linalg.norm(down)
                        out_dot = float(np.dot(-inward, down))  # >0: the footprint edge is on the low side
                        slope_e = np.hypot(pl[0], pl[1]) * phi_cos
                        len3 = plan_len * np.sqrt(1 + slope_e**2)
                        if sub:
                            kind = "step_flashing"  # sloped plane against a rising wall
                        elif phi_cos > 0.5:
                            kind = "rake"
                        elif out_dot > 0:
                            kind = "eave"
                        else:
                            kind = "high_edge"
                    edges.append(dict(kind=kind, plane=l, len_ft=len3 / FT, plan_len_ft=plan_len / FT, where="footprint", _seg=k, _ring=id(ring), xy=[list(map(float, pts[0])), list(map(float, pts[-1]))]))
    # absorb short (<3 ft) footprint runs (corner artefacts next to hips) into the longest run of the same footprint edge
    from collections import defaultdict
    grp = defaultdict(list)
    for e in edges:
        grp[(e["_ring"], e["_seg"])].append(e)
    merged = []
    for key, lst in grp.items():
        longest = max(lst, key=lambda e: e["plan_len_ft"])
        for e in lst:
            if e is not longest and e["plan_len_ft"] < 3.0 and e["kind"] != longest["kind"]:
                longest["len_ft"] += e["len_ft"]; longest["plan_len_ft"] += e["plan_len_ft"]
            else:
                merged.append(e)
    edges = merged
    # interior shared borders
    ids = sorted(by_id)
    for ia in range(len(ids)):
        for ib in range(ia + 1, len(ids)):
            A, B = by_id[ids[ia]], by_id[ids[ib]]
            bd = A["poly"].boundary.intersection(B["poly"].buffer(0.3))
            if bd.is_empty:
                continue
            # remove parts lying on the footprint boundary
            bd = bd.difference(fp.exterior.buffer(0.08))
            if bd.is_empty or bd.length < 0.5:
                continue
            xy = np.array([c for g in (bd.geoms if hasattr(bd, "geoms") else [bd]) for c in g.coords])
            plA, plB = A["plane"], B["plane"]
            # jump at midpoint
            m = xy.mean(0)
            zA, zB = plane_z(plA, *m), plane_z(plB, *m)
            # crease direction in plan = intersection of the 2 planes
            n1 = np.array([-plA[0], -plA[1], 1.0]); n2 = np.array([-plB[0], -plB[1], 1.0])
            dir3 = np.cross(n1, n2)
            dxy = dir3[:2]
            if np.linalg.norm(dxy) < 1e-6:  # parallel planes (walls/steps between flats)
                # use principal axis of the border
                u, s, vt = np.linalg.svd(xy - xy.mean(0))
                dxy = vt[0]
                dir3 = np.array([dxy[0], dxy[1], 0.0])
            dxy = dxy / np.linalg.norm(dxy)
            proj = (xy - xy.mean(0)) @ dxy
            tmin, tmax = proj.min(), proj.max()
            # snap crease ends to junctions with a third plane C (3-plane intersection) when one lies within 1 m of an end
            if np.linalg.norm(np.cross(n1, n2)[:2]) > 1e-6:
                c0 = xy.mean(0)
                for C in by_id.values():
                    if C is A or C is B:
                        continue
                    M = np.array([[-plA[0], -plA[1], 1.0], [-plB[0], -plB[1], 1.0], [-C["plane"][0], -C["plane"][1], 1.0]])
                    if abs(np.linalg.det(M)) < 1e-3:
                        continue
                    J = np.linalg.solve(M, np.array([plA[2], plB[2], C["plane"][2]]))
                    tj = float((J[:2] - c0) @ dxy)
                    perp_off = abs(float((J[:2] - c0) @ np.array([-dxy[1], dxy[0]])))
                    # only if C actually touches this crease (its polygon is near the junction)
                    if C["poly"].distance(Point(J[:2])) > 0.6 or perp_off > 1.5:
                        continue
                    if abs(tj - tmin) < 1.0:
                        tmin = tj
                    elif abs(tj - tmax) < 1.0:
                        tmax = tj
            plan_ext = tmax - tmin
            if plan_ext < 0.5:
                continue
            jump = abs(zA - zB)
            c0_ = xy.mean(0)
            seg_xy = [list(map(float, c0_ + dxy * tmin)), list(map(float, c0_ + dxy * tmax))]
            if A['flat'] and B['flat'] and jump <= wall_dz:
                continue  # drainage seam between flat sections, not an edge
            if jump > wall_dz:
                low, high = (A, B) if zA < zB else (B, A)
                kind = "wall_flashing" if low["flat"] else "step_flashing"
                # wall edge line follows the border: slope of low plane along the border
                pl = low["plane"]
                se = abs(np.dot([pl[0], pl[1]], dxy))
                len3 = plan_ext * np.sqrt(1 + se**2)
                edges.append(dict(kind=kind, plane=low["id"], other=high["id"], len_ft=len3 / FT, plan_len_ft=plan_ext / FT, where="interior", xy=seg_xy))
                continue
            # crease: convex/concave. probe 0.6 m into A perpendicular to crease
            perp = np.array([-dxy[1], dxy[0]])
            cen = A["poly"].centroid
            if np.dot(np.array([cen.x, cen.y]) - m, perp) < 0:
                perp = -perp
            pA = m + perp * 0.6
            concave = plane_z(plB, *pA) < plane_z(plA, *pA)
            slope_line = np.degrees(np.arctan2(abs(dir3[2]), np.linalg.norm(dir3[:2])))
            len3 = plan_ext / np.cos(np.radians(slope_line))
            dasp = None
            if A["aspect"] is not None and B["aspect"] is not None:
                dasp = abs((A["aspect"] - B["aspect"] + 180) % 360 - 180)
            if (A["flat"] != B["flat"] or (dasp is not None and dasp < 20)) and not concave and slope_line < 5 and False:
                kind = "transition"
            elif dasp is not None and dasp < 20 and abs(A["tilt"] - B["tilt"]) > 3:
                kind = "transition"
            elif concave:
                kind = "valley"
            else:
                kind = "ridge" if slope_line < 5 else "hip"
            edges.append(dict(kind=kind, plane=A["id"], other=B["id"], len_ft=len3 / FT, plan_len_ft=plan_ext / FT,
                              where="interior", line_slope_deg=slope_line, xy=seg_xy))
    totals = {}
    for e in edges:
        totals[e["kind"]] = totals.get(e["kind"], 0.0) + e["len_ft"]
    ar = sum(p["area_ft2"] for p in result_planes)
    flat_ar = sum(p["area_ft2"] for p in result_planes if p["flat"])
    summary = dict(total_area_ft2=ar, flat_area_ft2=flat_ar, pitched_area_ft2=ar - flat_ar, n_planes=len(result_planes),
                   edges_ft=totals)
    pj = [dict(id=p["id"], tilt_deg=p["tilt"], pitch_12=p["pitch"], aspect_deg=p["aspect"], flat=p["flat"],
               area_ft2=p["area_ft2"], n_points=p["npts"], polygon_xy_m=[list(map(list, p["poly"].exterior.coords))] if p["poly"].geom_type == "Polygon" else None)
          for p in result_planes]
    return dict(planes=pj, edges=edges, totals=summary, _planes=result_planes)

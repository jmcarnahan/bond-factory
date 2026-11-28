"""Every tunable of the roof engine in one frozen dataclass (no env vars, no module state).

Units are in the comment of each field: ``m`` metres, ``m2`` square metres, ``deg`` degrees, ``rise`` is inches of
rise per 12 inches of run (so 2.0 means a 2/12 pitch), ``pts`` a point count, ``ratio`` a unitless fraction.
The values are the reference engine's (the spike's final configuration); this module only names them.
``stable_hash()`` is the cache key / harness key: a sha256 of the sorted fields.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, fields


@dataclass(frozen=True)
class EngineParams:
    # ---- step 2: flat roofs, steep strips and pitched patches
    s2_flat: bool = True
    s2_steep_rise: float = 2.0  # rise: narrow outline strips at least this steep are examined by the eave-evidence test (_has_own_eave: level outer edge, normal point density); a strip that fails is absorbed. Not a pitch cutoff any more
    s2_strip_cap_rise: float = 14.0  # rise: above this a strip is never a roof facet (= plane_pitch_max)
    s2_eave_slope: float = 0.10  # m/m: a facet's outer edge is an eave when the plane rises less than this per metre along it
    s2_strip_density: float = 0.5  # ratio: ... and its returns are at least this share as dense as the roof's
    s2_eave_min_cells: int = 6  # cells: outer edge shorter than this cannot be judged (strip is then dropped as before)
    s2_eave_min_len_m: float = 0.8  # m: ... or shorter than this
    s2_strip_width: float = 1.5  # m: ... when narrower than this
    s2_patch_area: float = 15.0  # m2: a pitched patch inside a flat roof is real only above this ...
    s2_patch_rms: float = 0.05  # m: ... with a plane rms below this ...
    s2_patch_pitch: float = 2.0  # rise: ... and at least this pitch
    s2_strip_outside_share: float = 0.1  # ratio of the strip's ring that must lie outside the outline
    # ---- step 3: building frame (axis alignment) and aspect snapping
    s3_axis: bool = True  # work in the building frame (dominant wall direction = x)
    s3_snap_az: float = 10.0  # deg: aspects within this of a wall axis snap onto it
    # ---- step 4: gentle small-facet merge
    s4_gentle: bool = True
    s4_keep_area: float = 1.5  # m2: a well-fitted small facet at least this big may stay ...
    s4_rms: float = 0.05  # m: ... with an rms below this ...
    s4_pts: int = 12  # pts: ... and at least this many points ...
    s4_crease_share: float = 0.6  # ratio: ... and this share of its boundary on plane-intersection lines
    s4_crease_gap: float = 0.12  # m: a shared boundary point is "on the crease" when the planes differ by less
    # ---- density and verdict (plan 3.9)
    density_refuse: float = 4.0  # pts/m2 on the roof: below this the engine refuses (lidar_too_sparse)
    refuse_sparse: bool = True
    min_points: int = 15  # pts: fewer than this in the crop cannot hold one plane: refuse
    density_ok: float = 6.0  # pts/m2: below this the verdict is low_density
    mismatch_lo: float = 0.70  # ratio: roof support / outline below this: outline_mismatch
    mismatch_hi: float = 1.30  # ratio: ... above this: outline_mismatch
    mismatch_shift: float = 0.17  # ratio: outline_shift at or above this: outline_mismatch
    no_evidence_share: float = 0.20  # ratio: edge_no_evidence_share at or above this: outline_no_evidence (160 houses: 3 at 0.29-0.47, next 0.11)
    roof_continues_share: float = 0.10  # ratio: edge_end_share at or above this: roof_continues (160 houses: max 0.03; an attached roof along a tenth of the outline)
    part_missed_min_sqft: float = 32.3  # sq ft: roof_part_missed_sqft at or above this (the objects step's own 3 m2 gate): roof_part_missed
    planes_min_assigned_pct: float = 50.0  # percent: fewer returns on detected planes than this (or none found): poor_fit, reason planes_not_found (synthetic 14/12 cross gable at 8 pts/m2 before the steep fix drew one flat facet)
    fit_floor: float = 0.55  # ratio: fit_all below this: poor_fit
    fit_outline_margin_m: float = 0.3  # m: fit_all / fit_covered count the returns inside the drawn outline grown by this (the edge regularisation tolerance 0.15 m plus the finder's per-side noise, about 0.15 m)
    supported_floor: float = 70.0  # percent: supported area below this: poor_fit
    # ---- input preparation
    crop_buffer_m: float = 1.3  # m: points kept within this of the footprint
    thin_above_pts: int = 9000  # pts: voxel-thin a crop denser than this
    thin_voxel_m: float = 0.22  # m: voxel edge when thinning
    max_points: int = 60000  # pts: hard cap after thinning (deterministic stride); never reached on real roofs
    ring_filter: bool = True  # drop ring returns (outside the footprint) that cannot be roof, before plane detection
    ring_guard_m: float = 0.7  # m: only returns further than this from the footprint are tested (the overhang and the footprint's own error stay)
    ring_k: int = 12  # pts: nearest inside-the-footprint returns whose highest z is the roof height beside a ring point
    ring_above_m: float = 0.5  # m: a ring return this far above that is a crown or a neighbour's wall
    ring_cell_m: float = 0.3  # m: cell for the span test
    ring_span_m: float = 0.8  # m: a ring cell whose returns span more than this in height is a wall or a crown (12/12 over 0.3 m is 0.3 m)
    # ---- normals and region growing
    knn_k: int = 12  # pts: neighbours for the local normal
    knn_radius_m: float = 1.0  # m
    knn_min_valid: int = 6  # pts: fewer valid neighbours than this: no normal
    grow_angle_deg: float = 14.0  # deg: normal deviation allowed when growing
    grow_dist_m: float = 0.12  # m: distance to the growing plane allowed
    grow_min_pts: int = 15  # pts: smallest grown region kept
    grow_nbrs: int = 8  # pts: neighbours walked per point
    grow_seed_min: int = 4  # pts: free neighbours needed to start a seed
    grow_refit_factor: float = 1.25  # ratio: refit the growing plane every time it grew by this factor
    grow_refit_min: int = 8  # pts: ... but not before this many members
    # ---- plane assignment, merging, filtering
    assign_tol_m: float = 0.15  # m: a point belongs to a plane within this (first and final assignment)
    refit_tol_m: float = 0.13  # m: tolerance inside refit loops
    assign_drop_islands: bool = True  # unlabel small islands of a plane (tree crowns, equipment returns that fit an infinite roof plane)
    assign_link_m: float = 1.0  # m: plan distance that links two points of one plane into one body (4 pts/m2 spacing is 0.5)
    assign_island_pts: int = 25  # pts: an island of fewer points than this, apart from the plane's main body, is dropped ...
    assign_island_min_pts: int = 12  # pts: ... when it has at least this many (fewer are creased strays, kept). EVIDENCE: one synthetic case (complex hip: dropping strays cost 7 IoU points) and the tree L; +-20% (10 / 14): no tuning swing
    assign_island_rms_m: float = 0.0  # m: ... and only when their residual rms to the plane exceeds this floor (0 = off: real and crown islands overlap in rms) ...
    assign_island_noise_x: float = 0.0  # ratio: ... and this x the plane's main-body rms (0 = off)
    refit_min_pts: int = 6  # pts: smallest member set refitted
    coplanar_gdiff: float = 0.06  # rise/12 gradient difference below which two planes may merge
    coplanar_mdist_m: float = 0.10  # m: mean cross distance
    coplanar_rms_m: float = 0.06  # m: rms of the merged fit
    coplanar_near_m: float = 0.8  # m: the two point sets must come this close
    plane_min_pts: int = 12  # pts: smallest plane kept
    plane_min_area_m2: float = 4.0  # m2: smallest plane kept (unless "good small")
    support_cell_m: float = 0.35  # m: cell edge of the support-area estimate
    support_grid_m: float = 0.30  # m: raster step of the support-radius estimate
    good_small_area_m2: float = 1.5  # m2: a clean small plane (dormer, hip end) is kept above this
    good_small_rms_m: float = 0.05  # m
    good_small_pitch: float = 2.0  # rise
    plane_rms_max_m: float = 0.08  # m: noisier planes are dropped
    plane_pitch_max: float = 14.0  # rise: steeper planes are dropped unless big (below)
    plane_pitch_hard: float = 20.0  # rise: no plane steeper than this is ever a roof facet
    plane_steep_area_m2: float = 15.0  # m2: a plane between plane_pitch_max and plane_pitch_hard is kept when its support is at least this (synthetic 14-16/12 gable, hip, cross gable at 8 and 16 pts/m2; tuning: small steep patches are walls and trees)
    thin_radius_m: float = 0.55  # m: inscribed radius below which a plane is a strip (first pass)
    thin_area_m2: float = 12.0  # m2: ... when smaller than this
    thin2_radius_m: float = 0.75  # m: second-pass strip radius
    thin2_area_m2: float = 14.0  # m2
    thin2_keep_radius_m: float = 0.35  # m: a good small plane at least this wide is kept in the second pass
    outside_buffer_m: float = 0.6  # m: footprint buffer for the "mostly outside" test
    outside_min_share: float = 0.5  # ratio: a plane with less than this inside is dropped
    identical_gdiff: float = 0.03  # gradient difference below which planes became identical after regularisation
    identical_mean_m: float = 0.07  # m: mean cross residual
    # ---- regularisation
    reg_flat_rise: float = 0.5  # rise: below this a plane is flattened
    reg_grad_min: float = 0.10  # gradient (m/m) below which the aspect is not snapped
    reg_pitched_rise: float = 0.8  # rise: planes at or above this take part in pitch equalisation
    reg_pitch_tol: float = 0.5  # rise: pitches within this are equalised
    reg_opposing_deg: float = 155.0  # deg: aspects further apart than this are "opposing" (gable halves)
    reg_opposing_tol: float = 0.7  # rise: opposing slopes equalise within this
    flat_cut_rise: float = 2.0  # rise: below this a facet is "flat", at or above "pitched"
    reg_below_cut_rise: float = 1.99  # rise: a plane below the cut is never pushed above this
    # ---- outline
    footprint_snap_deg: float = 15.0  # deg: footprint edges within this of the axes are orthogonalised
    footprint_tol_m: float = 0.12  # m: simplify tolerance when orthogonalising the footprint
    final_snap_deg: float = 12.0  # deg: the same for the final roof outline
    final_tol_m: float = 0.15  # m
    ring_min_edge_m: float = 0.6  # m: shorter outline edges are removed
    offset_parallel_det: float = 0.08  # ratio: consecutive offset lines closer to parallel than this (|det|) use the mean offset
    offset_corner_max_m: float = 3.0  # m: an offset corner further than this from the original corner falls back to the mean offset
    offset_area_lo: float = 0.7  # ratio: an offset outline under this x the ring area is rejected (buffer fallback)
    footprint_area_lo: float = 0.8  # ratio: an orthogonalised footprint under this x the original is rejected
    footprint_area_hi: float = 1.2  # ratio: ... or over this
    footprint_simplify_m: float = 0.1  # m: fallback simplification of the footprint
    final_area_lo: float = 0.9  # ratio: a regularised final outline under this x the unregularised one is rejected
    final_area_hi: float = 1.1  # ratio: ... or over this
    outline_close_m: float = 0.15  # m: slits in the roof outline narrower than twice this are closed (the harness's own closing is 0.5 m wide)
    final_min_edge_m: float = 0.3  # m: shorter edges are removed from the FINAL outline (below the 0.45 m step a side is split at, so a measured eave jog stays)
    # ---- roof-edge finder (edge_finder.py): strips across each ring side, the run of returns on the roof plane
    edge_hag_m: float = 1.0  # m: a non-ground return this far above the local ground may be roof
    edge_ground_k: int = 6  # pts: the local ground is the median z of this many nearest ground returns
    edge_min_side_m: float = 1.2  # m: shorter ring sides get no strips (filled from the sides facing the same way)
    edge_step_m: float = 0.9  # m: strip spacing along a side
    edge_half_m: float = 0.45  # m: strip half width
    edge_in_m: float = 2.7  # m: strips start this far inside the ring side ...
    edge_out_m: float = 3.0  # m: ... and end this far outside it
    edge_inner_from_m: float = 1.5  # m: the inner window (local plane height, inner spacing, start of the walk) runs from this far inside ...
    edge_inner_to_m: float = 0.3  # m: ... to this far inside; the plane of a return is that of the nearest roof point inside this
    edge_plane_pad_m: float = 0.3  # m: roof points this far past a strip's ends may lend it their plane
    edge_plane_share: float = 0.25  # ratio: only planes holding this share of a strip's inner-window roof points lend it a plane (a cover's own plane reaching inside the ring does not)
    edge_min_plane_pts: int = 4  # pts: a strip with fewer roof points inside the edge has no plane (rejected)
    edge_min_strip_pts: int = 6  # pts: a strip with fewer candidate returns is rejected (10 rejected most strips of a 35%-thinned house)
    edge_warp_min_pts: int = 3  # pts: inner returns needed to correct the plane's local height
    edge_tol_m: float = 0.15  # m: a return within this of the local plane is a roof return
    edge_min_roof_pts: int = 4  # pts: a strip with fewer roof returns past the inner start is rejected
    edge_gap_m: float = 0.45  # m: the run of roof returns ends at the first gap longer than this ...
    edge_gap_k: float = 4.0  # returns: ... or than this many inner spacings (1 / returns per metre), whichever is longer: sparse roofs keep their area
    edge_gap_lam_floor: float = 0.5  # returns per m: floor of the inner rate in that spacing
    edge_end_margin_m: float = 0.3  # m: a run that reaches this close to the window end is no edge (cover, neighbour)
    edge_extend_m: float = 3.0  # m: a strip whose run reaches the window end looks this much further once; there the run's end counts only with a visible drop ...
    edge_extend_dn_min: int = 1  # pts: ... at least this many returns edge_dn_m below the surface within edge_up_win_m of the run's end
    edge_knee_m: float = 0.9  # m: the return rate at the run's end is counted over this last stretch ...
    edge_allow: float = 0.75  # spacings: ... and the edge lies this many spacings (1 / that rate) past the last roof return. 1.0 is unbiased for Poisson sampling; airborne LiDAR is stratified (scan lines), where the last of n returns across a strip lies n / (n + 1) spacings in (n about 2.5 at 8 pts/m2 in a 0.9 m strip); 1.0 put the synthetic d8 roofs 1.5-2.6% over
    edge_lam_min: float = 1.0  # returns per m: floor of that rate
    edge_up_m: float = 0.45  # m: a return this far ABOVE the plane just past the run ...
    edge_up_win_m: float = 0.76  # m: ... within this of the last roof return ...
    edge_up_max: int = 3  # pts: ... more than this many reject the strip (a tree over the edge) ...
    edge_dn_m: float = 0.45  # m: ... unless returns this far BELOW the plane ...
    edge_dn_win_m: float = 0.3  # m: ... within this of the last roof return ...
    edge_dn_min: int = 2  # pts: ... number at least this many (ground or wall seen: the edge is visible)
    edge_dev_m: float = 0.3  # m: a strip further than max(this, 3 MAD) from its side's median is dropped
    edge_min_strips: int = 2  # strips: a side needs this many kept strips for an offset
    edge_same_facing_deg: float = 25.0  # deg: sides whose normals agree within this face the same way (fill, registration)
    edge_shift_max_m: float = 2.0  # m: a registration shift longer than this is refused (the ring stays put)
    edge_split_m: float = 0.45  # m: a side whose strips form two runs further apart than this is split at the step ...
    edge_split_min_strips: int = 3  # strips: ... each run at least this many strips (2 split 66 sides in 56 of 151 houses, about half of the shortest false) ...
    edge_split_share: float = 0.75  # ratio: ... with at least this share of each run within edge_dev_m of its median
    edge_clamp_lo_m: float = 0.6  # m: a filled or tree-only side moves inward at most this far (a measured side keeps its measurement)
    edge_clamp_hi_m: float = 1.5  # m: a filled or tree-only side of a county (wall-line) outline moves outward at most this far
    edge_clamp_hi_roofedge_m: float = 0.5  # m: the same for an outline that already traces the roof edge (OpenStreetMap, LiDAR hull)
    support_buffer_m: float = 1.0  # m: the roof-point support (quality: roof_cover_of_outline) counts within the wall line grown by this
    support_cell_k: float = 1.0  # spacings: its cell edge is this many point spacings (1.0 in the registered frame matches the old support-polygon ratio: 160-house median 1.071 against 1.070) ...
    support_cell_max_m: float = 1.0  # m: ... at most this (and at least support_cell_m)
    # ---- labelling raster and graph cut
    grid_min_m: float = 0.12  # m: label raster step (never finer)
    grid_cells_target: float = 22000.0  # cells: step = sqrt(outline area / this)
    grid_quantum_m: float = 0.01  # m: the step is rounded up to a multiple of this, so a centimetre of outline does not change it
    label_clip_m: float = 0.10  # m: the labelled cells are kept inside the outline grown by this
    cost_tau_m: float = 0.25  # m: residual saturation in the data cost
    cost_nbrs: int = 5  # pts: neighbours per cell in the data cost
    cost_sigma_m: float = 0.30  # m: weight falloff
    cost_lambda: float = 0.35  # ratio: weight of the distance-to-label-support term
    cost_label_weight: float = 0.5  # ratio: weight of label mismatch versus residual
    cost_radius_m: float = 1.2  # m: neighbour search radius
    cost_support_dist_m: float = 1.5  # m: support-distance saturation
    graphcut_rounds: int = 4  # alpha-beta swap rounds
    graphcut_scale: int = 300  # integer scaling of the capacities
    beta_schedule: tuple[float, ...] = (0.9, 1.8, 3.2)  # smoothness weights tried in turn
    beta_m2_per_facet: float = 20.0  # m2 of outline per allowed facet before a smoother beta is tried
    beta_extra_facets: float = 2.0  # facets added to that allowance
    beta_keep_ratio: float = 0.8  # a smoother result replaces the best only when it has fewer than this share of facets
    # ---- clutter absorption on the label raster
    absorb_iters: int = 12
    absorb_flat_gap_m: float = 0.3  # m: flat labels merge when their mean boundary gap is below this
    absorb_one_plane_rms_m: float = 0.07  # m: ... or one plane explains both
    absorb_merge_rms_m: float = 0.09  # m: a merged plane may not exceed this rms
    absorb_gdiff: float = 0.05  # gradient difference for coplanar pitched labels
    absorb_pitched_gap_m: float = 0.12  # m
    absorb_min_pts: int = 12  # pts: points needed to judge a merge
    absorb_fit_min_pts: int = 6  # pts: smallest union refitted when two labels merge
    absorb_min_ring_cells: int = 4  # cells: a patch needs this many labelled cells round it to be judged
    clutter_area_m2: float = 15.0  # m2: patches up to this are clutter candidates
    clutter_small_area_m2: float = 6.0  # m2
    clutter_above_m: float = 0.3  # m: a small patch this far above its flat neighbour is clutter
    clutter_neighbour_share: float = 0.8  # ratio of ring cells that must agree
    clutter_outside_share: float = 0.25  # ratio: more outside than this and it is not an inner patch
    parapet_outside_share: float = 0.2  # ratio
    parapet_radius_m: float = 0.6  # m: inscribed radius of a parapet strip
    parapet_height_m: float = 0.15  # m: a parapet stands this much above the flat roof
    parapet_neighbour_share: float = 0.8  # ratio
    flat_patch_share: float = 0.6  # ratio: neighbours that must be flat for a pitched patch to be junk
    flat_patch_outside_share: float = 0.6  # ratio
    # ---- vectorisation
    simplify_tol_m: float = 0.25  # m: coverage-simplify tolerance
    min_polygon_m2: float = 0.05  # m2: smaller vectorised pieces are dropped
    crease_max_move_m: float = 0.7  # m: vertices move at most this onto a crease
    crease_extend_m: float = 1.0  # m: a crease chain ending on the outline is carried this far along its line. EVIDENCE: one synthetic case (dutch gable, hip 0.6 m short of the corner); tuning changes 0 houses
    small_cell_m2: float = 1.0  # m2: polygonized cells smaller than this are assigned by plane fit to their points
    small_cell_reach_m: float = 0.15  # m: points this near the cell count
    small_cell_min_pts: int = 3  # pts: fewer points and the cell keeps the facet it was cut from
    crease_junction_move_m: float = 1.3  # m: a three-facet junction moves at most this onto the point where its planes meet. EVIDENCE: one synthetic case (low-slope L at 8 pts/m2: raster node 1.0 m off); tuning identical at 1.04 and 1.56 (+-20%), synthetic 87 in both
    crease_gap_m: float = 0.35  # m: planes must be this close at a vertex to snap
    crease_parallel: float = 0.05  # gradient difference below which two planes are parallel
    # ---- facet cleanup
    sliver_area_m2: float = 1.5  # m2: facets smaller than this are slivers
    sliver_thin_area_m2: float = 4.0  # m2: ... or smaller than this and thinner than ...
    sliver_width_m: float = 0.45  # m
    small_facet_m2: float = 12.0  # m2: facets below this may merge into a neighbour
    off_plane_facet_mad_m: float = 0.35  # m: a small facet whose returns (all of them, assigned or not) have a median residual over its plane above this is not a roof plane: the neighbour with the longest shared boundary takes it (tree crown, clutter). EVIDENCE: 3 of 237 small facets of the tuning houses lie between 0.25 and 0.5; a real small hip end 0.16, a tree facet 0.75
    small_merge_rms_m: float = 0.045  # m: ... when the neighbour's rms rises by less than this
    coplanar_facet_gtol: float = 0.05  # gradient: adjacent facets merge when planes differ by less ...
    coplanar_facet_gap_m: float = 0.2  # m: ... and their mean gap is below this
    enclosed_flat_absorb: bool = True  # flat junk inside a pitched roof: rounded-ridge strips and enclosed small flat patches
    ridge_strip_width_m: float = 1.4  # m: a flat strip narrower than this (2 x area / perimeter) between pitched facets is a rounded ridge
    ridge_strip_max_rise: float = 1.0  # rise: ... and its plane is level (a rounded ridge top is flat; a 1.9/12 plane is a real low-slope facet: a real low-slope double-gable roof lost its whole south slope to this rule at width 2.2 / any flat-cut plane)
    ridge_strip_area_m2: float = 60.0  # m2: ... and smaller than this
    ridge_strip_rise_m: float = 0.05  # m: ... when the pitched neighbours extrapolate at least this far above the strip (rounded top)
    enclosed_flat_m2: float = 8.0  # m2: a flat patch smaller than this enclosed by pitched facets is a hole or sliver
    enclosed_pitched_share: float = 0.7  # ratio: share of its shared boundary against pitched facets
    enclosed_outline_share: float = 0.3  # ratio: a flat patch with more of its boundary than this on the roof outline is a real porch roof: kept
    ridge_strip_join_m: float = 0.06  # m: pieces of a cut strip join their facet across a gap up to this
    ridge_strip_cell_m: float = 0.1  # m: raster step when a ridge strip is cut between its neighbours
    gap_close_width_m: float = 0.5  # m: a channel between facets narrower than this (2 x area / perimeter) is closed (given to the facet sharing most boundary)
    gap_close_min_m2: float = 0.05  # m2: ... when at least this big
    flat_merge_fitting: bool = True  # merge adjacent flat facets when one plane keeps the fit (one flat region = one facet)
    flat_merge_min_edge_m: float = 0.5  # m: ... sharing at least this much boundary
    flat_merge_min_pts: int = 12  # pts: ... with at least this many returns in the pair
    flat_merge_fit_drop: float = 0.02  # ratio: the merged plane may lose at most this share of points within fit_tol_m
    junk_absorb: bool = True  # absorb small facets sitting against flat roof into the flat facet (equipment, bulkheads, platforms)
    junk_area_m2: float = 6.0  # m2: facets smaller than this are candidates (brief: equipment and bulkheads under 6 m2)
    junk_flat_share: float = 0.7  # ratio: share of the facet's shared boundary that must lie against flat facets
    strip_absorb: bool = True  # absorb thin facets along the roof edge into their neighbour (gutter / fascia / flattened eave)
    strip_width_m: float = 0.6  # m: a strip is narrower than this (2 x area / perimeter)
    strip_area_m2: float = 15.0  # m2: ... and smaller than this
    strip_outline_share: float = 0.4  # ratio: ... with at least this share of its boundary on the roof outline
    # ---- straightening
    node_tol_m: float = 0.3  # m: junctions closer than this are one node
    chain_min_seg_m: float = 0.9  # m: shortest segment of a free chain
    chain_crease_tol_m: float = 0.1  # m: simplify tolerance along a plane-intersection chain
    chain_crease_gap_m: float = 0.12  # m: chain vertices within this of the crease line
    chain_straight_m: float = 0.45  # m: a chain straightens end to end when it deviates less than this ...
    chain_straight_share: float = 0.08  # ... or this share of its length
    chain_axis_snap_deg: float = 15.0  # deg: staircase snap to the building axes
    chain_axis_tol_m: float = 0.4  # m: simplify tolerance of a free chain before the axis snap
    chain_free_tol_m: float = 0.08  # m: simplify tolerance of a chain against the outside
    chain_free_min_seg_m: float = 0.05  # m: shortest segment of such a chain
    chain_closed_tol_m: float = 0.15  # m: simplify tolerance of a closed chain
    chain_crease_min_seg_m: float = 0.3  # m: shortest segment of a crease chain
    chain_crease_gdiff: float = 0.05  # gradient difference above which two planes have a crease at all
    chain_collinear_deg: float = 5.0  # deg: vertices turning less than this are removed
    outline_touch_m: float = 0.04  # m: a chain end this close to the outline is on it
    owner_offset_m: float = 0.12  # m: probe distance either side of a chain to find the facets
    # ---- facets, edges
    flip_sigma: float = 0.25  # rise: a facet's own pitch fit this tight may override the 2/12 cut
    pitch_fit_tol_m: float = 0.25  # m: points within this of the plane enter the independent pitch fit
    level_change_m: float = 0.30  # m: a measured height jump at or above this is a level change
    ridge_slope: float = 0.06  # m/m: a high edge flatter than this is a ridge, steeper a hip
    seam_gdiff: float = 0.04  # gradient: coplanar facets below this share no edge
    transition_min_flat_m2: float = 8.0  # m2: a pitched/flat boundary is a transition only beside a flat facet this big ...
    transition_min_flat_share: float = 0.05  # ratio: ... and this share of the roof (else typed by the planes, or dropped)
    stub_min_len_m: float = 1.0  # m: a level change shorter than this is absorbed (clutter) ...
    stub_jump_m: float = 0.45  # m: ... as is one with a jump under this ...
    stub_len_m: float = 2.0  # m: ... and shorter than this
    canopy_above_m: float = 0.5  # m: a return this far ABOVE the surface under it is canopy, reported as tree_cover_pct (not in the verdict)
    borderline_area_share: float = 0.05  # ratio of roof area that makes a borderline facet matter
    borderline_sigma: float = 2.0  # sigmas of the pitch fit around the flat cut
    supported_step_m: float = 0.25  # m: sampling step of the supported-area estimate
    supported_reach_m: float = 0.5  # m
    chain_angle_deg: float = 7.0  # deg: edge segments chain when collinear within this
    edge_min_seg_m: float = 0.12  # m: shorter raw segments are dropped
    jump_outlier_m: float = 0.3  # m: a return this far off its own side's plane is not measured (a tree over the seam)
    jump_trim_m: float = 0.15  # m: after the fit, returns further than this (or 3 robust sigmas) from it are left out and it is refitted
    end_touch_m: float = 0.15  # m: a boundary piece with no line of its own that touches a line of the same two facets this closely takes its type
    step_along_deg: float = 30.0  # deg: a step line within this of the lower facet's fall line is sidewall (step) flashing
    step_up_cos: float = 0.3  # a step line across the lower slope with the upper roof up-slope of it (cos over this) is headwall flashing
    # ---- outputs
    fit_tol_m: float = 0.15  # m: a point fits its facet's plane within this (fit_all / fit_covered)
    # ---- objects standing on the roof (engine.objects.find_objects): chimneys, flues, lanterns; never trees
    obj_hag_m: float = 1.0  # m: a return is a candidate only above the local ground by more than this ...
    obj_reach_m: float = 3.0  # m: ... and within this of the roof outline
    obj_above_plane_m: float = 0.3  # m: ... and above the plane of the facet under it by more than this
    obj_link_min_m: float = 0.35  # m: candidates link into one blob within max(this, obj_link_spacings x mean spacing)
    obj_link_spacings: float = 1.6  # ratio of the mean return spacing (1/sqrt(density)) that still links two returns
    obj_min_points: int = 4  # pts: fewer returns is noise, not an object
    obj_pad_spacings: float = 0.15  # ratio of the mean spacing: the footprint is the rectangle of the returns grown by this (the outermost returns of a surface lie a fraction of a spacing inside its edge)
    obj_align_ratio: float = 1.6  # ratio: the footprint follows the walls unless the free minimum rectangle is this much smaller
    obj_max_aspect: float = 3.0  # ratio: long side over short side above this is a seam or ridge line, not an object (on the 160 tuning houses nine blobs 1.7-2.0 ft wide and 7-9 ft long lay along facet seams and ridges; no chimney or lantern is that thin)
    obj_min_side_m: float = 0.5  # m: a blob thinner than this is a seam or edge error of the facets (a line), not an object
    obj_edge_m: float = 0.4  # m: a blob this close to the roof edge is a parapet, wall or gutter line, not a chimney
    obj_min_area_m2: float = 0.25  # m2: a smaller footprint is dropped
    obj_tree_outside_share: float = 0.3  # ratio of a blob's returns outside the outline above which it is a tree
    obj_tree_reach_m: float = 1.5  # m: a blob this close to a tree blob is part of the same tree (its edge over the roof)
    obj_tree_h95_m: float = 4.0  # m: a blob whose 95th percentile height is above this is a tree
    obj_on_plane_m: float = 0.15  # m: a return this close to a facet plane is ON the roof (for the layered test)
    obj_layered_share: float = 0.35  # ratio: more roof returns than this inside the blob's footprint ...
    obj_layered_spread_m: float = 0.5  # m: ... with a height spread (std) above this is canopy with the roof seen through it
    obj_lantern_max_h_m: float = 0.9  # m: lower than this and at least obj_lantern_min_area_m2 wide is a lantern ...
    obj_lantern_min_area_m2: float = 2.0  # m2: the footprint is the rectangle of the returns (a roof lantern is about 2.4 m2; rooftop units on flat commercial roofs read 1.5-2.7)
    obj_chimney_max_area_m2: float = 3.0  # m2: ... at least obj_lantern_max_h_m high and at most this wide is a chimney
    obj_mislabel_area_m2: float = 3.0  # m2: a planar blob wider than this is a roof part the facets left out (mislabelled)
    obj_planar_rms_m: float = 0.08  # m: ... planar means a plane fit with an rms under this

    def __post_init__(self) -> None:
        """Canonical values (an int where a float is declared is stored as a float, so 1 and 1.0 hash alike) and sanity
        checks (finite, not negative, at least one smoothness weight)."""
        for f in fields(self):
            v = getattr(self, f.name)
            default = f.default
            if isinstance(default, bool) or isinstance(v, bool):
                continue
            if isinstance(default, float) and isinstance(v, int):
                object.__setattr__(self, f.name, float(v))
                v = float(v)
            if isinstance(v, int | float):
                if not math.isfinite(v):
                    raise ValueError(f"{f.name}: {v!r} is not finite")
                if v < 0:
                    raise ValueError(f"{f.name}: {v!r} is negative")
        if self.knn_k < 1 or self.grow_nbrs < 1 or not self.beta_schedule or min(self.beta_schedule) <= 0:
            raise ValueError("knn_k, grow_nbrs and beta_schedule must be positive")

    def stable_hash(self) -> str:
        """sha256 of the sorted fields: the result-cache and harness key."""
        blob = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()

    def replace(self, **kw: object) -> EngineParams:
        """A copy with some fields changed (unknown names raise)."""
        from dataclasses import replace

        return replace(self, **kw)


DEFAULT = EngineParams()

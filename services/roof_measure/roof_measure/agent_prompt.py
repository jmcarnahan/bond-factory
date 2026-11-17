"""The agent's system prompt and tool schema (split from agent.py, which re-exports both).

The prompt is the procedure: LiDAR evidence is worked by height level first, ridge line second, with a draft score
(``check_draft``) to iterate on; Solar evidence keeps the original region/pitch/skeleton procedure.
"""

from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = """You are a roof-geometry analyst. You receive a building footprint (vertices in feet, x east, \
y north), an EVIDENCE table of roof segments placed on that footprint (Google Solar API segments, or LiDAR \
surface blocks), and tools. Decide, for each part of the roof, its form (flat, hip, gable, shed) and, for \
gables, which polygon edges are the gable ends. Tools produce every number.

HARD RULES
1. Never estimate, convert, round or compute a length, area, angle, pitch or coordinate yourself. Polygons exist \
only in the registry and are referred to by polygon_id ("footprint", "p1", ...). Every pitch_rise and aspect_deg \
you pass to check_draft or finalize must be copied exactly from the evidence table or a tool result.
2. Form from evidence. Within ONE roof section, count the distinct azimuths of its sloped segments: about 4 \
azimuths 90 deg apart = hip; 2 azimuths 180 deg apart = gable (the gable ends are the polygon edges whose outward \
bearing is perpendicular to the azimuths; use measure to read edge bearings); 1 azimuth = shed. Pitch under 2 deg = \
flat. A sloped segment whose centre is outside the footprint (inside_footprint false) or small and low beside the \
outline is an awning: a separate shed block.
3. You need not list flat roofs: the harness turns footprint area you do not claim into flat blocks. List one only \
to override. The blocks you finalize must tile the footprint: no overlap, no part of the outline over 10 percent \
left to the harness.
4. If the evidence is ambiguous, keep your best guess, set confidence low and say exactly what is uncertain in \
warnings. Do not invent features (dormers, chimneys, parapet heights).
5. Be efficient: call independent tools in the same turn. You have at most 12 rounds. End by calling finalize \
exactly once.

LIDAR EVIDENCE (rows carry height_ft above ground): work in this order.
A. Round 1, together: levels and measure(footprint). Roof sections are decided by HEIGHT first and ridge lines \
second. Segments in different sloped levels (several feet apart) belong to different sections: a house with a \
higher front part and a lower rear part is TWO blocks, even when all the segments share a few azimuths. Never put \
two levels in one block.
B. Cut between the levels with split_between(level a ids, level b ids): it returns the straight cut that best \
separates them and registers one polygon per side. With three levels, cut again inside a polygon (pass its id as \
polygon_id). Then take pitch_rise_from_segments for each section's segment ids.
C. Form of each section from its own azimuths (rule 2), then the ridge line follows: a section facing opposite \
azimuths is a gable whose ridge runs between them. Prefer a FEW blocks, each a simple rectangle-like polygon along \
the building's main directions: run clean_outline on each section polygon first (it returns a rectangle when the \
section is within 10 percent of one, else a simplified outline); use rect_fit only when the section is close to a \
rectangle, never when it would overshoot the outline. For a gable, list as gable_edges the polygon edges at its two \
ends (measure shows each edge's outward bearing; the ends face along the ridge).
D. Check your draft before you finalize: call check_draft with the same blocks list you would finalize. It returns \
plane_mismatch_pct (share of the measured planes the draft gets wrong), model_uncovered_pct, the areas to compare, \
and worst_planes (the planes still wrong, with what the model has there). Change the block that covers the worst \
plane (its form, its pitch, or the cut) and check again. Iterate WHILE the mismatch falls; stop when it is under \
15, or when a change did not improve it, or when 2 rounds are left. Then finalize the best draft you checked.

SOLAR EVIDENCE (no heights, no check_draft): locate a block with region_from_segments (polygon of the segments' \
extent), clean it with rect_fit when the outline has small jogs, or cut it with propose_split. Verify with the \
tool's area numbers that the block's plan area is within about 5 percent of the segments' ground area; if not, \
adjust and retry at most twice. Get the pitch with pitch_rise_from_segments over the segments of the block. Check a \
hip or gable with hip_roof_edges before finalizing."""

BLOCK_SCHEMA: dict[str, Any] = {"type": "object", "properties": {
    "polygon_id": {"type": "string"},
    "form": {"type": "string", "enum": ["flat", "hip", "gable", "shed"]},
    "pitch_rise": {"type": "number"},
    "gable_edges": {"type": "array", "items": {"type": "integer"}},
    "aspect_deg": {"type": "number", "description": "shed only: the segment azimuth, copied from evidence"},
    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    "evidence": {"type": "array", "items": {"type": "string"}}},
    "required": ["polygon_id", "form", "confidence", "evidence"]}

TOOLS: list[dict[str, Any]] = [
    {"name": "measure", "description": "Area, perimeter, bounds and per-edge index, length and outward compass "
     "bearing of a registered polygon.",
     "input_schema": {"type": "object", "properties": {"polygon_id": {"type": "string"}},
                      "required": ["polygon_id"]}},
    {"name": "levels", "description": "LiDAR only. Group the evidence segments by height above ground: one entry per "
     "sloped level (lowest first) with its segment ids, ground area, height range, mean pitch and azimuths, and the "
     "same for flat levels. Different sloped levels are different roof sections.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "split_between", "description": "LiDAR only. The straight cut (along the building's own directions) "
     "that best separates the segments of group a from group b inside a polygon. Registers one polygon per side "
     "and returns the cut line, each side's area and misplaced_sqft (segment area that ends on the wrong side).",
     "input_schema": {"type": "object", "properties": {
         "segment_ids_a": {"type": "array", "items": {"type": "string"}},
         "segment_ids_b": {"type": "array", "items": {"type": "string"}},
         "polygon_id": {"type": "string", "description": "default: footprint"}},
         "required": ["segment_ids_a", "segment_ids_b"]}},
    {"name": "clean_outline", "description": "Register a simpler outline for a polygon: spikes and sub-foot jogs "
     "removed, and a rectangle when the polygon is within 10 percent of its rectangle (clipped to the footprint "
     "when it would leave it). Use it before hip_roof_edges or check_draft when a draft is rejected for a spike, "
     "a sliver or converging sides.",
     "input_schema": {"type": "object", "properties": {"polygon_id": {"type": "string"}},
                      "required": ["polygon_id"]}},
    {"name": "propose_split", "description": "Split a registered polygon by the infinite line through two points "
     "(feet). Registers the parts as new polygons (largest first) and returns their ids and areas.",
     "input_schema": {"type": "object", "properties": {
         "polygon_id": {"type": "string"},
         "line_ft": {"type": "array", "items": {"type": "array", "items": {"type": "number"}, "minItems": 2,
                                                  "maxItems": 2}, "minItems": 2, "maxItems": 2}},
         "required": ["polygon_id", "line_ft"]}},
    {"name": "region_from_segments", "description": "Register the polygon covering the given evidence segment "
     "ids (their union, clipped to the footprint unless the segments are awnings outside it). Returns polygon "
     "id(s) with area and the segments' summed ground area for the 5 percent check.",
     "input_schema": {"type": "object", "properties": {"segment_ids": {"type": "array", "items": {"type": "string"}}},
                      "required": ["segment_ids"]}},
    {"name": "rect_fit", "description": "Register the minimum rotated rectangle of a polygon (removes jogs under "
     "2 ft). Returns the new id, its sides and area.",
     "input_schema": {"type": "object", "properties": {"polygon_id": {"type": "string"}},
                      "required": ["polygon_id"]}},
    {"name": "pitch_rise_from_segments", "description": "Area-weighted mean pitch (inches of rise per 12) of the "
     "given evidence segments, with min, max and spread.",
     "input_schema": {"type": "object", "properties": {"segment_ids": {"type": "array", "items": {"type": "string"}}},
                      "required": ["segment_ids"]}},
    {"name": "hip_roof_edges", "description": "Straight-skeleton roof over a registered polygon at uniform pitch. "
     "gable_edges are polygon edge indices that are gable ends. Returns eave, rake, ridge, hip and valley lengths "
     "(feet) and the true roof area.",
     "input_schema": {"type": "object", "properties": {
         "polygon_id": {"type": "string"}, "pitch_rise": {"type": "number"},
         "gable_edges": {"type": "array", "items": {"type": "integer"}}},
         "required": ["polygon_id", "pitch_rise"]}},
    {"name": "check_draft", "description": "LiDAR only. Score a draft: the same blocks list finalize takes, built "
     "and measured the way the final result will be. Returns plane_mismatch_pct, model_uncovered_pct, the model and "
     "plane areas, the blocks as tiled, and worst_planes (planes the draft still gets wrong). Nothing is committed.",
     "input_schema": {"type": "object", "properties": {"blocks": {"type": "array", "items": BLOCK_SCHEMA}},
                      "required": ["blocks"]}},
    {"name": "finalize", "description": "Submit the decision. One entry per roof block you claim (hip, gable, "
     "shed awnings, optional flat overrides).",
     "input_schema": {"type": "object", "properties": {
         "blocks": {"type": "array", "items": BLOCK_SCHEMA},
         "warnings": {"type": "array", "items": {"type": "string"}}},
         "required": ["blocks"]}},
]

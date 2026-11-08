# Consistency checks, site 1 (Roofr pages 3 and 4)

SAYS = printed on the pages. INFERS = my reading or calculation. Pixel lengths use a 6.12 px/ft scale fitted to the flat areas, so they carry about 3 to 5 percent error.

## (a) Facet areas versus totals

| Item | Arithmetic | Printed total | Diff | Verdict |
|---|---|---|---|---|
| All 11 facets | 300+169+190+289 = 948; 82+87+86 = 255; 151+2121+1013+922 = 4207; 948+255+4207 = 5410 | 5405 | +5 (0.09 %) | PASS, marginal |
| Pitched | 948 + 255 = 1203 | 1200 | +3 | PASS, marginal |
| Flat | 151+2121+1013+922 = 4207 | 4205 | +2 | PASS, marginal |
| Totals among themselves | 1200 + 4205 = 5405 | 5405 | 0 | PASS |
| Predominant pitch area | 0/12 area 4205 = flat total; unspecified 0 | | | PASS |

Rounding bound: a value rounded to the nearest sq ft is off by at most 0.5, so 11 facets can drift 5.5, 7 facets 3.5, 4 facets 2.0. All three diffs are positive and sit at that bound. INFERS: either every facet was rounded up, or I misread a digit by 1 to 2 (289 and 2,121 are the least sure). Probability that all eleven drift the same way under honest rounding is very low, so treat facet labels as possibly rounded up.

## (b) What makes the 1200 sq ft pitched area

SAYS: handwritten "Tile" on the hip section and under each of the three awnings, "Re stack" beside the pitched line.
INFERS: pitched = 4 hip facets (948) + 3 awnings (255) = 1203, versus 1200 printed. PASS (same marginal rounding as (a)). The awnings are the only other non-flat facets, so no other combination reaches 1200 (948 alone is 252 short, 948+82+87 = 1117, 948+82+86 = 1116).
Awning slope: reconstructed awning plan areas are 81.2, 81.6, 81.6 sq ft against printed 82, 87, 86, a factor of 1.01 to 1.07, so the awnings are shallow (about 0/12 to 4/12). Low confidence.

## (c) Hip pitch

Geometry used. For a rectangular hip with width W, length L and equal pitch p (= rise/12):
- ridge length R = L - W
- every hip has plan length W/sqrt(2), true length (W/sqrt(2)) * sqrt(1 + p^2/2)
- area scales by sqrt(1 + p^2)

Checks:
1. Ridge. Printed 35 x 26 gives R = 35 - 26 = 9.0 ft. Roofr says 7.75 ft. With rounded-up labels L is in (34,35] and W in (25,26], so R should be in (8,10). 7.75 is 0.25 ft outside. MARGINAL FAIL, meaning the hip is not a perfect equal-pitch rectangle. Pixels agree: the south eave rises toward the east, west side about 26.5 ft and east side about 25.5 ft (this is why the SE hip prints 18, not 20). With W averaged 26 and L about 34.2, R = 8.2, close.
2. Area method (hip facets 948 sq ft, plus about 28 sq ft for the two openings on the west end):

| plan used | slope factor | rise/12 |
|---|---|---|
| 35 x 26 = 910, no add-back | 948/910 = 1.042 | 3.5 |
| 35 x 26 = 910, add-back 28 | 976/910 = 1.073 | 4.7 |
| 34.2 x 26 = 889, add-back | 976/889 = 1.098 | 5.4 |
| 34.2 x 25.5 = 872, add-back | 976/872 = 1.119 | 6.0 |
| reconstructed polygon at global scale 6.12 (plan 805) | 1.18 | 7.4 |
| reconstructed polygon at hip-local scale 5.83 (plan 905) | 1.05 | 3.9 |

The last two rows show the photo cannot fix the hip plan area to better than 5 percent, which swings the pitch from 4 to 7. Do not use the photo for this; use rounded printed dimensions.
3. East triangle (plan W^2/4, no opening on it): W = 26 gives 169 sq ft plan, 190/169 = 1.124, rise 6.2/12. W = 25.5 gives 7.3/12. The north facet (trapezoid) plan area from pixels is about 291 against 300, which would say only 1.03 (about 2/12), so facets disagree. INFERS: facet-by-facet area is unreliable.
4. Hip lengths. Printed 20, 20, 20, 18 (each rounded up); legend total 76 ft 2 in = 76.17.
   - W = 26: plan hip 18.38. Three hips must print 20, so true > 19, which needs factor > 1.034, p > 0.37 (4.5/12). At 4/12 the true hip is 18.89 and would print 19, so 4/12 is ruled out.
   - Fourth hip is in (17,18], so the other three average (76.17 - 18) / 3 = 19.39 up to (76.17 - 17) / 3 = 19.72. That gives p = 0.476 to 0.544, rise 5.7 to 6.5/12 (W = 26), or 6.7 to 7.5/12 (W = 25.5).
   - If all four hips were equal at 19.04: p = 0.38, 4.6/12.
   - Reference: at 5/12 four hips sum 76.7, at 6/12 78.0, at 4/12 75.6.

VERDICT: the hip pitch is about 5/12 to 6/12 (best single value 5/12, plausible range 4.5 to 6.5). It is not on the report and cannot be pinned to one standard pitch from these numbers. 4/12 is excluded only if the hip is 26 ft wide.

## (d) Eaves 209 ft 8 in (209.67)

Teal edges in the diagram, printed labels where they exist:

| Edge | ft |
|---|---|
| hip north 35 | 35 |
| hip west 13 + 12 (a short hidden piece may exist) | 25 |
| hip east | 26 |
| hip south west piece | 12 |
| hip south 22 (faces Flat 151) | 22 |
| three awning bottoms (82/11, 87/11, 86/11 = 7.5, 7.9, 7.8, printed up to 8) | 24 |
| small lobe top | 11 |
| NE block west teal edge | 11 |
| SE block west teal edge | 11 |
| divider NE/SE | 31 |
| Sum | 208 |

Printed 209.67, diff +1.67 (0.8 %), explained by the possible hidden west piece. PASS. Pixel-measured sum is 204 (diff -2.7 %), also within error. INFERS: the lead's guess (hip perimeter 122 + awnings) is right but incomplete. Hip perimeter is 120 to 122, awnings 24, and the other 65 ft are internal flat-to-flat boundaries that Roofr colours as eaves, not parapet. The label 22 beside the junction (see length_report.json) is NOT an extra eave, since adding it would give 230.

## (e) Parapet wall 423 ft 10 in (423.83)

Orange edges, from printed labels plus pixel-measured unlabelled pieces:

| Group | ft |
|---|---|
| west wall (151 left side plus SW block, unlabelled) 30.1; 151 right side 7.8; 151 bottom (label 22) 22.4 | 60.3 |
| south wall 30 | 30 |
| awning 1 left 10.5, top 7.4, right upper 4.4 | 22.3 |
| 20 | 20 |
| awning 2 left upper 4.4, top 7.7, steps 1.1 + 4.7 | 17.9 |
| 15 + step 2.6 | 17.6 |
| lobe west 8.5 + south 11 | 19.1 |
| awning 3 top 7.7, right 10.6, left upper 4.9 | 23.2 |
| SE: 33 + east 11 + 11 (+ hidden) + top-right 9.2 | 33.8 + 24.6 + 9.2 = 67.6 |
| NE: top 35 + east 12 + 12 + west 21 + steps 3.4 + 7.2 | 34.8 + 23.4 + 19.9 + 10.6 = 88.7 |
| middle north wall: 11, 16, 30, 12 plus steps 2.1, 1.8, 4.1 | 9.7 + 15.2 + 28.8 + 12.3 + 8.0 = 74.0 |
| Total (sum of rows) | about 440 |

Printed 423.83, measured about 440, diff +3.8 %. PASS (loose). Printed labels sum to only 302 for the 16 flat-roof edges plus 33 for awning sides, so about 100 ft of the parapet total sits on unlabelled edges (steps, awning tops, 151 sides). The 12 ft wall of the middle strip east of the hip, and the three awning tops, are orange. INFERS: step flashing (50 ft, brown dots) may be drawn on top of some orange edges, which would pull the parapet total down toward 424.

## (f) Wall flashing 344 ft 5 in (344.42) and double counting

Evidence: blue dashed lines appear only as the 16 dashed rectangles (14 full plus 3 small attached pieces, minus the one brown one). Their measured perimeters sum to about 232 ft (estimated from 3 to 4.6 ft boxes, plan area about 222 sq ft total).
- 232 vs 344: 112 ft (33 %) not visible as blue.
- If wall flashing were the inner side of all parapets it would be at least 440 ft, more than 344, and it would be drawn along the outer outline. It is not. So full double counting of parapet and wall flashing is NOT supported.
- Candidate for the missing 112 ft: the internal flat-to-flat teal edges (22.4 + 10.6 + 10.3 + 11.1 + 31.2 = 85.6 ft) plus part of the hip-to-Flat-151 junction. Those are where a flat roof meets a higher wall. Then Roofr would count the edge in both eaves and wall flashing, which the drawing cannot show because one colour wins. This is a hypothesis; I cannot confirm it from the pages.
- Also the step flashing 50 ft (brown dots): the one brown dashed rectangle is only about 11.6 ft. About 38 ft are not visible.

VERDICT: UNRESOLVED. Mostly the curb outlines of the 17 excluded openings, plus roughly 110 ft that is not visible as blue.

## (g) Excluded openings and areas

Reconstructed flat plan area at 6.12 px/ft = 4406 sq ft. Openings on flat roofs total 203 sq ft. 4406 - 203 = 4203 against printed 4205. PASS, but the 6.12 scale was fitted to the flat total, so this is only a partial test (the 203 is independent). Total reconstructed plan footprint 5474 sq ft including openings; bounding box 141.1 ft east-west by 57.1 ft north-south.

## (h) Label check (transcription quality)

I measured 34 labelled edges in pixels and compared with printed labels. 29 are within 1.2 ft; the outliers are hip bottom-west 12 (10.3 measured), the three SE-block 11s (12.5 measured), and awning 1/2 sides. This supports the transcription. PASS.

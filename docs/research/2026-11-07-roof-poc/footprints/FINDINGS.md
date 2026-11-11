# Footprints: site 1 (address in local/sites.json, not tracked)

Scratch root S = (session scratch, not in repo)
Scripts: S/scripts/{la_query2,la_bldg,osm,msft,analyze}.py. All metrics in EPSG:2229 (CA State Plane V, ftUS), computed with shapely/pyproj.

## FACTS

### Geocode
US Census onelineaddress (Public_AR_Current) -> site 1 lon/lat (real values in local/test-data/, untracked) (S/data/census_geocode.json).
The point is street-interpolated: it is outside the parcel polygon (distance withheld, real site). A point-in-polygon query returns zero parcels; a 60 m search radius is needed (or geocode to the rooftop first).

### LA County (all on-demand ArcGIS REST, no key, 0.14-0.23 s per query, 3 runs each)
- Parcels: https://public.gis.lacounty.gov/public/rest/services/LACounty_Cache/LACounty_Parcel/MapServer/0 (query supported; max 1000 records).
  Params used: geometry=<lon>,<lat>&geometryType=esriGeometryPoint&inSR=4326&spatialRel=esriSpatialRelIntersects&distance=60&units=esriSRUnit_Meter&outFields=*&outSR=4326&f=geojson
  Parcel for the address: AIN (assessor parcel id, withheld), site 1 address, area, vertex count and bounding box withheld (real site). File: S/data/lacounty/parcel_<AIN>.geojson (all 34 parcels in 60 m: parcels_60m.geojson).
  Parcel attributes include UseCode, DesignType1, YearBuilt1, SQFTmain1, Units, Bedrooms, roll values. Several AINs (site 1 and neighbouring addresses) share one identical polygon: it is a multi-unit condo/townhome lot (figures withheld, real site).
- Building outlines (Countywide Building Outlines, LARIAC), layers on https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/ :
  - 2014 (LARIAC4): Countywide_Building_Outlines/FeatureServer/1
  - 2017 (LARIAC5): Countywide_Building_Outlines_(2017)/FeatureServer/0
  - 2020 (LARIAC6): Countywide_Building_Outlines_(2020)/FeatureServer/0 (also MapServer .../LACounty_Dynamic/LARIAC_Buildings_2020/MapServer/0 on public.gis.lacounty.gov)
  - older DPW layer: https://dpw.gis.lacounty.gov/dpw/rest/services/buildingfootprints/MapServer/0 (same fields, minScale 9000)
  Query by polygon (parcel ring) POST with geometryType=esriGeometryPolygon returns exactly 1 building in each vintage. Files S/data/lacounty/bldg{2014,2017,2020}_{parcel,pt60m}.geojson.
  Attributes (2020): CODE, BLD_ID, HEIGHT (ft), ELEV (ft), SOURCE, DATE_, STATUS, OLD_BLD_ID, AREA (sf). The 2014 layer is also pre-joined with parcel/assessor fields. NO roof type, NO stories, NO pitch.
  Values for this building (withheld, real site) are identical in all 3 vintages, with SOURCE LARIAC2 and a 2008 date. => the geometry is from the 2008 stereo capture and was never re-digitised.
  Layer description (hub): outlines captured from stereo imagery (LARIAC2, 2008), updated in 2014/2017/2020; "over 3,000,000" buildings; includes height and area.
- HEIGHT interpretation (INFERENCE): the HEIGHT value (withheld) is probably max height above ground derived from stereo/LiDAR; it suggests 2-3 stories but says nothing on roof form. ELEV looks like ground elevation (it matches the OSM ele tag).

### OpenStreetMap (Overpass, https://overpass-api.de/api/interpreter, around:40 of the point)
Script S/scripts/osm.py; raw S/data/osm/overpass_raw.json; GeoJSON S/data/osm/buildings_40m.geojson (7 buildings).
Our building: way <osm-id, withheld>, tags building=house, building:units=1, ele, height, start_date (values withheld), lacounty:ain=<withheld>, lacounty:bld_id=<withheld>. No roof:shape, no building:levels.
=> it is the LA County import (same BLD_ID); same vertex count, geometry identical to LARIAC to <0.1 sf. It is NOT independent evidence. Neighbour way <osm-id, withheld> (the neighbouring parcel) does have roof:shape=hipped, so some roof tags exist locally but not here.
Overpass behaviour: first request 502 "at capacity", 2 mirrors timed out, retry on main succeeded.

### Microsoft footprints
Global ML Building Footprints, quadkey (zoom 9) 023012311, US file, release 2026-02-03 (Vexcel imagery 2021-2025): https://minedbuildings.z5.web.core.windows.net/global-buildings/2026-02-03/global-buildings.geojsonl/RegionName=UnitedStates/quadkey=023012311/part-00015-4feead82-d499-422b-94cb-c036c212127a.c000.csv.gz (170 MB gz, 1,679,325 features, GeoJSON lines, props: height, confidence). Located via dataset-links.csv (S/data/msft/dataset-links.csv).
Footprint on parcel: height 6.04 m (19.8 ft), confidence 0.988, 16 vertices. 27 other buildings within ~55 m saved: S/data/msft/msft_near.geojson.
Note: README now points to a newer dataset-links.csv (2026-08-13, adds Vexcel 2025 data); I used the 2026-02-03 link from the CSV I downloaded. A newer part file may differ.

### Comparison table (EPSG:2229)
| Source | Area sf | Perimeter ft | Vertices | BBox ft | Min-rot-rect ft | Height |
|---|---|---|---|---|---|---|
| Report (roof) | withheld | withheld (not a footprint perimeter) | n/a | withheld | n/a | n/a |
| LA 2014/2017/2020 | withheld (real site) | withheld | withheld | withheld | withheld | withheld |
| OSM way <osm-id, withheld> | same as LA to within 1 sf | withheld | withheld | withheld | withheld | withheld |
| MSFT | about 7% above the report | withheld | far fewer than LA | withheld | withheld | lower than LA |
| Parcel | withheld | withheld | withheld | withheld | | |

Area ratios vs report: LA/OSM about 1.28 (a gap of roughly a fifth of the outline), MSFT about 1.07 (figures partly withheld). A hip roof's sloped area exceeds its ground area, so the report's ground-equivalent is somewhat below its printed total (INFERENCE), widening the gap to MSFT to ~10% and to LA to ~30%.

### Hip section / awnings
- All sources give ONE polygon for the whole building. The hipped 35x26 block and the 11-12 ft awnings are NOT separate polygons in any source (FACT, see Figure: footprints.png (local only, not tracked: local/research-images/footprints.png; it shows real coordinates)).
- LA/OSM polygon has many 1.6-3.6 ft jogs (vertex count and edge lengths withheld, real site) and three long edges; the small steps at the south edge are consistent with awning/bay offsets but cannot be proven (INFERENCE).
- MSFT is a squarer, simplified version: it drops the jogs and shifts the west and east ends inward by several feet (visible in the PNG).

## INFERENCES / CAVEATS
- Best match to the report area: MSFT (+7%). Best match to detail/shape (U-shape with notches, matches "L/U-shaped"): LARIAC (stereo-derived, 2008). LARIAC is 28% larger than the report; likely because it traces roof/eave edges of the whole 5-unit complex including balconies, overhangs or courtyard-side structures the report excludes, or because the report is a different/partial scope. Unproven.
- ADDRESS-SCOPE WARNING: assessor data say site 1 is a multi-unit residential lot (figures withheld, real site). A flat-roof building with parapets and long tile eaves is plausible for stacked townhomes, but the lead should confirm the report covers the whole parcel building.
- Vertex count is not an accuracy indicator: LARIAC's notches may be real detail; MSFT's 16 vertices are a regularised guess.

## GENERALISATION
| Source | Vintage | Access | Licence |
|---|---|---|---|
| LA County parcels | current assessor roll (Roll_Year in 2014 join: 2012; layer live) | on-demand REST, no key, ~0.2 s | County Terms of Use (eGIS Hub terms page; licenseInfo field = "informational purposes... County reserves the right to change, restrict, or discontinue access"). Not CC0/ODbL. Commercial use: terms page not machine-readable (JS app), NOT verified. Bulk alternative: File Geodatabase download https://apps.gis.lacounty.gov/static/hub/lariac_documents/LARIAC6/LARIAC6_Buildings_2020.gdb.zip |
| LARIAC buildings | geometry 2008 stereo, layers re-published 2014/2017/2020 (this building unchanged) | on-demand REST, no key, ~0.2 s; maxRecordCount 2000; also bulk gdb | same County terms (see above) |
| OSM | continuously edited; this way imported from LARIAC | Overpass on-demand but rate-limited, one 502 seen; not production-grade without own instance/extract | ODbL (attribution, share-alike on derived databases) |
| Microsoft Global ML | Vexcel 2021-2025 imagery, release 2026-02-03 | bulk tile only (170 MB gz for this tile, no point API); needs your own index | CDLA Permissive 2.0 per GlobalMLBuildingFootprints README (commercial OK, attribution not required); legacy USBuildingFootprints is ODbL |

HEIGHT/ELEV: LARIAC HEIGHT (value withheld, real site) is present and usable for a story count and approximate roof height, but only a single max-height number, not parapet vs ridge, and no roof type.

## COULD NOT DETERMINE
- Whether the County Terms of Use permit commercial redistribution/derivative use (page not retrievable as text).
- Whether the report's total covers the full building or a subset; no way to see the report from here.
- Which edges in the LARIAC polygon are the hip block or awnings.
- Whether the newer Microsoft part file (2026-08-13 links) changes this footprint.
- Parcel layer vintage (SpatialChangeDate attribute is null).

## VERDICT AND NEXT PROBES
Use LARIAC 2020 (LA County Countywide Building Outlines) as the POC footprint: free, keyless, ~0.2 s, fixed schema, plus HEIGHT, and the most detailed outline; reconcile with Microsoft as a sanity check for area. Geocode with the parcel layer (60 m radius, pick nearest/matching SitusFullAddress) because Census points land in the street. OSM adds nothing here (copy of LARIAC). No source separates the hip section, so facet splitting must come from LiDAR/roof-plane work.
Next probes: (1) overlay the footprint on the report diagram (rotate/scale to the 160x57 ft bbox) to see which edges match parapet/eaves; (2) read LA County eGIS terms in a browser; (3) check LARIAC6 2020 DSM/LiDAR coverage for the roof planes; (4) compare against the 2025 Vexcel-based Microsoft tile; (5) subtract the five 1990 condo footprints if the report is per-unit.

# Roof module v1 spikes (2026-11-11)

Rule: no coordinates, addresses or building ids in this file, ever. The spike script
(`services/roof_measure/tools/spike_national.py`) keeps its sites in the gitignored `local/spike-sites.json`.
Each site is one OpenStreetMap `building=house` way picked within 1–3 km of a generic suburban seed.

## 1. National hit rate

Success criterion: at least 4 of 5 non-LA states measured in under 90 s (`lidar_skeleton`, no LLM agent).
A sixth site in Los Angeles County is the parcel-layer control and is not counted.

### Baseline, pipeline before this change (2026-11-11 08:08–08:36)

| state | footprint_source | 3dep_project | density pts/m² | seconds | outcome |
|---|---|---|---|---|---|
| TX | osm | n/a | 11.7 | 35.5 | failed: no roof block survived segmentation |
| FL | n/a | n/a | n/a | 0 | skipped: the picked house has no address tag and the old pipeline took no coordinates |
| NY | n/a | n/a | n/a | 0 | pick failed (Overpass) |
| CO | osm | USGS_LPC_CO_SoPlatteRiver_Lot2a_2013_LAS_2015 | 7.7 | 43.6 | failed: below the 8 pts/m² floor |
| WA | n/a | n/a | n/a | 90 | timeout inside the footprint stage |

0 of 5. Findings that drove the design: two of the three configured Overpass mirrors did not answer at all, the
third returned 502 or answered in 30–40 s, and the chain tried them one after another with a 70 s timeout each;
the 8 pts/m² density floor rejected a usable Colorado cloud.

### After this change (2026-11-11 09:05, run 4; the chain of D17/D18)

| state | footprint_source | 3dep_project | density pts/m² | seconds | outcome |
|---|---|---|---|---|---|
| TX | osm | n/a | 11.7 | 35.2 | failed `measurement_failed`: no roof block survived segmentation |
| FL | osm | FL_Peninsular_FDEM_Orange_2018 | 26.2 | 30.4 | done (footprint 27.0 s, lidar 3.0 s) |
| NY | osm | NY_FEMAR2_Central_3_2018 | 13.0 | 34.5 | done (footprint 28.3 s, lidar 5.3 s) |
| CO | lidar_hull | USGS_LPC_CO_SoPlatteRiver_Lot2a_2013_LAS_2015 | 6.3 | 1.0 | done (cached tiles; hull fallback) |
| WA | osm | n/a | n/a | 38.3 | failed `measurement_failed`: the model oracle rejected a sliver facet ("spike 6.6° at a vertex"); the first run failed earlier because an unreachable Overpass stopped the chain before the hull (fixed) |
| CA (control) | lariac | CA_LosAngeles_1_B23 | 10.4 | 4.7 | done (parcel layer; not counted) |

3 of 5 under 90 s (target 4). The Overpass step alone costs 27–38 s per site when the public instances answer.
The two misses are geometry robustness in the existing segmentation and model code, not the new chain: the Texas
roof fails in the blocks stage despite adequate density (small or oddly segmented roof; `lidar_agent` is the
manual retry path) and the Washington roof produced a sliver facet the model oracle rejects. A static national footprint source would remove the Overpass dependency; not in this round.

## 2. Docker image size and cold start

Measured 2026-11-11 on the Mac mini with colima (aarch64 VM) running the `linux/amd64` image under emulation, so
timings are upper bounds; Railway's native cold start is unmeasured until the first deploy.

| metric | value |
|---|---|
| image size | 270 MB (`python:3.12-slim` + libgomp1 + `uv sync --frozen --no-dev`) |
| cold start to first `/healthz` 200 | 63 s on the very first run (emulation warm-up), 5–7 s afterwards |
| real pipeline job from the blocks fixture, inside the container | 19.5 s queued → done |
| cache hit on a repeat `POST` | immediate `202 {status: "done"}` |
| auth | 401 for a missing and for a wrong token; refuses to start with `ROOF_MEASURE_AUTH=off` on a non-loopback host |

Findings: uvicorn bound to `::` is IPv6-only, so a local `docker run -p` needs `ROOF_MEASURE_HOST=0.0.0.0`
(Railway is IPv6, `::` stays the default); the installed package needs `ROOF_MEASURE_FIXTURES=/app/fixtures`
(set in the Dockerfile); Railway volumes mount root-owned, so `RAILWAY_RUN_UID=0` is documented as required.

## 3. Verifier cost and latency

Measured 2026-11-11 with `tools/spike_verifier.py --fixtures` against the live API (`claude-sonnet-5-5`,
`thinking: between_tools`, effort low, `max_tokens` 2000, 6-round cap).

| fixture | verdict | rounds | input tokens | output tokens | USD | seconds |
|---|---|---|---|---|---|---|
| synthetic_hip | pass | 2 | 4,759 | 374 | 0.0133 | 4.2 |
| synthetic_gable | pass | 2 | 4,590 | 394 | 0.0131 | 4.2 |
| synthetic_flat_parapet | pass | 2 | 4,027 | 493 | 0.0130 | 5.5 |
| synthetic_hip_zigzag | adjusted | 2 | 4,753 | 346 | 0.0130 | 4.5 |

About $0.013 and 4–6 s per roof: the $0.05 and 30 s targets hold with a 4× cost margin and 6× time margin. The
zigzag eave (seven segments) was merged into one 35.0 ft line and the verdict came back `adjusted` as designed.

## 4. Library install in python:3.12.9-slim (linux/amd64)

Method: `python:3.12.9-slim` built with `--platform linux/amd64`; `apt-get install git`; no libgomp1;
`pip install "roof-measure @ git+https://github.com/jmcarnahan/bond-factory.git@<phase-1 sha>#subdirectory=services/roof_measure"`;
then `measure()` on the blocks fixture with `isolate=True` and `verify=False`.

| metric | value |
|---|---|
| install seconds | 69.0 s (second run 109.9 s; varies with network), plus 14.2 s for apt git |
| site-packages size | 366 MB, 37 packages |
| image size | 843 MB for the committed spike container (base 189 MB + site-packages 366 MB + about 290 MB of apt git, pip cache and clone residue that a clean Dockerfile build would not keep); a clean core install is about 555 MB |
| cold `import roof_measure.pipeline`, seconds | 1.8 s (second run 2.1 s); `import roof_measure` alone 0.1 s |
| `measure()` seconds, blocks fixture, `isolate=True` | 11.0 s first call, 10.1 s and 10.2 s after (second run 9.3, 10.4, 7.4 s); `isolate=False` 6.1 s |
| child peak RSS | 268.8 MB (second run 271.0 MB) |

The container ran on an Apple-silicon Mac under linux/amd64 emulation (colima), which inflates CPU-bound times several-fold: the `import`, `measure()` and in-process seconds are upper bounds, not what a native amd64 host sees (the same fixture run takes 1.0 s isolated and 0.7 s in-process on the Mac natively). Sizes and the install/package facts are unaffected.

The compas_cgal wheel needs no libgomp1 (verified 2026-11-11 on bookworm), and there is no linux aarch64 wheel.

Run on 2026-11-11 against base `python:3.12.9-slim` (Debian 12.10, digest
`sha256:48a11b7ba705fd53bf15248d1f94d36c39549903c5d59edcfa2f3f84126e7b44`), twice; the tables show the first run and
name the second where it differs.

- **Transport.** pip's `git+file` form from a read-only bind mount of the checkout at 6abcc03, with
  `#subdirectory=services/roof_measure`. It clones, builds with PEP 517 and installs like the https form. Only the
  transport differs. The https form is checked after the branch is pushed. git needed `safe.directory` for the mount.
- **git.** `apt-get install --no-install-recommends git` took 14.2 s (second run 22.6 s). libgomp1 was not
  installed (`ldconfig` finds none) and `compas_cgal.straight_skeleton_2` imported.
- **Extras absent.** `matplotlib` and `fastapi` fail to import after the core install.
- **Packages.** 37 in the core install.
- **Largest site-packages directories (MB).** scipy 109, numpy 43, anthropic 32, scipy.libs 30, numpy.libs 27,
  pyproj 22, networkx 19, compas 15.
- **Driver.** The installed package, not the source tree, ran `measure()` on the blocks fixture with
  `method="lidar_skeleton"`, `verify=False`, three times with `isolate=True` and once with `isolate=False`. The
  envelope contract was `bond.roof_model/0.2` and all four areas were equal. The import timings are two separate
  processes, so both are cold with respect to the module cache.
- **anthropic 1.x.** In a Mac venv with `anthropic==1.14.0`, the verifier, seam, errors and library tests passed
  (104 passed).

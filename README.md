# Christchurch Residential Development Suitability Screening

**Indicative parcel-level screening for residential development opportunity in inner south-west Christchurch, New Zealand.**

A reproducible GIS demonstration that combines open Council, LINZ and Stats NZ data to (1) classify parcels by current building status, (2) map environmental and geotechnical constraints, and (3) score residential zones on infrastructure proximity, parcel size, terrain and flood exposure. The output is a parcel table and three maps intended to prioritise which parcels deserve further planning, engineering and consent assessment — not to confirm development feasibility.

---

## Study area

Nine inner south-west suburbs under NZTM 2000 (EPSG:2193):

**Wigram, Broken Run, Aidanfield, Hoon Hay, Oaklands, Halswell, Hillmorton, Spreydon, Sockburn South**

Total extent ≈ 12 km × 6 km. 20,984 parcels zoned Residential in the Christchurch District Plan are scored.

---

## Data sources

| Theme | Source | Layer / dataset | Licence |
|---|---|---|---|
| Parcels | LINZ | NZ Primary Parcels (layer 50772) | CC BY 4.0 |
| Building footprints | LINZ | NZ Building Outlines (layer 101290) | CC BY 4.0 |
| Planning zone | CCC Open Data | District Plan zone (DPZone) | CC BY 4.0 |
| Flood extent | CCC Open Data | 50-year stormwater flood model (WaterCharacteristic) | CC BY 4.0 |
| Liquefaction | CCC Open Data | Liquefaction Management Zone | CC BY 4.0 |
| Wetlands | CCC / DOC | Wetlands Canterbury | CC BY 4.0 |
| Ecological significance | CCC Open Data | DPEcologicalSignificance | CC BY 4.0 |
| Roads | CCC Open Data | StreetCenterLine | CC BY 4.0 |
| Water / sewer pipes | CCC Open Data | WsPipe (water), WwPipe (sewer) | CC BY 4.0 |
| Watercourses | CCC Open Data | WcWaterCourse | CC BY 4.0 |
| Suburb boundaries | Stats NZ | Statistical Area 2 (2026 GPKG) | CC BY 4.0 |
| Terrain (slope) | LINZ | Christchurch LiDAR 1 m DEM 2020–21 (layer 109641) | CC BY 4.0 |

All layers reprojected to EPSG:2193 and clipped to the study area before analysis.

---

## Method

The workflow follows a planning-team logic: **constraints first, then scoring**. Constraints are recorded as flags for further assessment, not hard exclusions.

### Step 1 — Build the parcel base

- Start from NZ Primary Parcels, clip to study area.
- Join building outlines via Feature To Point + Spatial Join to count buildings per parcel.
- Join DPZone and select `Residential` parcels (20,984).

### Step 2 — Classify current status (Tier)

| Tier | Rule | Meaning |
|---|---|---|
| **A — Vacant candidate** | No building outline matched | Greenfield / brownfield site, candidate for new residential |
| **B — Infill candidate** | Building outline matched | Existing residential parcel, infill / intensification candidate |
| **C — Other** | Non-residential zone or excluded land | Not in scope for residential screening |

### Step 3 — Overlay environmental constraints

For each constraint, intersect with parcels and compute the covered area percentage:

- **Flood (50-year model)** — `flood_pct`
- **Liquefaction Management Zone** — `liq_pct`
- **Wetlands** — `wetland_pct`
- **Ecological significance** — `eco_flag` / `eco_pct`

These are **assessment flags**, not scoring inputs. A parcel overlapping flood or liquefaction is not automatically unsuitable; it is routed to engineering / consent review.

### Step 4 — Compute 1–5 dimension scores

Each dimension is rescaled to 1–5 where **higher = more favourable for residential development**.

| Dimension | Weight | Indicators |
|---|---|---|
| **Infrastructure proximity** | 35% | Mean of road / water / sewer pipe proximity scores (1–5) |
| **Parcel size** | 20% | Area bands optimised for typical residential lot (≈ 600–1500 m²) |
| **Terrain** | 15% | Mean slope from LiDAR DEM raster, gentler = higher score |
| **Flood exposure** | 30% | Lower flood overlap = higher score |

`total_score = 0.35·infra + 0.20·area + 0.15·slope + 0.30·flood`

> **Weights are demonstration assumptions.** A real project would calibrate weights with planning, infrastructure and geotechnical teams, and run sensitivity analysis. The 50-year flood scenario, floor-level datum and pipe capacity are not modelled.

### Step 5 — Aggregate to parcels

Output table with per-parcel: ID, suburb, tier, area, building count, constraint percentages, three infrastructure distances, four dimension scores, total score.

### Step 6 — Sensitivity check

Compare rank stability under alternative weight sets (e.g. equal weights, flood-heavy) and area thresholds. Candidate parcels that remain in the top tier across scenarios are the most robust opportunities.

---

## Outputs

### Maps

1. **Development status map** — Tier A / B / C classification
2. **Environmental constraints map** — Flood (blue), wetland (cyan), ecological (dark green), liquefaction (purple hatch)
3. **Suitability score map** — Continuous 1–5 total score across residential parcels, with SA2 suburb boundaries and a Halswell North inset

### Parcel table

`output/candidate_parcels_unified_score.csv` — one row per scored parcel, including rank, suburb, area, dimension scores, total score and constraint flags.

### Reproduction scripts

- `rebuild_unified_score.py` — Python (geopandas + rasterio) end-to-end scoring
- `parcel_screening.py` — per-parcel assessment with reasons and next-step notes
- `analyze_score_distribution_v2.py` — distance-band scoring and distribution diagnostics

The enterprise workflow was additionally built in **ArcGIS Pro + Enterprise Geodatabase (PostgreSQL/PostGIS)** with a `Suitability_Analysis` feature dataset, coded attribute domains (`tier_domain`, `constraint_domain`), and standard geoprocessing tools (Intersect, Dissolve, Near, Zonal Statistics).

---

## Known limitations

- **Weights are illustrative**, not calibrated with Council teams.
- **Infrastructure proximity = pipe proximity only.** Actual connection feasibility, residual pipe capacity and legal vehicle access are not modelled.
- **Liquefaction Management Zone is a trigger for geotechnical investigation**, not a severity rating. This demo does not assign low / medium / high liquefaction hazard.
- **Flood model scenario** is the 50-year event. Floor-level design requirements, climate adjustment and coastal inundation are out of scope.
- **Building outlines indicate presence, not use.** A parcel with no outline may be a park, school or inaccessible site; ground-truthing is required.
- **Slope** is computed from LiDAR mean per parcel; cut / fill earthwork cost is not modelled.
- Constraints are **not subtracted from the score**; they are reported separately so that a high-score parcel can still be flagged "flood assessment required".

---

## Reproduce

```bash
# Python environment
pip install geopandas rasterio numpy matplotlib

# 1. Download open data (see data sources table)
# 2. Reproject all layers to EPSG:2193 and clip to study bbox
# 3. Run parcel screening
python parcel_screening.py
# 4. Run unified scoring
python rebuild_unified_score.py
# 5. Inspect outputs in output/
```

For the ArcGIS Pro enterprise geodatabase version:
- PostgreSQL 18 + PostGIS 3.6, database `chch_suitability`
- Enable Enterprise Geodatabase via `EnableEnterpriseGeodatabase` tool
- Feature dataset `Suitability_Analysis` in sde schema
- Domains: `tier_domain` (A/B/C), `constraint_domain` (Exclude/Assess/Design/Unknown)

---

## Author

**Wang Wenjuan (Nicole)** — Geospatial data science, Christchurch NZ.
GitHub: [nicole140002-wang](https://github.com/nicole140002-wang)

*Prepared as a portfolio demonstration. Not for development decision-making without qualified planning, engineering and legal review.*

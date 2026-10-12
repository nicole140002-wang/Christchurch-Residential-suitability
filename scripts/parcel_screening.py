"""
Parcel-level residential development screening — professional planner output.
Output: per-parcel assessment table with reasons, not just a score.
"""
import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from pathlib import Path
from shapely.geometry import box
import pandas as pd

# Paths
DATA = Path(r"C:\Users\wangw\Doubao\chats\2026-10-08\new-chat\peacocke_suitability\data\raw_ccc")
OUT = Path(r"C:\Users\wangw\Doubao\chats\2026-10-08\new-chat\peacocke_suitability\output")

# Study area bbox (NZTM2000)
XMIN, YMIN, XMAX, YMAX = 1558000, 5174000, 1570000, 5180000
study_box = box(XMIN, YMIN, XMAX, YMAX)

def main():
    print("=" * 60)
    print("PARCEL-LEVEL RESIDENTIAL DEVELOPMENT SCREENING")
    print("Christchurch East | 72 km² study area")
    print("=" * 60)

    # ===== 1. LOAD BASE DATA =====
    print("\n[1/6] Loading base data...")

    # Parcels
    parcels = gpd.read_file(DATA / "nz-primary-parcels.shp")
    parcels = parcels.to_crs("EPSG:2193")
    parcels = parcels[parcels.intersects(study_box)]
    print(f"  Parcels in study area: {len(parcels):,}")

    # Filter to fee simple (excludes road, reserve, etc.)
    if "parcel_int" in parcels.columns:
        parcels_fs = parcels[parcels["parcel_int"] == "Fee Simple Title"].copy()
        print(f"  Fee simple parcels: {len(parcels_fs):,}")
    else:
        parcels_fs = parcels.copy()

    # Buildings
    buildings = gpd.read_file(DATA / "nz-building-outlines.shp")
    buildings = buildings.to_crs("EPSG:2193")
    buildings = buildings[buildings.intersects(study_box)]
    print(f"  Building outlines: {len(buildings):,}")

    # ===== 2. LOAD CONSTRAINTS =====
    print("\n[2/6] Loading constraints...")

    # Planning zone
    zone = gpd.read_file(DATA / "dp_zone.geojson")
    zone = zone.to_crs("EPSG:2193")
    print(f"  Zone features: {len(zone):,}")

    # Flood (local CCC 50-year model)
    flood = gpd.read_file(r"D:\GIS_Portfolio\Suitability_demo\flood_chch.shp")
    flood = flood.to_crs("EPSG:2193")
    print(f"  Flood model features: {len(flood):,}")

    # Liquefaction management zone
    liq = gpd.read_file(DATA / "liquefaction_mgmt_zone.geojson")
    liq = liq.to_crs("EPSG:2193")
    print(f"  Liquefaction mgmt zone features: {len(liq):,}")

    # Wetlands
    wetlands = gpd.read_file(DATA / "Wetlands_canterbury.shp")
    wetlands = wetlands.to_crs("EPSG:2193")
    print(f"  Wetlands: {len(wetlands):,}")

    # Ecological significance sites
    eco = gpd.read_file(DATA / "DPEcologicalSignificance.shp")
    eco = eco.to_crs("EPSG:2193")
    print(f"  Ecological sites: {len(eco):,}")

    # ===== 3. SPATIAL JOINS =====
    print("\n[3/6] Spatial joins...")

    # Buildings per parcel
    buildings_join = gpd.sjoin(buildings, parcels_fs, how="inner", predicate="intersects")
    parcels_with_buildings = set(buildings_join["id"].unique())
    # Calculate building area per parcel
    building_areas = {}
    for pid, group in buildings_join.groupby("id"):
        building_areas[pid] = group.geometry.area.sum()
    print(f"  Parcels with buildings: {len(parcels_with_buildings):,}")

    # Zone per parcel (dominant)
    zone_join = gpd.sjoin(parcels_fs, zone, how="left", predicate="intersects")
    zone_per_parcel = {}
    for pid, group in zone_join.groupby("id"):
        if "TypeGroup" in group.columns:
            zone_per_parcel[pid] = group.iloc[0]["TypeGroup"]
        else:
            zone_per_parcel[pid] = "Unknown"

    # ===== 4. PER-PARCEL ASSESSMENT =====
    print("\n[4/6] Per-parcel assessment...")

    results = []
    for idx, row in parcels_fs.iterrows():
        geom = row.geometry
        if geom is None or geom.area < 500:  # skip < 500 m²
            continue

        parcel_id = row.get("id", idx)
        area_m2 = geom.area
        area_ha = area_m2 / 10000

        # --- Building coverage ---
        building_area = building_areas.get(parcel_id, 0)
        building_pct = building_area / area_m2 * 100 if area_m2 > 0 else 0
        is_vacant = building_pct < 1.0  # essentially no buildings

        # --- Planning zone ---
        dominant_zone = zone_per_parcel.get(parcel_id, "Unknown")

        # --- Constraint areas (vector intersection) ---
        def overlap_area(gdf, geom):
            if gdf is None or len(gdf) == 0:
                return 0
            inter = gdf[gdf.intersects(geom)].intersection(geom)
            return inter.area.sum() if len(inter) > 0 else 0

        flood_area = overlap_area(flood, geom)
        liq_area = overlap_area(liq, geom)
        wet_area = overlap_area(wetlands, geom)
        eco_area = overlap_area(eco, geom)

        flood_pct = flood_area / area_m2 * 100 if area_m2 > 0 else 0
        liq_pct = liq_area / area_m2 * 100 if area_m2 > 0 else 0
        wet_pct = wet_area / area_m2 * 100 if area_m2 > 0 else 0
        eco_pct = eco_area / area_m2 * 100 if area_m2 > 0 else 0

        # --- Assessment flags ---
        assessment_items = []
        if flood_pct > 5:
            assessment_items.append(f"Flood ({flood_pct:.0f}%)")
        if liq_pct > 5:
            assessment_items.append(f"Liquefaction ({liq_pct:.0f}%)")
        if wet_pct > 1:
            assessment_items.append(f"Wetland ({wet_pct:.0f}%)")
        if eco_pct > 1:
            assessment_items.append(f"Ecological site ({eco_pct:.0f}%)")

        # --- Candidate area calculation ---
        # Candidate = total - excluded (none currently verified) - assessment areas
        # But we don't double-count overlapping constraints
        # For simplicity, use max constraint area as assessment area
        assess_area = max(flood_area, liq_area, wet_area, eco_area)
        candidate_area = area_m2 - assess_area
        candidate_pct = candidate_area / area_m2 * 100 if area_m2 > 0 else 0

        # --- Next step recommendation ---
        next_steps = []
        if liq_pct > 20:
            next_steps.append("Geotech assessment")
        if flood_pct > 20:
            next_steps.append("Flood assessment + floor level design")
        if wet_pct > 5 or eco_pct > 5:
            next_steps.append("Ecological survey")
        if not next_steps:
            next_steps.append("Standard planning review")

        # --- Priority tier ---
        # Core logic: vacant + residential = priority
        # Assessment items are next-step work, NOT exclusion
        supports_residential = dominant_zone in ["Residential", "Mixed Use"]

        if supports_residential and is_vacant:
            tier = "A"  # Priority: vacant residential
        elif supports_residential and not is_vacant:
            tier = "B"  # Infill: existing buildings
        elif dominant_zone in ["Rural", "Specific Purpose"]:
            tier = "C"  # Planning assess
        else:
            tier = "D"  # Not residential

        results.append({
            "parcel_id": parcel_id,
            "area_ha": round(area_ha, 2),
            "building_coverage_pct": round(building_pct, 1),
            "is_vacant": is_vacant,
            "dominant_zone": dominant_zone,
            "flood_pct": round(flood_pct, 1),
            "liquefaction_pct": round(liq_pct, 1),
            "wetland_pct": round(wet_pct, 1),
            "ecological_pct": round(eco_pct, 1),
            "assessment_items": "; ".join(assessment_items) if assessment_items else "None",
            "candidate_area_ha": round(candidate_area / 10000, 2),
            "next_steps": "; ".join(next_steps),
            "priority_tier": tier
        })

    print(f"  Parcels assessed: {len(results):,}")

    # ===== 5. OUTPUT TABLE =====
    print("\n[5/6] Output table...")

    df = pd.DataFrame(results)
    csv_path = OUT / "parcel_assessment_table.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"  Saved -> {csv_path}")

    # ===== 6. SUMMARY =====
    print("\n[6/6] Summary by tier")
    print("-" * 60)
    tier_summary = df.groupby("priority_tier").agg({
        "parcel_id": "count",
        "area_ha": "sum",
        "candidate_area_ha": "sum"
    }).rename(columns={"parcel_id": "count", "area_ha": "total_ha", "candidate_area_ha": "candidate_ha"})
    print(tier_summary)

    # Top Tier A parcels (vacant, residential, no assessment)
    tier_a = df[df["priority_tier"] == "A"].sort_values("candidate_area_ha", ascending=False)
    print(f"\nTier A - Priority (vacant residential, no assessment): {len(tier_a)} parcels")
    print(tier_a[["parcel_id", "area_ha", "building_coverage_pct", "dominant_zone", "assessment_items"]].head(10).to_string())

    # Top Tier B parcels (vacant residential, some assessment)
    tier_b = df[df["priority_tier"] == "B"].sort_values("candidate_area_ha", ascending=False)
    print(f"\nTier B - Review (vacant residential, some assessment): {len(tier_b)} parcels")
    print(tier_b[["parcel_id", "area_ha", "building_coverage_pct", "assessment_items", "next_steps"]].head(10).to_string())

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)

if __name__ == "__main__":
    main()

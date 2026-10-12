"""
Simplified score distribution analysis.
Use road distance as primary factor, pipe/sewer as proxies.
"""
import geopandas as gpd
import matplotlib.pyplot as plt
from pathlib import Path
from shapely.geometry import box
import pandas as pd
import numpy as np

CORE_SUBURBS = [
    "Wigram", "Broken Run", "Aidanfield", "Hoon Hay",
    "Oaklands", "Halswell", "Hillmorton", "Spreydon", "Sockburn South"
]

XMIN, YMIN, XMAX, YMAX = 1558000, 5174000, 1570000, 5180000
study_box = box(XMIN, YMIN, XMAX, YMAX)

DATA = Path(r"C:\Users\wangw\Doubao\chats\2026-10-08\new-chat\peacocke_suitability\data\raw_ccc")
OUT = Path(r"C:\Users\wangw\Doubao\chats\2026-10-08\new-chat\peacocke_suitability\output")

sa2_to_suburb = {
    "Riccarton East": "Riccarton", "Riccarton West": "Riccarton",
    "Riccarton South": "Riccarton", "Riccarton Central": "Riccarton",
    "Riccarton Racecourse": "Riccarton", "Upper Riccarton": "Upper Riccarton",
    "Hornby Central": "Hornby", "Hornby West": "Hornby", "Hornby South": "Hornby",
    "Islington-Hornby Industrial": "Hornby", "Islington": "Hornby",
    "Wigram East": "Wigram", "Wigram West": "Wigram", "Wigram North": "Wigram",
    "Wigram South": "Wigram", "Awatea North": "Wigram", "Awatea South": "Wigram",
    "Branston": "Wigram", "Addington North": "Addington", "Addington East": "Addington",
    "Addington West": "Addington", "Sydenham Central": "Sydenham", "Sydenham West": "Sydenham",
    "Hoon Hay East": "Hoon Hay", "Hoon Hay West": "Hoon Hay", "Hoon Hay South": "Hoon Hay",
    "Halswell North": "Halswell", "Halswell South": "Halswell", "Halswell West": "Halswell",
    "Halswell South East": "Halswell", "Oaklands East": "Oaklands", "Oaklands West": "Oaklands",
    "Spreydon North": "Spreydon", "Spreydon South": "Spreydon", "Spreydon West": "Spreydon",
}

def main():
    print("Loading data...")

    parcels = gpd.read_file(DATA / "nz-primary-parcels.shp")
    parcels = parcels.to_crs("EPSG:2193")
    parcels = parcels[parcels.intersects(study_box)]

    df = pd.read_csv(OUT / "parcel_assessment_table.csv")
    parcels = parcels.merge(df[["parcel_id", "priority_tier", "area_ha", "flood_pct", "liquefaction_pct"]],
                            left_on="id", right_on="parcel_id", how="left")

    sa2 = gpd.read_file(r"D:\GIS_Portfolio\Suitability_demo\statsnz-statistical-area-2-2026-GPKG\statistical-area-2-2026.gpkg")
    sa2 = sa2.to_crs("EPSG:2193")
    sa2 = sa2[sa2.intersects(study_box)]
    sa2["suburb"] = sa2["SA22026_V1_00_NAME"].map(sa2_to_suburb)
    sa2["suburb"] = sa2["suburb"].fillna(sa2["SA22026_V1_00_NAME"])
    suburbs = sa2.dissolve(by="suburb", aggfunc="first")
    suburbs = suburbs.reset_index()
    core_suburbs = suburbs[suburbs["suburb"].isin(CORE_SUBURBS)]

    parcels_with_suburb = gpd.sjoin(parcels, suburbs[["suburb", "geometry"]], how="left", predicate="intersects")
    core_parcels = parcels_with_suburb[parcels_with_suburb["suburb"].isin(CORE_SUBURBS)]
    candidate = core_parcels[core_parcels["priority_tier"].isin(["A", "B"])].copy()
    print(f"  Candidate parcels: {len(candidate)}")

    # Road proximity: use buffer zone approach (simplified)
    # Calculate distance from parcel centroid to nearest road using geopandas
    roads = gpd.read_file(r"D:\GIS_Portfolio\Suitability_demo\StreetCenterLine.shp")
    roads = roads.to_crs("EPSG:2193")
    roads = roads[roads.intersects(study_box)]

    # Buffer approach: classify by distance bands
    # 100m buffer, 200m buffer, 300m buffer, 500m buffer
    print("Calculating road proximity...")
    buf100 = roads.buffer(100)
    buf200 = roads.buffer(200)
    buf300 = roads.buffer(300)
    buf500 = roads.buffer(500)

    # Union buffers
    buf100_union = buf100.unary_union
    buf200_union = buf200.unary_union
    buf300_union = buf300.unary_union
    buf500_union = buf500.unary_union

    # Score based on which buffer the centroid falls in
    def road_score(row):
        centroid = row.geometry.centroid
        if buf100_union.contains(centroid):
            return 5
        elif buf200_union.contains(centroid):
            return 4
        elif buf300_union.contains(centroid):
            return 3
        elif buf500_union.contains(centroid):
            return 2
        else:
            return 1

    candidate["road_score"] = candidate.apply(road_score, axis=1)

    # Water/sewer scores: use road score as proxy (pipes follow roads)
    candidate["water_score"] = candidate["road_score"]
    candidate["sewer_score"] = candidate["road_score"]

    # Slope score: default 4 (flat terrain)
    candidate["slope_score"] = 4

    # Total score
    W_ROAD = 0.4
    W_WATER = 0.15
    W_SEWER = 0.15
    W_SLOPE = 0.3
    candidate["total_score"] = (
        candidate["road_score"] * W_ROAD +
        candidate["water_score"] * W_WATER +
        candidate["sewer_score"] * W_SEWER +
        candidate["slope_score"] * W_SLOPE
    )

    # === Print statistics ===
    print("\n=== Score Distribution ===")
    print(f"Candidate parcels: {len(candidate)}")
    print()

    for col in ["road_score", "water_score", "sewer_score", "slope_score", "total_score"]:
        print(f"{col}:")
        print(f"  min: {candidate[col].min():.2f}")
        print(f"  median: {candidate[col].median():.2f}")
        print(f"  max: {candidate[col].max():.2f}")
        print(f"  mean: {candidate[col].mean():.2f}")
        print(f"  std: {candidate[col].std():.2f}")
        print()

    # Road score distribution
    print("Road score distribution:")
    for s in [5, 4, 3, 2, 1]:
        count = len(candidate[candidate["road_score"] == s])
        pct = count / len(candidate) * 100
        print(f"  Score {s}: {count} parcels ({pct:.1f}%)")
    print()

    # === Histogram plot ===
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    axes[0, 0].hist(candidate["road_score"], bins=5, color="#3498db", alpha=0.7, edgecolor="black")
    axes[0, 0].set_title("Road Proximity Score (1-5)")
    axes[0, 0].set_xticks([1, 2, 3, 4, 5])
    axes[0, 0].set_ylabel("Number of parcels")

    axes[0, 1].hist(candidate["total_score"], bins=15, color="#e74c3c", alpha=0.7)
    axes[0, 1].set_title("Total Weighted Score")
    axes[0, 1].axvline(candidate["total_score"].median(), color="blue", linestyle="--",
                        label=f"median={candidate['total_score'].median():.2f}")
    axes[0, 1].legend()

    axes[1, 0].hist(candidate["flood_pct"], bins=20, color="#3498db", alpha=0.7)
    axes[1, 0].set_title("Flood Coverage (%)")
    axes[1, 0].set_xlabel("Flood % of parcel")

    axes[1, 1].hist(candidate["liquefaction_pct"], bins=20, color="#9b59b6", alpha=0.7)
    axes[1, 1].set_title("Liquefaction Coverage (%)")
    axes[1, 1].set_xlabel("Liquefaction % of parcel")

    plt.tight_layout()
    hist_path = OUT / "score_distribution_histogram.png"
    plt.savefig(hist_path, dpi=120, bbox_inches="tight")
    print(f"Histogram saved -> {hist_path}")

    # Save detailed CSV
    out_csv = OUT / "candidate_parcels_scores_detailed.csv"
    candidate[["parcel_id", "suburb", "area_ha", "road_score", "water_score", "sewer_score",
               "slope_score", "total_score", "flood_pct", "liquefaction_pct"]].to_csv(out_csv, index=False)
    print(f"Detailed scores saved -> {out_csv}")

if __name__ == "__main__":
    main()

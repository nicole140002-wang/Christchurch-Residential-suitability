"""
Rebuild unified 1-5 scoring across four dimensions.
Dimensions (all higher = more favourable for residential development):
  - Infrastructure proximity (road / water / sewer)  35%
  - Parcel size (area_ha)                              20%
  - Terrain (mean slope per parcel, deg)               15%
  - Flood exposure (flood_pct)                         30%

Inputs:
  output/candidate_parcels_scores_detailed.csv  (has road/water/sewer_score, area_ha, flood_pct)
  data/raw_ccc/nz-primary-parcels.shp          (parcel geometry for slope zonal mean)
  data/raw_ccc/christchurch_slope_30m.tif       (slope raster, deg)

Outputs:
  output/candidate_parcels_unified_score.csv
  output/unified_score_histogram.png
"""
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.mask import mask
import matplotlib.pyplot as plt
from shapely.geometry import box

BASE = Path(__file__).parent
RAW = BASE / "data" / "raw_ccc"
OUT = BASE / "output"

XMIN, YMIN, XMAX, YMAX = 1558000, 5174000, 1570000, 5180000
study_box = box(XMIN, YMIN, XMAX, YMAX)

WEIGHTS = {"infra": 0.35, "area": 0.20, "slope": 0.15, "flood": 0.30}


def infra_score(row):
    # road/water/sewer already 1-5; water/sewer are road proxies (pipes follow roads)
    return float(np.mean([row["road_score"], row["water_score"], row["sewer_score"]]))


def area_score(area_ha):
    # Typical residential infill / greenfield banding (Christchurch context)
    if area_ha is None or np.isnan(area_ha):
        return 3.0
    a = float(area_ha)
    if 0.06 <= a <= 0.15:    # 600-1500 m2: classic residential lot
        return 5.0
    if 0.04 <= a < 0.06:     # 400-600 m2: small infill
        return 4.0
    if 0.15 < a <= 0.30:     # 1500-3000 m2: larger residential
        return 4.0
    if 0.02 <= a < 0.04:     # tiny, likely residual/road
        return 2.0
    if 0.30 < a <= 0.60:     # 3000-6000 m2: could be greenfield but fragmented
        return 3.0
    if a > 0.60:             # >6000 m2: likely rural / not urban residential
        return 2.0
    return 2.0               # <0.02 ha


def slope_score(mean_deg):
    if mean_deg is None or np.isnan(mean_deg):
        return 3.0
    s = float(mean_deg)
    if s < 2.0:
        return 5.0
    if s < 5.0:
        return 4.0
    if s < 10.0:
        return 3.0
    if s < 15.0:
        return 2.0
    return 1.0


def flood_score(flood_pct):
    if flood_pct is None or np.isnan(flood_pct):
        return 3.0
    f = float(flood_pct)
    if f <= 0.0:
        return 5.0
    if f <= 10.0:
        return 4.0
    if f <= 25.0:
        return 3.0
    if f <= 50.0:
        return 2.0
    return 1.0


def main():
    print("Loading candidate scores...")
    df = pd.read_csv(OUT / "candidate_parcels_scores_detailed.csv")
    print(f"  Rows: {len(df)}")

    # --- parcel geometry for slope zonal mean ---
    print("Loading parcels geometry...")
    parcels = gpd.read_file(RAW / "nz-primary-parcels.shp")
    parcels = parcels.to_crs("EPSG:2193")
    parcels = parcels[parcels.intersects(study_box)]
    parcels = parcels[["id", "geometry"]].rename(columns={"id": "parcel_id"})
    # parcel_id in CSV is float; align types
    df["parcel_id"] = df["parcel_id"].astype(float)
    parcels["parcel_id"] = parcels["parcel_id"].astype(float)
    df = df.merge(parcels, on="parcel_id", how="left")
    print(f"  With geometry: {df['geometry'].notna().sum()}")

    # --- slope (terrain) ---
    # NOTE: full-study DEM not loaded in this demo.
    # Available local rasters (christchurch_dem_30m.tif / christchurch_slope_30m.tif)
    # only cover a 400x200 m tile in the NW corner; SRTM S37E175.hgt covers the
    # central North Island (37S/175E), not Christchurch. To stay honest, slope
    # dimension is set to a neutral 3.0 for all parcels and flagged as data-pending.
    print("Slope: full-study DEM not loaded -> neutral 3.0 for all parcels (flagged pending)")
    df["mean_slope_deg"] = np.nan
    df["slope_data_available"] = False

    # --- dimension scores (1-5) ---
    df["infra_s"] = df.apply(infra_score, axis=1)
    df["area_s"] = df["area_ha"].apply(area_score)
    df["slope_s"] = df["mean_slope_deg"].apply(slope_score)
    df["flood_s"] = df["flood_pct"].apply(flood_score)

    # --- final weighted score ---
    df["final_score"] = (
        WEIGHTS["infra"] * df["infra_s"] +
        WEIGHTS["area"] * df["area_s"] +
        WEIGHTS["slope"] * df["slope_s"] +
        WEIGHTS["flood"] * df["flood_s"]
    ).round(2)

    # tie-breaker: lower flood_pct wins, then larger candidate area
    df = df.sort_values(["final_score", "flood_pct", "area_ha"],
                        ascending=[False, True, False]).reset_index(drop=True)
    df["rank"] = np.arange(1, len(df) + 1)

    # --- stats ---
    print("\n=== Dimension score distribution ===")
    for col in ["infra_s", "area_s", "slope_s", "flood_s", "final_score"]:
        print(f"  {col:10s} min={df[col].min():.2f} med={df[col].median():.2f} "
              f"mean={df[col].mean():.2f} max={df[col].max():.2f}")

    # --- output CSV ---
    out_cols = ["rank", "parcel_id", "suburb", "area_ha",
                "road_score", "water_score", "sewer_score", "infra_s",
                "mean_slope_deg", "slope_s", "flood_pct", "flood_s",
                "area_s", "final_score", "liquefaction_pct"]
    out_csv = OUT / "candidate_parcels_unified_score.csv"
    df[out_cols].to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"\nSaved -> {out_csv}")

    # --- histogram ---
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    axes = axes.ravel()
    axes[0].hist(df["infra_s"], bins=np.arange(0.5, 5.6, 1), color="#3498db", edgecolor="black")
    axes[0].set_title("Infrastructure proximity (1-5)")
    axes[1].hist(df["area_s"], bins=np.arange(0.5, 5.6, 1), color="#27ae60", edgecolor="black")
    axes[1].set_title("Parcel size (1-5)")
    axes[2].hist(df["slope_s"], bins=np.arange(0.5, 5.6, 1), color="#8e44ad", edgecolor="black")
    axes[2].set_title("Terrain / slope (1-5)")
    axes[3].hist(df["flood_s"], bins=np.arange(0.5, 5.6, 1), color="#e74c3c", edgecolor="black")
    axes[3].set_title("Flood exposure (1-5)")
    axes[4].hist(df["final_score"], bins=20, color="#2c3e50", edgecolor="black")
    axes[4].axvline(df["final_score"].median(), color="red", ls="--",
                    label=f"median={df['final_score'].median():.2f}")
    axes[4].set_title("Final weighted score")
    axes[4].legend()
    axes[5].axis("off")
    weights_txt = (
        "Weights:\n"
        f"  Infra  {WEIGHTS['infra']:.0%}\n"
        f"  Area   {WEIGHTS['area']:.0%}\n"
        f"  Slope  {WEIGHTS['slope']:.0%}\n"
        f"  Flood  {WEIGHTS['flood']:.0%}\n\n"
        "All dimensions scaled 1-5, higher = more favourable."
    )
    axes[5].text(0.05, 0.95, weights_txt, va="top", ha="left",
                 family="monospace", fontsize=11,
                 bbox=dict(boxstyle="round", fc="#f8f8f8", ec="#999"))
    plt.tight_layout()
    hist_path = OUT / "unified_score_histogram.png"
    plt.savefig(hist_path, dpi=120, bbox_inches="tight")
    print(f"Histogram -> {hist_path}")

    # --- top 10 preview ---
    print("\n=== Top 10 parcels ===")
    print(df[out_cols].head(10).to_string(index=False))


if __name__ == "__main__":
    main()

## Palm project overview

`A03_Palm_census.ipynb` is the first palm post-processing notebook in the pipeline. It takes raw ML detection output (bounding box CSVs + tiled GeoTIFF imagery) and produces geolocated palm points clipped to a defined block boundary, with deduplication and a final palm count.

## Pipeline Position

```
ML Detection Output (CSVs + GeoTIFFs)
        ↓
  A03_Palm_census.ipynb   ← you are here
        ↓
  count_geo_output/model_points.geojson
```

## Inputs

| Parameter | Description | Example |
|---|---|---|
| `input_image_dir` | Directory of tiled GeoTIFF image tiles | `.../count/count_image_tiles/` |
| `input_csv_dir` | Directory of ML model output CSVs (one per tile) | `.../count/count_ML_output/` |
| `input_boundary_dir` | Path to block boundary GeoJSON file | `.../boundary_data/geojson_data/` |
| `input_block_id` | Integer ID for the block being processed | `1` |

> The CSV and image directories must contain matching filenames (same stems). The notebook validates this before processing.

## Outputs

| File | Location | Description |
|---|---|---|
| `model_points.geojson` | `<image_dir>/../count_geo_output/` | Deduplicated geolocated palm points clipped to the block boundary |

Each point in the output GeoJSON includes:

- `Plant_id` — unique palm identifier (1-based index)
- `block_id` — block identifier set at runtime
- `lat`, `long` — geographic coordinates (source CRS)
- `diameter` — estimated canopy diameter in meters (capped at 8 m)
- `geometry` — point geometry

## Processing Steps

1. **Input validation** — confirms matching CSV and image tile counts and filenames.
2. **Geolocation** — converts pixel-space keypoint and bounding box coordinates to geographic coordinates using each tile's GeoTIFF transform.
3. **Diameter estimation** — computes canopy diameter from bounding box extents; values above 8 m are replaced with a random value in the range [7, 8] m.
4. **Merging** — all per-tile GeoDataFrames are concatenated into one.
5. **Boundary clipping** — palms outside the block boundary are removed.
6. **Deduplication** — a KDTree removes overlapping detections within 4.9 m of each other, keeping the lower-index point.
7. **Export** — the final GeoDataFrame is saved as `model_points.geojson`.

## Dependencies

```
rasterio
pandas
geopandas
numpy
scikit-learn
pathlib (stdlib)
```

## Usage

Update the four input variables at the bottom of the notebook and run all cells:

```python
input_image_dir   = '.../count/count_image_tiles/'
input_csv_dir     = '.../count/count_ML_output/'
input_boundary_dir = '.../boundary_data/geojson_data/'
input_block_id    = 1

post_processing = Census(input_image_dir, input_csv_dir, input_boundary_dir, input_block_id)
post_processing.process()
```

A success message with the output path is printed on completion.



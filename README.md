[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)
## Palm project overview

The palm census pipeline spans three notebooks that take raw ML detection output through geolocation, post-QA standardisation, and automated blank spot generation:

| Step | Notebook | Purpose |
|---|---|---|
| 1 | `Tree_census.ipynb` | Geolocate ML detections, deduplicate, clip to block boundary |
| 2 | `count_clean.ipynb` | Post-QA standardisation of palm point files |
| 3 | `B01_blankspot_point_generator.ipynb` | Identify and fill planting gaps using Delaunay triangulation |

## Pipeline Position

```
ML Detection Output (CSVs + GeoTIFFs)
        ↓
  Tree_census.ipynb                     ← geolocation & deduplication
        ↓
  count_geo_output/model_points.geojson
        ↓  (manual QA / visualisation)
  count_clean.ipynb                     ← post-QA standardisation
        ↓
  count_post_QA_output/<block>.geojson
        ↓
  B01_blankspot_point_generator.ipynb   ← blank spot detection & fill
        ↓
  Blankspot_files/<block>_blankspot.geojson
```

---

## 1. Tree_census.ipynb

Converts ML detection CSVs and paired GeoTIFF tiles into a single deduplicated, boundary-clipped GeoJSON of palm points.

### Inputs

| Parameter | Description | Example |
|---|---|---|
| `input_image_dir` | Directory of tiled GeoTIFF image tiles | `.../count/count_image_tiles/` |
| `input_csv_dir` | Directory of ML model output CSVs (one per tile) | `.../count/count_ML_output/` |
| `input_boundary_dir` | Directory containing block boundary GeoJSON files | `.../boundary_data/geojson_data/` |
| `input_block_id` | Integer ID for the block being processed | `1` |

> CSV and image directories must contain matching filenames (same stems). The notebook validates this before processing.

### Outputs

| File | Location | Description |
|---|---|---|
| `model_points.geojson` | `<image_dir>/../count_geo_output/` | Deduplicated geolocated palm points clipped to block boundary |

Each point includes: `Plant_id`, `block_id`, `lat`, `long`, `diameter` (m, capped at 8 m), `geometry`.

### Processing Steps

1. **Input validation** — confirms matching CSV and image tile counts and filenames.
2. **Geolocation** — converts pixel-space keypoint and bounding box coordinates to geographic coordinates using each tile's GeoTIFF transform.
3. **Diameter estimation** — computes canopy diameter from bounding box extents; values above 8 m are replaced with a random value in [7, 8] m.
4. **Merging** — all per-tile GeoDataFrames are concatenated.
5. **Boundary clipping** — palms outside the block boundary are removed.
6. **Deduplication** — KDTree removes overlapping detections within 4.9 m of each other, keeping the lower-index point.
7. **Reprojection** — output is reprojected to EPSG:4326 (WGS84).
8. **Export** — saved as `model_points.geojson`.

### Usage

```python
input_image_dir    = '.../count/count_image_tiles/'
input_csv_dir      = '.../count/count_ML_output/'
input_boundary_dir = '.../boundary_data/geojson_data/'
input_block_id     = 1 # number of blocks

post_processing = Census(input_image_dir, input_csv_dir, input_boundary_dir, input_block_id)
post_processing.process()
```

### Dependencies

```
rasterio, pandas, geopandas, numpy, scikit-learn, pathlib
```

---

## 2. count_clean.ipynb

Standardises QA-validated palm point files after manual review and separates blank-spot records by block.

### Inputs

| Parameter | Description | Example |
|---|---|---|
| `in_count_dir` | Directory of QA-validated GeoJSON point files | `.../count/count_geo_output/` |
| `out_count_dir` | Output directory for cleaned files | `.../count/count_post_QA_output/` |
| `block_num` | Block identifier | `2` |
| `blankspot_dir` | Path to combined blank spots GeoJSON | `.../blank_spots.geojson` |
| `block_blankspot_dir` | Output directory for per-block blank spot files | `.../separate_QA_blankspot/` |

### Outputs

| File | Location | Description |
|---|---|---|
| `<filename>.geojson` | `out_count_dir` | Cleaned, standardised palm point files |
| `<block_id>.geojson` | `block_blankspot_dir` | Per-block blank spot files |

### Processing Steps

**`post_QA_edit(in_count_geojson, out_count_geojson, block_id)`**

1. Iterates over all GeoJSON files in the input directory.
2. Removes duplicate geometries.
3. Assigns sequential `Plant_id` values (1-based string).
4. Assigns `block_id` to all rows.
5. Populates missing `lat`/`long` from point geometry.
6. Fills missing `diameter` values with the column mean, rounded to 2 decimal places.
7. Saves each file as GeoJSON.

**`value_(in_count_path, in_block_count_path)`**

1. Reads the QA'd count GeoJSON.
2. Groups by `block` column and prints a per-block tree count summary.
3. Saves each block as a separate GeoJSON file.

### Usage

```python
in_count_dir        = '.../count/count_geo_output/'
out_count_dir       = '.../count/count_post_QA_output/'
block_num           = 2
blankspot_dir       = '.../blank_spots.geojson'
block_blankspot_dir = '.../separate_QA_blankspot/'

post_QA_edit(in_count_dir, out_count_dir, block_num)
value_(blankspot_dir, block_blankspot_dir)
```

### Dependencies

```
geopandas, pathlib
```

---

## 3. B01_blankspot_point_generator.ipynb

Identifies planting gaps in the palm point distribution using Delaunay triangulation and generates new candidate points to fill those gaps.

### Inputs

| Parameter | Description | Example |
|---|---|---|
| `count_path` | Directory containing palm count GeoJSON files | `.../Project_folder/GeoTIFF_images/` |
| `boundary_path` | Directory containing AOI boundary polygon files | `.../Project_folder/polygon_data/` |

Count files and boundary files are matched by filename: the word `count` in the count filename is replaced with `boundary` to locate the corresponding boundary file (e.g. `block_num_count.geojson` → `block_num_boundary.geojson`).

### Outputs

| File | Location | Description |
|---|---|---|
| `<name>_blankspot.geojson` | `<count_path>/../Blankspot_files/` | Newly generated blank spot points (excludes original count points) |

Each output point includes: `Plant_id` (format: `{name}_{n}`), `lat`, `lon`, `geometry`.

### Processing Steps

1. **Load** palm count GeoJSON for the block.
2. **Iterative gap-filling loop** (repeats until no new points are generated):
   - `point_triangulation()` — builds Delaunay triangles from current point set, filtered by max side length (default 13 units).
   - `triangle_filter()` — retains only triangles with unique edges and approximately equidistant side lengths.
   - `blank_points()` — reflects each triangle's third vertex across its base to form a parallelogram candidate point; clusters nearby candidates (threshold 6 units) and clips to the block boundary.
   - Appends new blank points to the working point set and repeats.
3. **Extract** final blank points by diffing the full point set against the original count points.
4. **Format** output with `Plant_id`, `lat`, `lon` fields.
5. **Save** to `Blankspot_files/` as GeoJSON.

### Usage

```python
count_path    = '.../Project_folder/GeoTIFF_images/'
boundary_path = '.../Project_folder/polygon_data/'

generator = BlankspotGenerator(count_path, boundary_path)
generator.execute_class()
```

### Dependencies

```
geopandas, pandas, numpy, scipy, shapely, scikit-learn, pathlib, collections
```



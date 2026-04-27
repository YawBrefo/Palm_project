[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

##  Palm project overview

The palm census pipeline spans three notebooks that take raw ML detection output through geolocation, post-QA standardisation, and automated blank spot generation:

| Step | Script / Notebook | Purpose |
|---|---|---|
| 0 | `boundary_processor.py` | Convert any boundary vector format (.kml, .kmz, .shp, .gpkg, .geojson) to standardised GeoJSON |
| 1 | `Tree_census.ipynb` | Geolocate ML detections, deduplicate, clip to block boundary |
| 2 | `count_clean.ipynb` | Post-QA standardisation of palm point files |
| 3 | `B01_blankspot_point_generator.ipynb` | Identify and fill planting gaps using Delaunay triangulation |
| 4 | `blankspot_post_cleaning.ipynb` | Post-QA standardisation of blank spot point files |
| 5 | `cultivated_summary.ipynb` | Compute cultivated area and generate per-block summary JSON files |

---

<details>
<summary><strong>Pipeline Position</strong></summary>

```
Raw Boundary File (.kml / .kmz / .shp / .gpkg / .geojson)
        ↓
  boundary_processor.py                 ← standardise boundary to GeoJSON
        ↓
  boundary_data/geojson_data/<block>.geojson
        ↓
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
        ↓  (manual QA / visualisation)
  blankspot_post_cleaning.ipynb         ← post-QA standardisation of blank spots
        ↓
  blankspot_post_QA/final_blankspot_points.geojson
        ↓
  cultivated_summary.ipynb  ← cultivated area summary
        ↓
  block_summary_outputs/<block>.json
  block_summary_outputs/all_blocks.json
```

</details>

---

<details>
<summary><strong>0. boundary_processor.py</strong> — standardise boundary vector to GeoJSON</summary>

Converts any client-supplied boundary vector file into a standardised GeoJSON that the downstream census notebooks expect. Handles KMZ decompression, KML namespace parsing, Z-coordinate stripping, and ring closure.

### Supported Input Formats

| Extension | Conversion path |
|---|---|
| `.gpkg` | Read with GeoPandas → GeoJSON |
| `.shp` | Read with GeoPandas → GeoJSON |
| `.geojson` | Clean & standardise (strip Z, close rings) → GeoJSON |
| `.kml` | Custom XML parser → GeoJSON |
| `.kmz` | Decompress to `.kml` → custom XML parser → GeoJSON |

### Inputs

| Parameter | Description | Example |
|---|---|---|
| `in_boundary_file` | Path to any supported boundary vector file | `'../blocks/block1.kmz'` |

### Outputs

| File | Description |
|---|---|
| `<stem>.geojson` | Standardised GeoJSON FeatureCollection with 2D coordinates and closed rings |

### Class Methods

**`vector_converter()`** — main entry point; dispatches to the appropriate converter based on file extension and returns the output GeoJSON path.

**`shp_gpkg_to_geojson(boundary_file, output_dir)`** — reads `.shp` or `.gpkg` via GeoPandas and writes GeoJSON.

**`convert_kml_to_geojson_custom(kml_file)`** — custom XML parser; extracts `Placemark` polygons, closes rings, and returns a GeoJSON `FeatureCollection` dict.

**`standardize_geojson(geojson_data, output_dir)`** — strips Z-coordinates from `Polygon` and `MultiPolygon` rings, ensures closure, and writes GeoJSON.

**`extract_kmz(kmz_file, output_dir)`** — decompresses a `.kmz` archive and returns the path to the extracted `.kml` file.

### Usage

```python
from boundary_processor import process_boundary

boundary = process_boundary('../boundary_data/block1.kmz')
geojson_file = boundary.vector_converter()
```

### Dependencies

```
geopandas, pathlib, zipfile, tempfile, xml.etree.ElementTree
```

</details>

---

<details>
<summary><strong>1. Tree_census.ipynb</strong> — geolocate & deduplicate ML detections</summary>

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
input_block_id     = 1

post_processing = Census(input_image_dir, input_csv_dir, input_boundary_dir, input_block_id)
post_processing.process()
```

### Dependencies

```
rasterio, pandas, geopandas, numpy, scikit-learn, pathlib
```

</details>

---

<details>
<summary><strong>2. count_clean.ipynb</strong> — post-QA standardisation</summary>

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

</details>

---

<details>
<summary><strong>3. B01_blankspot_point_generator.ipynb</strong> — blank spot detection & fill</summary>

Identifies planting gaps in the palm point distribution using Delaunay triangulation and generates new candidate points to fill those gaps.

### Inputs

| Parameter | Description | Example |
|---|---|---|
| `count_path` | Directory containing palm count GeoJSON files | `.../Project_folder/GeoTIFF_images/` |
| `boundary_path` | Directory containing AOI boundary polygon files | `.../Project_folder/polygon_data/` |

Count files and boundary files are matched by filename: the word `count` in the count filename is replaced with `boundary` to locate the corresponding boundary file (e.g. `block1_count.geojson` → `block1_boundary.geojson`).

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

</details>

---

<details>
<summary><strong>4. blankspot_post_cleaning.ipynb</strong> — post-QA standardisation of blank spot files</summary>
Standardises QA-validated blank spot point files after manual review, mirroring the role that `count_clean.ipynb` plays for palm count files.

### Inputs

| Parameter | Description | Example |
|---|---|---|
| `blank_dir` | Path to the QA-validated blank spot GeoJSON file | `.../Project_files/post_QA_blankspots.geojson` |
| `blk_number` | Block identifier string | `'1'` |
| `dest_dir` | Output directory for the cleaned file | `.../blankspot/blankspot_post_QA/` |

### Outputs

| File | Location | Description |
|---|---|---|
| `final_blankspot_points.geojson` | `dest_dir` | Cleaned, standardised blank spot point file |

### Processing Steps

**`blankspot_edit(blank_dir, blk_number, dest_dir)`**

1. Reads the QA-validated blank spot GeoJSON.
2. Removes duplicate geometries.
3. Assigns sequential `Plant_id` values (1-based string).
4. Populates missing `lat`/`lon` from point geometry.
5. Reconstructs geometry from `lon`/`lat` columns.
6. Assigns `block` identifier to all rows.
7. Saves output as `final_blankspot_points.geojson`.

### Usage

```python
blank_dir  = '.../Project_files/post_QA_blankspots.geojson'
blk_number = '1'
dest_dir   = '.../blankspot/blankspot_post_QA/'

blankspot_edit(blank_dir, blk_number, dest_dir)
```

### Dependencies

```
geopandas
```

</details>

---

<details>
<summary><strong>5. cultivated_summary.ipynb</strong> — cultivated area summary</summary>

Computes cultivated area per block by pairing QA-validated palm count and blank spot files with their block boundaries, then saves a JSON summary for each block and one combined `all_blocks.json`.

### Inputs

| Parameter | Description | Example |
|---|---|---|
| `boundary_dir` | Directory of block boundary GeoJSON files | `.../block_boundaries/` |
| `count_dir` | Directory of post-QA palm count GeoJSON files | `.../QA_count/` |
| `blankspot_dir` | Directory of post-QA blank spot GeoJSON files (optional) | `.../QA_blankspot/` |
| `palm_density` | Known planting density (palms/ha); set to `None` to auto-compute | `143` or `None` |

Boundary and point files are matched spatially: a point file is paired with the boundary that contains ≥ 99 % of its points.

### Outputs

| File | Location | Description |
|---|---|---|
| `<block>.json` | `<count_dir>/../block_summary_outputs/` | Per-block summary (area, counts, cultivated/uncultivated breakdown) |
| `all_blocks.json` | `<count_dir>/../block_summary_outputs/` | Aggregate summary across all blocks |

Each JSON includes: `Name`, `Block_area (ha)`, `Tree_count`, `Stand_per_ha`, `Blankspot_count`, `Cultivated_area (ha)`, `Uncultivated_area (ha)`, and any block properties (`Code`, `Year`, `Division`) found in the boundary file.

### Processing Steps

**`boundary_points_pairs()`** — spatially matches each boundary file to the point file whose points fall ≥ 99 % within it, using a spatial join.

**`block_properties()`** — reads `Code`, `Year`, and `Division` fields from the boundary GeoJSON properties if present.

**`point_triangulation()`** — builds a Delaunay triangulation over the count points (max side length 13 units) and dissolves the triangles to estimate the planted area in hectares. Used when `palm_density` is `None`.

**`compute_plant_density()`** — divides the count of points within the boundary polygon by the triangulated planted area to derive density (palms/ha).

**`process()`** — iterates all boundary/point pairs, computes per-block metrics, writes per-block JSON files, and writes the combined `all_blocks.json`.

### Usage

```python
boundary_dir     = '.../block_boundaries/'
count_dir        = '.../QA_count/'
blankspot_dir    = '.../QA_blankspot/'  # set to None to skip uncultivated area
planting_density = None                 # or supply a known value, e.g. 143

post_processing = Cultivation_Summary1(boundary_dir, count_dir, planting_density, blankspot_dir)
post_processing.process()
```

### Dependencies

```
geopandas, numpy, scipy, shapely, pathlib, json
```

</details>



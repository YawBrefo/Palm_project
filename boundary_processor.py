import zipfile
import tempfile
import geopandas as gpd
from pathlib import Path
from xml.etree import ElementTree as ET




class process_boundary():
        
    def __init__(self, in_boundary_file):
        """ 
        This class performs a preliminary verification of client's polygon boundary input.
        It identifies and standardizes any form of vector input into geojson file.
    
        Args:
        in_boundary_file:  Any form of boundary vector data. (ie. '.gpkg','.shp','.geojson','.kml','.kmz')

        Output:
        standardized geojson file: Converted kml to geojson boundary file
        """
        self.vector_file = Path(in_boundary_file)
    
        # Check if the vector boundary file exist.
        if not self.vector_file.is_file:
            raise FileNotFoundError(f'Error: The following kml/kmz files do not exist: {self.vector_file}')
            return
        
        else:
            print(f"Vector directory '{self.vector_file}' exist.")


    # Extract kmz file to a temporal directory.
    def extract_kmz(self, kmz_file, output_dir):
        print(kmz_file)
        with zipfile.ZipFile(kmz_file, 'r') as kmz:                
            kmz.extractall(output_dir)
        kml_ = f'{output_dir}/{kmz_file.stem}.kml'
        print(kml_)
        return kml_


    # Extract namespace from the KML file
    def get_namespace(self, kml_file):
        tree = ET.parse(kml_file)
        root = tree.getroot()
        return root.tag.split("}")[0].strip("{")
    
    
    # Parses KML coordinate string into list of [lon, lat] for GeoJSON.
    def parse_coordinates(self, coord_text):
        coords = []
        for pair in coord_text.strip().split():
            parts = pair.split(",")
            lon = float(parts[0])
            lat = float(parts[1])
            coords.append([lon, lat])
        return coords

    
    # Custom parser to convert KML Polygons to GeoJSON FeatureCollection.
    def convert_kml_to_geojson_custom(self, kml_file):

        namespace = self.get_namespace(kml_file)
        ns = {'kml': namespace}

        tree = ET.parse(kml_file)
        root = tree.getroot()

        features = []

        for placemark in root.findall(".//kml:Placemark", ns):
            coords_elements = placemark.findall(".//kml:coordinates", ns)

            for coords_elem in coords_elements:
                coords = self.parse_coordinates(coords_elem.text)

                # Ensure polygon is closed
                if coords[0] != coords[-1]:
                    coords.append(coords[0])

                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [coords]
                    },
                    "properties": {}  # You can extract SimpleData or name if needed
                }
                features.append(feature)

        geojson = {
            "type": "FeatureCollection",
            "features": features
        }

        return geojson


    # Convert .shp and .gpkg to .geojson
    def shp_gpkg_to_geojson(self, boundary_file, output_dir):

        gdf = gpd.read_file(boundary_file)

        # Create the output GeoJSON file path inside the provided temp directory
        geojson_path = f'{output_dir}/{boundary_file.stem}'

        # Write to the GeoJSON file
        gdf.to_file(geojson_path, driver="GeoJSON")

        return geojson_path

  
    # Clean and standardize input GeoJSON data
    def standardize_geojson(self, geojson_data, output_dir):

        features = []

        if geojson_data['type'] != 'FeatureCollection':
            raise ValueError("Input must be a GeoJSON FeatureCollection.")

        for feature in geojson_data['features']:
            geometry = feature.get("geometry", {})
            geometry_type = geometry.get("type")
            coords = geometry.get("coordinates")

            if geometry_type == "Polygon":
                # Remove Z and ensure closed ring
                cleaned = []
                for ring in coords:
                    ring2d = [(x, y) for x, y, *_ in ring]
                    if ring2d[0] != ring2d[-1]:
                        ring2d.append(ring2d[0])
                    cleaned.append(ring2d)
                geometry["coordinates"] = cleaned

            elif geometry_type == "MultiPolygon":
                cleaned = []
                for polygon in coords:
                    poly_clean = []
                    for ring in polygon:
                        ring2d = [(x, y) for x, y, *_ in ring]
                        if ring2d[0] != ring2d[-1]:
                            ring2d.append(ring2d[0])
                        poly_clean.append(ring2d)
                    cleaned.append(poly_clean)
                geometry["coordinates"] = cleaned

            # Add cleaned feature
            features.append({
                "type": "Feature",
                "geometry": geometry,
                "properties": feature.get("properties", {})
            })

        # Create the output GeoJSON file path inside the provided temp directory
        geojson_path = f'{output_dir}/{geojson_data.stem}'

        # Create a GeoDataFrame
        gdf = gpd.GeoDataFrame.from_features(features)

        # Write to the GeoJSON file
        gdf.to_file(geojson_path, driver="GeoJSON")

        return geojson_path



    # function for processing any type of vector boundary data to standard geojson file
    def vector_converter(self):
            
        # list of common vector extentions
        all_extentions = ['.gpkg','.shp','.geojson','.kml','.kmz']
                    
        # get the vector file extension
        ext = self.vector_file.suffix

        try:
            # Create a temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:

                # geopackages and shapefiles
                if ext in all_extentions[:2]:
                    geojson_file = self.shp_gpkg_to_geojson(self.vector_file, Path(temp_dir))

                # geojson, kmz and kml
                elif ext in all_extentions[-3:]:
                                                      
                    if ext == '.geojson':
                        
                        geojson_file = self.standardize_geojson(self.vector_file, Path(temp_dir))
                                    
                    elif ext == '.kmz':

                        # decompress kmz to kml
                        kml_file = self.extract_kmz(self.vector_file, Path(temp_dir))
                        
                        geojson_file = self.convert_kml_to_geojson_custom(kml_file)

                    else:
                        geojson_file = self.convert_kml_to_geojson_custom(self.vector_file)
    
        except Exception as e:
            print(f"Error reading {self.vector_file}: {e}")

        return geojson_file



# Usage
boundary_file = '../.kml or kmz or any form of boundary file'

# Implementation
from boundary_processor import vector_converter

# process the kml or any other file input into geojson
geojson_file = vector_converter(boundary_file)
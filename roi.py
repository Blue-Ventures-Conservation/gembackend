import ee
from typing import Dict, List, Tuple
from project import tile_timeout
from assets import make_export, asset_dl_timeout

buffers = {
    '1 km': 1000, '2.5 km': 2500, '5 km': 5000, '7.5 km': 7500,
    '10 km': 10000, '15 km': 15000, '20 km': 20000
}
mangroves_scale = 30
mangroves_max_pixels = 1e13

def known_mangroves() -> ee.Image:
    giri = ee.ImageCollection("LANDSAT/MANGROVE_FORESTS").mean()
    gmw2020 = ee.ImageCollection("projects/sat-io/open-datasets/GMW/annual-extent/GMW_MNG_2020").mean()
    gmw = ee.Image("projects/earthengine-legacy/assets/projects/sat-io/open-datasets/GMW/union/gmw_v3_mng_union")
    return giri.blend(gmw).blend(gmw2020)

# poly here should be the dict equivalent of a geojson polygon
def coastline(roi_poly: ee.Geometry) -> ee.Geometry:
    mainlands = ee.FeatureCollection('projects/sat-io/open-datasets/shoreline/mainlands')
    big_islands = ee.FeatureCollection('projects/sat-io/open-datasets/shoreline/big_islands')
    small_islands = ee.FeatureCollection('projects/sat-io/open-datasets/shoreline/small_islands')
    # use the roi to clip the world boundary polygons
    area = mainlands.merge(big_islands).merge(small_islands).filterBounds(roi_poly)

    # convert the geometries to a coordinate list
    area_coords = ee.Geometry.MultiPolygon(area.geometry().geometries()).dissolve().coordinates().flatten()
    # use the coordinates to create a sting geometry
    area_point = ee.Geometry.MultiPoint(area_coords)
    
    # select points in roi and convert to coordinate list
    return area_point.intersection(roi_poly, ee.ErrorMargin(1))

def best_buffer(poly: dict, excludes: List[dict]) -> int:
    sums = area_chart(poly, excludes)["sums"]
    vals = sums["vals"]
    keys = sums["keys"]
    mval = 0.99 * vals[len(vals)-1]
    
    best = len(keys) - 1
    for i, v in enumerate(vals):
        if v >= mval:
            best = i
            break
    
    return list(buffers.values())[best]

def area_chart(poly: dict, excludes: List[dict]) -> Dict[str, dict]:
    mang = known_mangroves()
    roi = ee.Geometry(poly)
    
    excludeGeoms = []
    for exclude in excludes:
        excludeGeoms.append(ee.Geometry(exclude))
    
    def clipGeom(cst: ee.Geometry, buf: int) -> ee.Geometry:
        buffed = cst.buffer(buf)
        for excl in excludeGeoms:
            buffed = buffed.difference(excl)
        
        return buffed.intersection(roi)
    
    coast = coastline(roi).simplify(1000)
    # create an image collection of various buffered mangroves, using the distance list
    mangrove_buff = ee.Image(0) \
        .addBands(ee.Image.pixelArea().updateMask(mang.clip(clipGeom(coast, 1000))).rename(['1'])) \
        .addBands(ee.Image.pixelArea().updateMask(mang.clip(clipGeom(coast, 2500))).rename(['2'])) \
        .addBands(ee.Image.pixelArea().updateMask(mang.clip(clipGeom(coast, 5000))).rename(['5'])) \
        .addBands(ee.Image.pixelArea().updateMask(mang.clip(clipGeom(coast, 7500))).rename(['7'])) \
        .addBands(ee.Image.pixelArea().updateMask(mang.clip(clipGeom(coast, 10000))).rename(['10'])) \
        .addBands(ee.Image.pixelArea().updateMask(mang.clip(clipGeom(coast, 15000))).rename(['15'])) \
        .addBands(ee.Image.pixelArea().updateMask(mang.clip(clipGeom(coast, 20000))).rename(['20']))
    
    bands = mangrove_buff.bandNames().slice(1, 8)
    mangrove_buff = mangrove_buff.select(bands)

    geom = roi
    for excl in excludeGeoms:
        geom = geom.difference(excl)
    
    sums = mangrove_buff.reduceRegion(
        reducer = ee.Reducer.sum(),
        geometry = geom,
        scale = mangroves_scale,
        maxPixels = mangroves_max_pixels,
        bestEffort = True
    ).getInfo()
    
    sums = dict(sorted(sums.items(), key=lambda x:x[1]))
    
    return {"sums": {"keys": list(sums.keys()), "vals": [int(x) for x in list(sums.values())]}, "buffers": {"keys": list(buffers.keys()), "vals": list(buffers.values())}}

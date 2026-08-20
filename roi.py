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

def geo_coords(geo: ee.Geometry) -> List[list]:
    return ee.Geometry(geo).coordinates()

# poly here should be the dict equivalent of a geojson polygon
def coastline(roi_poly: ee.Geometry) -> ee.Geometry:
    # mainlands = ee.FeatureCollection('projects/sat-io/open-datasets/shoreline/mainlands')
    # big_islands = ee.FeatureCollection('projects/sat-io/open-datasets/shoreline/big_islands')
    # small_islands = ee.FeatureCollection('projects/sat-io/open-datasets/shoreline/small_islands')
    # area = mainlands.merge(big_islands).merge(small_islands).filterBounds(roi_poly)
    s2Coast = ee.FeatureCollection('projects/sat-io/open-datasets/S2COAST-2023')
    narinda = ee.FeatureCollection('projects/gem-project-378721/assets/S2Coast_gapfill_Helodrano_Narinda')
    # use the roi to clip the world boundary polygons
    area = s2Coast.merge(narinda).filterBounds(roi_poly)
    
    # max edges for simplify is 2,000,000
    # we divide by twenty, because to split the coordinates up
    # we will have to create variables and call ee.List.slice()
    # which requires knowing the indices for the sublists
    # we could divide by 2,000,000, but we wouldn't know how many
    # variables to use, and I can't think of a way to push the slicing
    # logic onto the backend, so we'd have to ask for the number to be
    # sent to the frontend and do a loop, and that size() call is slow
    # so twenty is chosen which should be enough hopefully to divide
    # the data up below that number of edges for any one simplify call
    area_coords = ee.Geometry.MultiPoint(area.geometry().geometries().map(geo_coords).flatten()).coordinates()
    
    twentieth = area_coords.size().divide(20).int().add(1)
    
    simp = 200
    s1 = ee.Geometry.MultiPoint(area_coords.slice(0, twentieth)).simplify(simp).coordinates()
    s2 = ee.Geometry.MultiPoint(area_coords.slice(twentieth, twentieth.multiply(2))).simplify(simp).coordinates()
    s3 = ee.Geometry.MultiPoint(area_coords.slice(twentieth.multiply(2), twentieth.multiply(3))).simplify(simp).coordinates()
    s4 = ee.Geometry.MultiPoint(area_coords.slice(twentieth.multiply(3), twentieth.multiply(4))).simplify(simp).coordinates()
    s5 = ee.Geometry.MultiPoint(area_coords.slice(twentieth.multiply(4), twentieth.multiply(5))).simplify(simp).coordinates()
    s6 = ee.Geometry.MultiPoint(area_coords.slice(twentieth.multiply(5), twentieth.multiply(6))).simplify(simp).coordinates()
    s7 = ee.Geometry.MultiPoint(area_coords.slice(twentieth.multiply(6), twentieth.multiply(7))).simplify(simp).coordinates()
    s8 = ee.Geometry.MultiPoint(area_coords.slice(twentieth.multiply(7), twentieth.multiply(8))).simplify(simp).coordinates()
    s9 = ee.Geometry.MultiPoint(area_coords.slice(twentieth.multiply(8), twentieth.multiply(9))).simplify(simp).coordinates()
    s10 = ee.Geometry.MultiPoint(area_coords.slice(twentieth.multiply(9), twentieth.multiply(10))).simplify(simp).coordinates()
    s11 = ee.Geometry.MultiPoint(area_coords.slice(twentieth.multiply(10), twentieth.multiply(11))).simplify(simp).coordinates()
    s12 = ee.Geometry.MultiPoint(area_coords.slice(twentieth.multiply(11), twentieth.multiply(12))).simplify(simp).coordinates()
    s13 = ee.Geometry.MultiPoint(area_coords.slice(twentieth.multiply(12), twentieth.multiply(13))).simplify(simp).coordinates()
    s14 = ee.Geometry.MultiPoint(area_coords.slice(twentieth.multiply(13), twentieth.multiply(14))).simplify(simp).coordinates()
    s15 = ee.Geometry.MultiPoint(area_coords.slice(twentieth.multiply(14), twentieth.multiply(15))).simplify(simp).coordinates()
    s16 = ee.Geometry.MultiPoint(area_coords.slice(twentieth.multiply(15), twentieth.multiply(16))).simplify(simp).coordinates()
    s17 = ee.Geometry.MultiPoint(area_coords.slice(twentieth.multiply(16), twentieth.multiply(17))).simplify(simp).coordinates()
    s18 = ee.Geometry.MultiPoint(area_coords.slice(twentieth.multiply(17), twentieth.multiply(18))).simplify(simp).coordinates()
    s19 = ee.Geometry.MultiPoint(area_coords.slice(twentieth.multiply(18), twentieth.multiply(19))).simplify(simp).coordinates()
    s20 = ee.Geometry.MultiPoint(area_coords.slice(twentieth.multiply(19), twentieth.multiply(20))).simplify(simp).coordinates()
    
    # use the coordinates to create a sting geometry
    area_point = ee.Geometry.MultiPoint(ee.List([s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11, s12, s13, s14, s15, s16, s17, s18, s19, s20]).flatten())
    
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
    
    coast = coastline(roi)
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

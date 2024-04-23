import ee
import time
from typing import Dict, List, Tuple
from project import tile_timeout
from assets import make_export, asset_dl_timeout

buffers = {
    '1 km': 1000, '2.5 km': 2500, '5 km': 5000, '7.5 km': 7500, '10 km': 10000, '12.5 km': 12500,
    '15 km': 15000, '17.5 km': 17500, '20 km': 20000, '22.5 km': 22500, '25 km': 25000
}
default_indices = ["CMRI", "MMRI", "MNDWI", "SAVI"]
cloud_cover_limit = 15
tidal_zone = 1000
ls4_dataset = "LANDSAT/LT04/C02/T1_L2"
ls5_dataset = "LANDSAT/LT05/C02/T1_L2"
ls7_dataset = "LANDSAT/LE07/C02/T1_L2"
ls8_dataset = "LANDSAT/LC08/C02/T1_L2"
ls9_dataset = "LANDSAT/LC09/C02/T1_L2"
# B4, B5, B3 false color composite
ls_visual = {'bands': ['Near IR', 'Shortwave IR 1', 'Red'], 'min': 0, 'max': 0.27}

class NoContemporaryImages(Exception):
    pass

class NoHistoricalImages(Exception):
    pass

def ls_imagery_export(uid: str, vis: bool, roi: dict, buff_dist: int):
    try:
        hhot, hlot = hist_imagery(roi, buff_dist)
    except NoImages:
        raise NoHistoricalImages()
    
    try:
        chot, clot = cont_imagery(roi, buff_dist)
    except NoImages:
        raise NoContemporaryImages()

    if vis == True:
        hhot = hhot.visualize(bands = ls_visual['bands'], min = ls_visual['min'], max = ls_visual['max'])
        hlot = hlot.visualize(bands = ls_visual['bands'], min = ls_visual['min'], max = ls_visual['max'])
        chot = chot.visualize(bands = ls_visual['bands'], min = ls_visual['min'], max = ls_visual['max'])
        clot = clot.visualize(bands = ls_visual['bands'], min = ls_visual['min'], max = ls_visual['max'])
    
    coast = buffered_coastline(ee.Geometry(roi["polygon"]), buff_dist)
    
    hhot_task = make_export(uid, hhot, coast, "historical_high_tide")
    hlot_task = make_export(uid, hlot, coast, "historical_low_tide")
    chot_task = make_export(uid, chot, coast, "contemporary_high_tide")
    clot_task = make_export(uid, clot, coast, "contemporary_low_tide")
    
    return {
        "chot": chot_task,
        "clot": clot_task,
        "hhot": hhot_task,
        "hlot": hlot_task,
        "created_at": int(time.time()),
        "timeout": asset_dl_timeout
    }

def known_mangroves() -> ee.Image:
    giri = ee.ImageCollection("LANDSAT/MANGROVE_FORESTS").mean()
    gmw = ee.Image("projects/earthengine-legacy/assets/projects/sat-io/open-datasets/GMW/union/gmw_v3_mng_union")
    return giri.blend(gmw)

def buffered_coastline(roi_poly: ee.Geometry, buff_dist: int) -> ee.Geometry:
    coast = coastline(roi_poly)
    return coast.buffer(buff_dist).intersection(roi_poly)

# poly here should be the dict equivalent of a geojson polygon
def coastline(roi_poly: ee.Geometry) -> ee.Geometry:
    mainlands = ee.FeatureCollection('projects/sat-io/open-datasets/shoreline/mainlands')
    big_islands = ee.FeatureCollection('projects/sat-io/open-datasets/shoreline/big_islands')
    small_islands = ee.FeatureCollection('projects/sat-io/open-datasets/shoreline/small_islands')
    # use the roi to clip the world boundary polygons
    area = mainlands.merge(big_islands).merge(small_islands).filterBounds(roi_poly).geometry()

    def geom_coords(geo: ee.Geometry) -> ee.List:
        return ee.Geometry(geo).coordinates()
    
    # convert the geometries to a coordinate list
    area_coords = area.geometries().map(geom_coords).flatten()
    # use the coordinates to create a sting geometry
    area_point = ee.Geometry.MultiPoint(area_coords)
    
    # select points in roi and convert to coordinate list
    return area_point.intersection(roi_poly, ee.ErrorMargin(1))

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
    mangrove_buff = ee.Image(mang) \
        .addBands(ee.Image.pixelArea().updateMask(mang.clip(clipGeom(coast, 1000))).rename(['1'])) \
        .addBands(ee.Image.pixelArea().updateMask(mang.clip(clipGeom(coast, 2500))).rename(['2'])) \
        .addBands(ee.Image.pixelArea().updateMask(mang.clip(clipGeom(coast, 5000))).rename(['5'])) \
        .addBands(ee.Image.pixelArea().updateMask(mang.clip(clipGeom(coast, 7500))).rename(['7'])) \
        .addBands(ee.Image.pixelArea().updateMask(mang.clip(clipGeom(coast, 10000))).rename(['10'])) \
        .addBands(ee.Image.pixelArea().updateMask(mang.clip(clipGeom(coast, 15000))).rename(['15'])) \
        .addBands(ee.Image.pixelArea().updateMask(mang.clip(clipGeom(coast, 20000))).rename(['20']))
    
    bands = mangrove_buff.bandNames().slice(1, 9)
    mangrove_buff = mangrove_buff.select(bands)
    
    sums = mangrove_buff.reduceRegion(
        reducer = ee.Reducer.sum(),
        geometry = roi,
        scale = 30,
        maxPixels = 1e13,
        bestEffort = True
    ).getInfo()
    
    sums = dict(sorted(sums.items(), key=lambda x:x[1]))
    
    return {"sums": {"keys": list(sums.keys()), "vals": [int(x) for x in list(sums.values())]}, "buffers": {"keys": list(buffers.keys()), "vals": list(buffers.values())}}

def visualize_imagery(roi: dict, buff_dist: int) -> Dict[str, str]:
    try:
        hhot, hlot = hist_imagery(roi, buff_dist)
    except NoImages:
        raise NoHistoricalImages()
    
    try:
        chot, clot = cont_imagery(roi, buff_dist)
    except NoImages:
        raise NoContemporaryImages()
    
    chot_url = chot.getMapId(ls_visual)["tile_fetcher"].url_format
    clot_url = clot.getMapId(ls_visual)["tile_fetcher"].url_format
    hhot_url = hhot.getMapId(ls_visual)["tile_fetcher"].url_format
    hlot_url = hlot.getMapId(ls_visual)["tile_fetcher"].url_format
    
    return {
        "chot_url": chot_url,
        "clot_url": clot_url,
        "hhot_url": hhot_url,
        "hlot_url": hlot_url,
        "created_at": int(time.time()),
        "timeout": tile_timeout
    }

def chot_imagery(roi: dict, buff_dist: int) -> ee.Image:
    chot, _ = cont_imagery(roi, buff_dist)
    return chot

def clot_imagery(roi: dict, buff_dist: int) -> ee.Image:
    _, clot = cont_imagery(roi, buff_dist)
    return clot

def hhot_imagery(roi: dict, buff_dist: int) -> ee.Image:
    hhot, _ = hist_imagery(roi, buff_dist)
    return hhot

def hlot_imagery(roi: dict, buff_dist: int) -> ee.Image:
    _, hlot = hist_imagery(roi, buff_dist)
    return hlot

def cont_imagery(roi: dict, buff_dist: int) -> Tuple[ee.Image, ee.Image]:
    return get_imagery(buff_dist, roi.get("indices", default_indices), roi["polygon"], roi.get("excludes", []), roi["cont_year_start"], roi["cont_year_end"], roi["cont_month_start"], roi["cont_month_end"])
    
def hist_imagery(roi: dict, buff_dist: int) -> Tuple[ee.Image, ee.Image]:
    return get_imagery(buff_dist, roi.get("indices", default_indices), roi["polygon"], roi.get("excludes", []), roi["hist_year_start"], roi["hist_year_end"], roi["hist_month_start"], roi["hist_month_end"])

def cont_imagery_collection(roi: dict, buff_dist: int) -> Tuple[ee.ImageCollection, ee.Geometry, List[str]]:
    return get_imagery_collection(buff_dist, roi.get("indices", default_indices), roi["polygon"], roi.get("excludes", []), roi["cont_year_start"], roi["cont_year_end"], roi["cont_month_start"], roi["cont_month_end"])

def hist_imagery_collection(roi: dict, buff_dist: int) -> Tuple[ee.ImageCollection, ee.Geometry, List[str]]:
    return get_imagery_collection(buff_dist, roi.get("indices", default_indices), roi["polygon"], roi.get("excludes", []), roi["hist_year_start"], roi["hist_year_end"], roi["hist_month_start"], roi["hist_month_end"])
    
class NoImages(Exception):
    pass

def get_imagery_collection(buff_dist: int, indices: List[str], poly: dict, excludes: List[dict], year1: int, year2: int, month1: int, month2: int) -> Tuple[ee.ImageCollection, ee.Geometry, List[str]]:
    roi = ee.Geometry(poly)
    coast = coastline(roi)
    buffered_roi_poly = coast.buffer(buff_dist).intersection(roi)
    zone = coast.simplify(500).buffer(tidal_zone).simplify(500)
    
    ls4 = ls4_imagery(buffered_roi_poly, year1, year2, month1, month2)
    ls5 = ls5_imagery(buffered_roi_poly, year1, year2, month1, month2)
    # ls7 = ls7_imagery(buffered_roi_poly, year1, year2, month1, month2)
    ls8 = ls8_imagery(buffered_roi_poly, year1, year2, month1, month2)
    ls9 = ls9_imagery(buffered_roi_poly, year1, year2, month1, month2)
    
    # rename bands
    oli_imgs = ee.ImageCollection(ls8.merge(ls9)) \
            .select(['SR_B2','SR_B3','SR_B4','SR_B5','SR_B6','SR_B7','ST_B10','QA_PIXEL'], ['B1','B2','B3','B4','B5','B7','B6','pixel_qa'])
    
    # merge TM/ETM+ the collection
    tm_imgs = ee.ImageCollection(ls5.merge(ls4)) \
            .select(['SR_B1','SR_B2','SR_B3','SR_B4','SR_B5','SR_B7','ST_B6','QA_PIXEL'], ['B1','B2','B3','B4','B5','B7','B6','pixel_qa'])
    
    tm_imgs = tm_imgs.map(etm_to_oli)
    
    imgs = oli_imgs.merge(tm_imgs)
    
    img_count = imgs.size().getInfo()
    if img_count <= 0:
        raise NoImages()
    
    imgs = imgs.map(apply_scale_factors).map(fix_float).map(doubleOO).map(cloud_mask)
    imgs = tide_bands(shore_refl(imgs, zone, buffered_roi_poly))
    
    for exclude in excludes:
        buffered_roi_poly = buffered_roi_poly.difference(exclude)
    
    return imgs, buffered_roi_poly, indices
 
def get_imagery(buff_dist: int, indices: List[str], poly: dict, excludes: List[dict], year1: int, year2: int, month1: int, month2: int) -> Tuple[ee.Image, ee.Image]:
    imgs, buffered_roi_poly, indices = get_imagery_collection(buff_dist, indices, poly, excludes, year1, year2, month1, month2)
    return mosaic_indices(imgs, buffered_roi_poly, indices)
 
def mosaic_indices(imgs: ee.ImageCollection, buffered_roi: ee.Geometry, indices: List[str]) -> Tuple[ee.Image, ee.Image]:
    high_tide = ee.ImageCollection(imgs).qualityMosaic("MNDWI").select(['B1','B2','B3','B4','B5','B6','B7']).clip(buffered_roi)
    low_tide = ee.ImageCollection(imgs).qualityMosaic("inv_MNDWI").select(['B1','B2','B3','B4','B5','B6','B7']).clip(buffered_roi)
    
    known_indices = []
    
    for idx in indices:
        if idx == 'CMRI':
            high_tide = add_cmri(high_tide)
            low_tide = add_cmri(low_tide)
            known_indices.append('CMRI')
        elif idx == 'MMRI':
            high_tide = add_mmri(high_tide)
            low_tide = add_mmri(low_tide)
            known_indices.append('MMRI')
        elif idx == 'MNDWI':
            high_tide = add_mndwi(high_tide)
            low_tide = add_mndwi(low_tide)
            known_indices.append('MNDWI')
        elif idx == 'SAVI':
            high_tide = add_savi(high_tide)
            low_tide = add_savi(low_tide)
            known_indices.append('SAVI')
    
    # rename bands to human friendly names and ditch B6 (heat/LWIR)
    current_bands = ['B1','B2','B3','B4','B5','B7'] + known_indices
    renamed_bands = ['Blue', 'Green', 'Red', 'Near IR', 'Shortwave IR 1', 'Shortwave IR 2'] + known_indices
    high_tide = high_tide.select(current_bands, renamed_bands)
    low_tide = low_tide.select(current_bands, renamed_bands)
    
    return high_tide.float(), low_tide.float()

def ls4_imagery(poly: ee.Geometry, year1: int, year2: int, month1: int, month2: int) -> ee.ImageCollection:
    return filtered_ls(ls4_dataset, poly, year1, year2, month1, month2)

def ls5_imagery(poly: ee.Geometry, year1: int, year2: int, month1: int, month2: int) -> ee.ImageCollection:
    return filtered_ls(ls5_dataset, poly, year1, year2, month1, month2)

def ls7_imagery(poly: ee.Geometry, year1: int, year2: int, month1: int, month2: int) -> ee.ImageCollection:
    return filtered_ls(ls7_dataset, poly, year1, year2, month1, month2)

def ls8_imagery(poly: ee.Geometry, year1: int, year2: int, month1: int, month2: int) -> ee.ImageCollection:
    return filtered_ls(ls8_dataset, poly, year1, year2, month1, month2)

def ls9_imagery(poly: ee.Geometry, year1: int, year2: int, month1: int, month2: int) -> ee.ImageCollection:
    return filtered_ls(ls9_dataset, poly, year1, year2, month1, month2)

def filtered_ls(dataset: str, poly: ee.Geometry, year1: int, year2: int, month1: int, month2: int) -> ee.ImageCollection:
    return ee.ImageCollection(dataset).filterBounds(poly) \
        .filterMetadata("CLOUD_COVER", "not_greater_than", cloud_cover_limit) \
        .filterDate(f'{year1}-01-01', f'{year2}-12-31') \
        .filter(ee.Filter.calendarRange(month1, month2, "month")) # handles wrapping if month1 < month2
    
def etm_to_oli(img: ee.Image) -> ee.Image:
    itcps = ee.Image.constant([0.0003, 0.0088, 0.0061, 0.0412, 0.0254, 0.0172]).multiply(10000)
    slopes = ee.Image.constant([0.8474, 0.8483, 0.9047, 0.8462, 0.8937, 0.9071])
    return img.select(['B1','B2','B3','B4','B5','B7']).multiply(slopes) \
            .add(itcps).round().toShort().addBands(img.select('B6', 'pixel_qa'))

def apply_scale_factors(img: ee.Image) -> ee.Image:
    opticalBands = img.select(['B1','B2','B3','B4','B5','B7']).multiply(0.0000275).add(-0.2)
    thermalBand = img.select(['B6']).multiply(0.00341802).add(149.0)
    return img.addBands(opticalBands, None, True).addBands(thermalBand, None, True)

def fix_float(img: ee.Image) -> ee.Image:
    specCast = img.select(['B1','B2','B3','B4','B5','B7']).cast({'B1':'float', 'B2': 'float', 'B3': 'float', 'B4': 'float', 'B5': 'float', 'B7': 'float'})
    return img.addBands(specCast, None, True)

def doubleOO(img: ee.Image) -> ee.Image:
    clamped = img.select(['B5']).clamp(0, 1)
    return clamped.addBands(img.select(['B1','B2','B3','B4','B7','B6', 'pixel_qa']))

def cloud_mask(img: ee.Image) -> ee.Image:
    # Bits 3 and 5 are cloud shadow and cloud, respectively.
    cloudShadowBitMask = (1 << 3)
    cloudsBitMask = (1 << 5)
    # Get the pixel QA band.
    qa = img.select('pixel_qa')
    # Both flags should be set to zero, indicating clear conditions.
    mask = qa.bitwiseAnd(cloudShadowBitMask).eq(0).And(qa.bitwiseAnd(cloudsBitMask).eq(0))
    kernel = ee.Kernel.gaussian(radius = 10)
    opened = mask.focalMin(kernel = kernel, iterations = 1)
    return img.updateMask(opened)

def shore_refl(imgs: ee.ImageCollection, zone: ee.Geometry, poly: ee.Geometry) -> ee.ImageCollection:
    # import the PLASAT dataset and create an land mask
    land_mask = ee.ImageCollection('JAXA/ALOS/PALSAR/YEARLY/SAR') \
            .filter(ee.Filter.date('2017-01-01', '2018-01-01')) \
            .mosaic().clip(poly) \
            .select('qa').eq(50)
    
    def mndwi_map(img: ee.Image) -> ee.Image:
        mndwi = produce_mndwi(img)
        # use the MODIS land/water mask and cloud mask to mask out the land
        masked_mndwi = mndwi.updateMask(land_mask)
        # reduce the image to the buffered shoreline, calculating a MNDWI
        cum_val = masked_mndwi.reduceRegion(
            reducer = ee.Reducer.mean(),
            geometry = zone,
            scale = 100,
            maxPixels = 1e15,
            bestEffort = True,
            tileScale = 16
        ).get('MNDWI')
        
        # input that value into the image metadata as the property 'MNDWI'
        return img.set('MNDWI', ee.Number(cum_val))
    
    def ndwi_map(img: ee.Image) -> ee.Image:
        ndwi = produce_ndwi(img)
        # use the MODIS land/water mask and cloud mask to mask out the land
        masked_ndwi = ndwi.updateMask(land_mask)
        # reduce the image to the buffered shoreline, calculating a NDWI
        cum_val = masked_ndwi.reduceRegion(
            reducer = ee.Reducer.mean(),
            geometry = zone,
            scale = 100,
            maxPixels = 1e15,
            bestEffort = True,
            tileScale = 16
        ).get('NDWI')
        
        # input that value into the image metadata as the property 'NDWI'
        return img.set('NDWI', ee.Number(cum_val))
    
    
    m = ee.ImageCollection(imgs).map(mndwi_map).map(ndwi_map)
    
    return m.filter(ee.Filter.gte("MNDWI", -1.0))

def tide_bands(imgs: ee.ImageCollection) -> ee.ImageCollection:
    # add a band to each image called MNDWI (created from the shoreRefl function)
    def mndwi_band(img: ee.Image) -> ee.Image:
        return img.addBands(img.metadata("MNDWI")).addBands(img.metadata("NDWI"))
    # create an inverse MNDWI to be used for high-tide conditions
    def inv_mndwi(img: ee.Image) -> ee.Image:
        return img.set("inv_MNDWI", ee.Number(img.get("MNDWI")).multiply(-1)).set("inv_NDWI", ee.Number(img.get("NDWI")).multiply(-1))
    # create an inverse MNDWI band for high-tide conditions
    def inv_mndwi_band(img: ee.Image) -> ee.Image:
        return img.addBands(img.metadata("inv_MNDWI")).addBands(img.metadata("inv_NDWI"))
    
    return imgs.map(mndwi_band).map(inv_mndwi).map(inv_mndwi_band)

#
# We don't use normalizedDifference from the API because it affects classification poorly for some reason...
#

def add_cmri(img: ee.Image) -> ee.Image:
    return img.addBands(produce_ndvi(img).subtract(produce_mndwi(img)).rename('CMRI'))

def add_mndwi(img: ee.Image) -> ee.Image:
    return img.addBands(produce_mndwi(img))

def add_mmri(img: ee.Image) -> ee.Image:
    ndvi = produce_ndvi(img).abs()
    mndwi = produce_mndwi(img).abs()
    return img.addBands(mndwi.subtract(ndvi).divide(mndwi.add(ndvi)).rename(['MMRI']))

def add_savi(img: ee.Image) -> ee.Image:
    return img.addBands(produce_savi(img))

def produce_ndvi(img: ee.Image) -> ee.Image:
    return img.expression('(B4 - B3)/(B4 + B3)', {'B4': img.select('B4'), 'B3': img.select('B3')}).rename(['NDVI'])

def produce_mndwi(img: ee.Image) -> ee.Image:
    return img.expression('(B2 - B5)/(B2 + B5)', {'B2': img.select('B2'), 'B5': img.select('B5')}).rename(['MNDWI'])

def produce_ndwi(img: ee.Image) -> ee.Image:
    return img.expression('(B2 - B4)/(B2 + B4)', {'B2': img.select('B2'), 'B4': img.select('B4')}).rename(['NDWI'])

def produce_savi(img: ee.Image) -> ee.Image:
    return img.select('B4').subtract(img.select('B3')).divide(img.select('B4').add(img.select('B3')).add(0.5)).multiply(1.5).rename(['SAVI'])

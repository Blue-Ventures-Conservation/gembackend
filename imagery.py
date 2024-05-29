import ee
import time
from typing import Callable, Dict, List, Tuple
from project import tile_timeout
from assets import make_export, asset_dl_timeout
from roi import coastline

default_cloud_limit = 15  # percent
default_tidal_zone = 1000 # meters
default_indices = ["CMRI", "MMRI", "MNDWI", "SAVI"]
# B4, B5, B3 false color composite
imagery_vis = {'bands': ['Near IR', 'Shortwave IR 1', 'Red'], 'min': 0, 'max': 0.27}

ls4_dataset = "LANDSAT/LT04/C02/T1_L2"
ls5_dataset = "LANDSAT/LT05/C02/T1_L2"
ls7_dataset = "LANDSAT/LE07/C02/T1_L2"
ls8_dataset = "LANDSAT/LC08/C02/T1_L2"
ls9_dataset = "LANDSAT/LC09/C02/T1_L2"
ls_scale = 30
ls_qa_pixel = "QA_PIXEL"
ls_cloud_property = "CLOUD_COVER"
ls_tir_rename = 'Heat'
oli_bands = ['SR_B2','SR_B3','SR_B4','SR_B5','SR_B6','SR_B7','ST_B10']
etm_bands = ['SR_B1','SR_B2','SR_B3','SR_B4','SR_B5','SR_B7','ST_B6']

s2_dataset = "COPERNICUS/S2_SR_HARMONIZED"
s2_start_year = 2018
s2_start_month = 12
s2_scale = 10
s2_qa_pixel = "QA60"
s2_cloud_property = "CLOUDY_PIXEL_PERCENTAGE"
s2_bands = ['B2','B3','B4','B8','B11','B12']
s2_cloudscore_band = 'cs'

# temp names used for calculating spectral indices
optical_bands = ['B1','B2','B3','B4','B5','B7']

# names to be shown in the UI on the frontend
human_bands = ['Blue', 'Green', 'Red', 'Near IR', 'Shortwave IR 1', 'Shortwave IR 2']

class NoImages(Exception):
    pass

class NoContemporaryImages(Exception):
    pass

class NoHistoricalImages(Exception):
    pass

def visualize_imagery(roi: dict, buff_dist: int) -> Dict[str, str]:
    try:
        hhot, hlot, _ = hist_imagery(roi, buff_dist)
    except NoImages:
        raise NoHistoricalImages()
    
    try:
        chot, clot, _ = cont_imagery(roi, buff_dist)
    except NoImages:
        raise NoContemporaryImages()
    
    chot_url = chot.getMapId(imagery_vis)["tile_fetcher"].url_format
    clot_url = clot.getMapId(imagery_vis)["tile_fetcher"].url_format
    hhot_url = hhot.getMapId(imagery_vis)["tile_fetcher"].url_format
    hlot_url = hlot.getMapId(imagery_vis)["tile_fetcher"].url_format
    
    return {
        "chot_url": chot_url,
        "clot_url": clot_url,
        "hhot_url": hhot_url,
        "hlot_url": hlot_url,
        "created_at": int(time.time()),
        "timeout": tile_timeout
    }

def buffered_coastline(roi_poly: ee.Geometry, buff_dist: int, excludes: List[dict]) -> ee.Geometry:
    coast = coastline(roi_poly)
    buffed = coast.buffer(buff_dist).intersection(roi_poly)
    for exclude in excludes:
        buffed = buffed.difference(ee.Geometry(excludes))
    
    return buffed

def imagery_export(uid: str, vis: bool, roi: dict, buff_dist: int):
    try:
        hhot, hlot, scale = hist_imagery(roi, buff_dist)
    except NoImages:
        raise NoHistoricalImages()
    
    try:
        chot, clot, scale = cont_imagery(roi, buff_dist)
    except NoImages:
        raise NoContemporaryImages()
    
    if vis == True:
        hhot = hhot.visualize(bands = imagery_vis['bands'], min = imagery_vis['min'], max = imagery_vis['max'])
        hlot = hlot.visualize(bands = imagery_vis['bands'], min = imagery_vis['min'], max = imagery_vis['max'])
        chot = chot.visualize(bands = imagery_vis['bands'], min = imagery_vis['min'], max = imagery_vis['max'])
        clot = clot.visualize(bands = imagery_vis['bands'], min = imagery_vis['min'], max = imagery_vis['max'])
    
    coast = buffered_coastline(ee.Geometry(roi["polygon"]), buff_dist, roi.get("excludes", []))
    
    hhot_task = make_export(uid, hhot, coast, "historical_high_tide", scale)
    hlot_task = make_export(uid, hlot, coast, "historical_low_tide", scale)
    chot_task = make_export(uid, chot, coast, "contemporary_high_tide", scale)
    clot_task = make_export(uid, clot, coast, "contemporary_low_tide", scale)
    
    return {
        "chot": chot_task,
        "clot": clot_task,
        "hhot": hhot_task,
        "hlot": hlot_task,
        "created_at": int(time.time()),
        "timeout": asset_dl_timeout
    }

def should_use_s2(hist_year: int, hist_month: int) -> bool:
    return (hist_year > s2_start_year) or (hist_year == s2_start_year and hist_month >= s2_start_month)

def get_landsat(roi: dict) -> bool:
    return roi.get("force_landsat", True) or not should_use_s2(roi["hist_year_start"], roi["hist_month_start"])

def get_cloud_limit(roi: dict) -> int:
    return roi.get("cloud_limit", default_cloud_limit)

def get_tidal_zone(roi: dict) -> int:
    return roi.get("tidal_zone", default_tidal_zone)

def cont_imagery(roi: dict, buff_dist: int) -> Tuple[ee.Image, ee.Image, int]:
    return get_imagery(get_landsat(roi), buff_dist, roi.get("indices", default_indices), roi["polygon"], get_cloud_limit(roi), get_tidal_zone(roi), roi.get("excludes", []), roi["cont_year_start"], roi["cont_year_end"], roi["cont_month_start"], roi["cont_month_end"])
 
def hist_imagery(roi: dict, buff_dist: int) -> Tuple[ee.Image, ee.Image, int]:
    return get_imagery(get_landsat(roi), buff_dist, roi.get("indices", default_indices), roi["polygon"], get_cloud_limit(roi), get_tidal_zone(roi), roi.get("excludes", []), roi["hist_year_start"], roi["hist_year_end"], roi["hist_month_start"], roi["hist_month_end"])

def cont_imagery_collection(roi: dict, buff_dist: int) -> Tuple[ee.ImageCollection, ee.Geometry, List[str], int]:
    return get_imagery_collection(get_landsat(roi), buff_dist, roi.get("indices", default_indices), roi["polygon"], get_cloud_limit(roi), get_tidal_zone(roi), roi.get("excludes", []), roi["cont_year_start"], roi["cont_year_end"], roi["cont_month_start"], roi["cont_month_end"])

def hist_imagery_collection(roi: dict, buff_dist: int) -> Tuple[ee.ImageCollection, ee.Geometry, List[str], int]:
    return get_imagery_collection(get_landsat(roi), buff_dist, roi.get("indices", default_indices), roi["polygon"], get_cloud_limit(roi), get_tidal_zone(roi), roi.get("excludes", []), roi["hist_year_start"], roi["hist_year_end"], roi["hist_month_start"], roi["hist_month_end"])

def get_imagery_collection(landsat: bool, buff_dist: int, indices: List[str], poly: dict, cloud_limit: int, tidal_zone: int, excludes: List[dict], year1: int, year2: int, month1: int, month2: int) -> Tuple[ee.ImageCollection, ee.Geometry, List[str], int]:
    roi = ee.Geometry(poly)
    coast = coastline(roi)
    buffered_roi_poly = coast.buffer(buff_dist).intersection(roi)
    zone = coast.simplify(500).buffer(tidal_zone).simplify(500)
    
    images = None
    scale = None
    if landsat == True:
        images = get_landsat_imagery(buffered_roi_poly, cloud_limit, year1, year2, month1, month2)
        scale = ls_scale
    else:
        images = get_sentinel2_imagery(buffered_roi_poly, cloud_limit, year1, year2, month1, month2)
        scale = s2_scale
    
    for exclude in excludes:
        buffered_roi_poly = buffered_roi_poly.difference(exclude)
    
    images = tide_bands(shore_refl(images, zone, buffered_roi_poly, scale))
    
    return images, buffered_roi_poly, indices, scale

def get_landsat_imagery(buffered_roi: ee.Geometry, cloud_limit: int, year1: int, year2: int, month1: int, month2: int) -> ee.ImageCollection:
    ls4 = ls4_imagery(buffered_roi, cloud_limit, year1, year2, month1, month2)
    ls5 = ls5_imagery(buffered_roi, cloud_limit, year1, year2, month1, month2)
    ls7 = ls7_imagery(buffered_roi, cloud_limit, year1, year2, month1, month2)
    ls8 = ls8_imagery(buffered_roi, cloud_limit, year1, year2, month1, month2)
    ls9 = ls9_imagery(buffered_roi, cloud_limit, year1, year2, month1, month2)
    
    renames = ee.List(optical_bands).cat([ls_tir_rename, ls_qa_pixel])
    
    # rename bands
    oli_imgs = ee.ImageCollection(ls8.merge(ls9)) \
            .select(ee.List(oli_bands).add(ls_qa_pixel), renames)
    
    # merge TM/ETM+ the collection
    tm_imgs = ee.ImageCollection(ls7.merge(ls5.merge(ls4))) \
            .select(ee.List(etm_bands).add(ls_qa_pixel), renames).map(etm_to_oli)
    
    imgs = oli_imgs.merge(tm_imgs)
    
    img_count = imgs.size().getInfo()
    if img_count <= 0:
        raise NoImages()
    
    swir1 = ee.String(optical_bands[4])
    return clamp_band(imgs.map(ls_scale_factors).map(fix_float), swir1, renames).map(ls_cloud_mask)

def get_sentinel2_imagery(buffered_roi: ee.Geometry, cloud_limit: int, year1: int, year2: int, month1: int, month2: int) -> ee.ImageCollection:
    s2 = sentinel2_imagery(buffered_roi, cloud_limit, year1, year2, month1, month2)
    
    renames = ee.List(optical_bands).add(s2_qa_pixel)
    
    return s2_cloud_mask(ee.ImageCollection(s2).select(ee.List(s2_bands).add(s2_qa_pixel), renames).map(s2_scale_factors))

def get_imagery(landsat: bool, buff_dist: int, indices: List[str], poly: dict, cloud_limit: int, tidal_zone: int, excludes: List[dict], year1: int, year2: int, month1: int, month2: int) -> Tuple[ee.Image, ee.Image, int]:
    imgs, buf_excl_roi, indices, scale = get_imagery_collection(landsat, buff_dist, indices, poly, cloud_limit, tidal_zone, excludes, year1, year2, month1, month2)
    return mosaic_indices(imgs, buf_excl_roi, indices, scale)

def mosaic_indices(imgs: ee.ImageCollection, buffered_excluded_roi: ee.Geometry, indices: List[str], scale: int) -> Tuple[ee.Image, ee.Image, int]:
    high_tide = ee.ImageCollection(imgs).qualityMosaic("MNDWI").select(optical_bands).clip(buffered_excluded_roi)
    low_tide = ee.ImageCollection(imgs).qualityMosaic("inv_MNDWI").select(optical_bands).clip(buffered_excluded_roi)
    
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
    
    current_bands = optical_bands + known_indices
    renamed_bands = human_bands + known_indices
    high_tide = high_tide.select(current_bands, renamed_bands)
    low_tide = low_tide.select(current_bands, renamed_bands)
    
    return high_tide.float(), low_tide.float(), scale

def sentinel2_imagery(poly: ee.Geometry, cloud_limit: int, year1: int, year2: int, month1: int, month2: int) -> ee.ImageCollection:
    return filter_collection(s2_dataset, poly, s2_cloud_property, cloud_limit, year1, year2, month1, month2)

def s2_scale_factors(img: ee.Image) -> ee.Image:
    optics = img.select(optical_bands).divide(10000)
    return img.addBands(optics, None, True)

def s2_cloud_mask(imgs: ee.ImageCollection) -> ee.ImageCollection:
    return imgs.linkCollection(ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED'), [s2_cloudscore_band]).map(s2_cloud_filter)

def s2_cloud_filter(img: ee.Image) -> ee.Image:
    return img.updateMask(img.select(s2_cloudscore_band).gte(0.60))

def ls4_imagery(poly: ee.Geometry, cloud_limit: int, year1: int, year2: int, month1: int, month2: int) -> ee.ImageCollection:
    return filter_collection(ls4_dataset, poly, ls_cloud_property, cloud_limit, year1, year2, month1, month2)

def ls5_imagery(poly: ee.Geometry, cloud_limit: int, year1: int, year2: int, month1: int, month2: int) -> ee.ImageCollection:
    return filter_collection(ls5_dataset, poly, ls_cloud_property, cloud_limit, year1, year2, month1, month2)

def ls7_imagery(poly: ee.Geometry, cloud_limit: int, year1: int, year2: int, month1: int, month2: int) -> ee.ImageCollection:
    justMay = month1 == 5 and month2 == 5
    normal = month1 < month2
    wrapping = month1 > month2
    monthRangeOverlaps = (wrapping and month1 <= 5) or (wrapping and month2 >= 5) or (normal and (month1 <= 5))
    monthsOverlap = justMay or monthRangeOverlaps
    overlaps = year1 < 2003 or (year1 == 2003 and monthsOverlap)
    if not overlaps:
        return ee.ImageCollection([])
    
    truncate = year2 > 2003 or (year2 == 2003 and monthsOverlap)
    
    ls7 = ee.ImageCollection(ls7_dataset)
    dateFiltered = ee.ImageCollection([])
    if truncate:
        fullYears = ee.ImageCollection([])
        if year1 < 2003:
            fullYears = ls7.filterDate(f'{year1}-01-01', f'2003-01-01') \
                    .filter(ee.Filter.calendarRange(month1, month2, "month"))

        truncated = ls7.filterDate(f'2003-01-01', f'2003-05-30') \
                .filter(ee.Filter.calendarRange(month1, 5, "month"))

        dateFiltered = truncated.merge(fullYears)
    else:
        y2 = year2 + 1
        dateFiltered = ls7.filterDate(f'{year1}-01-01', f'{y2}-01-01') \
                    .filter(ee.Filter.calendarRange(month1, month2, "month"))
    
    return dateFiltered.filterBounds(poly) \
        .filterMetadata("CLOUD_COVER", "not_greater_than", cloud_limit)

def ls8_imagery(poly: ee.Geometry, cloud_limit: int, year1: int, year2: int, month1: int, month2: int) -> ee.ImageCollection:
    return filter_collection(ls8_dataset, poly, ls_cloud_property, cloud_limit, year1, year2, month1, month2)

def ls9_imagery(poly: ee.Geometry, cloud_limit: int, year1: int, year2: int, month1: int, month2: int) -> ee.ImageCollection:
    return filter_collection(ls9_dataset, poly, ls_cloud_property, cloud_limit, year1, year2, month1, month2)

def filter_collection(dataset: str, poly: ee.Geometry, cloud_property: str, cloud_limit: int, year1: int, year2: int, month1: int, month2: int) -> ee.ImageCollection:
    y2 = year2 + 1
    return ee.ImageCollection(dataset).filterBounds(poly) \
        .filterMetadata(cloud_property, "not_greater_than", cloud_limit) \
        .filterDate(f'{year1}-01-01', f'{y2}-01-01') \
        .filter(ee.Filter.calendarRange(month1, month2, "month")) # handles wrapping if month1 < month2
 
def etm_to_oli(img: ee.Image) -> ee.Image:
    itcps = ee.Image.constant([0.0003, 0.0088, 0.0061, 0.0412, 0.0254, 0.0172]).multiply(10000)
    slopes = ee.Image.constant([0.8474, 0.8483, 0.9047, 0.8462, 0.8937, 0.9071])
    return img.select(optical_bands).multiply(slopes) \
            .add(itcps).round().toShort().addBands(img.select(ls_tir_rename, ls_qa_pixel))

def ls_scale_factors(img: ee.Image) -> ee.Image:
    optics = img.select(optical_bands).multiply(0.0000275).add(-0.2)
    thermals = img.select([ls_tir_rename]).multiply(0.00341802).add(149.0)
    return img.addBands(optics, None, True).addBands(thermals, None, True)

def fix_float(img: ee.Image) -> ee.Image:
    specCast = img.select(optical_bands).cast(ee.Dictionary.fromLists(optical_bands, ee.List.repeat('float', 6)))
    return img.addBands(specCast, None, True)

def clamp_band(images: ee.ImageCollection, clamp_band: str, all_bands: List[str]) -> ee.ImageCollection:
    def clampf(image: ee.Image) -> ee.Image:
        clamped = image.select(clamp_band).clamp(0, 1)
        return clamped.addBands(image.select(all_bands)) # bands are not overwritten
    
    return images.map(clampf)

def ls_cloud_mask(img: ee.Image) -> ee.Image:
    # Bits 3 and 5 are cloud shadow and cloud, respectively.
    cloudShadowBitMask = (1 << 3)
    cloudsBitMask = (1 << 5)
    # Get the pixel QA band.
    qa = img.select(ls_qa_pixel)
    # Both flags should be set to zero, indicating clear conditions.
    mask = qa.bitwiseAnd(cloudShadowBitMask).eq(0).And(qa.bitwiseAnd(cloudsBitMask).eq(0))
    kernel = ee.Kernel.gaussian(radius = 10)
    opened = mask.focalMin(kernel = kernel, iterations = 1)
    return img.updateMask(opened)

def shore_refl(imgs: ee.ImageCollection, zone: ee.Geometry, poly: ee.Geometry, scale: int) -> ee.ImageCollection:
    # import the PLASAT dataset and create an land mask
    land_mask = ee.ImageCollection('JAXA/ALOS/PALSAR/YEARLY/SAR') \
            .filter(ee.Filter.date('2017-01-01', '2018-01-01')) \
            .mosaic().clip(poly) \
            .select('qa').eq(50)
    
    ts = 16
    if scale < 20:
        ts = 1
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
            tileScale = ts,
        ).get('MNDWI')
        
        # input that value into the image metadata as the property 'MNDWI'
        return img.set('MNDWI', ee.Number(cum_val))
    
    m = ee.ImageCollection(imgs).map(mndwi_map)
    
    return tide_bands(m.filter(ee.Filter.gte("MNDWI", -1.0)))

def tide_bands(imgs: ee.ImageCollection) -> ee.ImageCollection:
    # add a band to each image called MNDWI (created from the shoreRefl function)
    def mndwi_band(img: ee.Image) -> ee.Image:
        return img.addBands(img.metadata("MNDWI"))
    # create an inverse MNDWI to be used for high-tide conditions
    def inv_mndwi(img: ee.Image) -> ee.Image:
        return img.set("inv_MNDWI", ee.Number(img.get("MNDWI")).multiply(-1))
    # create an inverse MNDWI band for high-tide conditions
    def inv_mndwi_band(img: ee.Image) -> ee.Image:
        return img.addBands(img.metadata("inv_MNDWI"))
    
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

import ee
import time
import math
from typing import Callable, Dict, List, Tuple
from project import tile_timeout
from assets import make_export, asset_dl_timeout
from roi import coastline, best_buffer

default_cloud_limit = 15  # percent
default_indices = ["CMRI", "MMRI", "MNDWI", "SAVI", "NDVI"]
# B4, B5, B3 false color composite
imagery_vis = {'bands': ['NIR', 'SWIR1', 'Red'], 'min': 0, 'max': 0.27}

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
bgr = ['Blue', 'Green', 'Red']
nir = ['NIR']
swirs = ['SWIR1', 'SWIR2']
ls_human_bands = bgr + nir + swirs
tide_band_names = ['MNDWI', 'inv_MNDWI']

s2_dataset = "COPERNICUS/S2_SR_HARMONIZED"
s2_start_year = 2018
s2_start_month = 12
s2_scale = 10
s2_qa_pixel = "QA60"
s2_cloud_property = "CLOUDY_PIXEL_PERCENTAGE"
s2_bands = ['B2','B3','B4','B5','B6','B7','B8','B8A','B11','B12']
s2_human_bands = bgr + ['RE1', 'RE2', 'RE3'] + nir + ['RE4'] + swirs

sar_start_year = 2014
sar_start_month = 10

class NoImages(Exception):
    pass

class NoContemporaryImages(Exception):
    pass

class NoHistoricalImages(Exception):
    pass

def visualize_imagery(roi: dict, buff_dist: int) -> Dict[str, str]:
    if buff_dist <= 0:
        buff_dist = best_buffer(roi["polygon"], roi["excludes"])
    
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
        "buff_dist": buff_dist,
        "created_at": int(time.time()),
        "timeout": tile_timeout
    }

def buffered_coastline(roi_poly: ee.Geometry, buff_dist: int, inland: bool, excludes: List[dict]) -> Tuple[ee.Geometry, ee.Geometry]:
    coast = coastline(roi_poly)
    buffed = coast.buffer(buff_dist).intersection(roi_poly)
    
    if inland == True:
        buffed = buffed.buffer(buff_dist)
    
    for exclude in excludes:
        buffed = buffed.difference(ee.Geometry(exclude))
    
    return buffed, coast

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
    
    buffered_roi, _ = buffered_coastline(ee.Geometry(roi["polygon"]), buff_dist, roi.get("inland_mang", False), roi.get("excludes", []))
    
    hhot_task = make_export(uid, hhot, buffered_roi, "historical_high_tide", scale)
    hlot_task = make_export(uid, hlot, buffered_roi, "historical_low_tide", scale)
    chot_task = make_export(uid, chot, buffered_roi, "contemporary_high_tide", scale)
    clot_task = make_export(uid, clot, buffered_roi, "contemporary_low_tide", scale)
    
    return {
        "chot": chot_task,
        "clot": clot_task,
        "hhot": hhot_task,
        "hlot": hlot_task,
        "created_at": int(time.time()),
        "timeout": asset_dl_timeout
    }

def should_use_s2(cont_start_year: int, cont_months: List[int], hist_start_year: int, hist_months: List[int]) -> bool:
    return fits_s2_range(cont_start_year, cont_months) and fits_s2_range(hist_start_year, hist_months)

def fits_s2_range(year: int, months: List[int]) -> bool:
    finalYearMaxLen = 13 - s2_start_month
    return (year > s2_start_year) or (year == s2_start_year and (len(months) >= finalYearMaxLen and months[0] >= s2_start_month))

def fits_sar_range(year: int, months: List[int]) -> bool:
    finalYearMaxLen = 13 - sar_start_month
    return (year > sar_start_year) or (year == sar_start_year and (len(months) >= finalYearMaxLen and months[0] >= sar_start_month))

def should_use_sar(roi: dict) -> bool:
    cont_months, hist_months = get_roi_months(roi)
    cont_start_year = roi["cont_year_start"]
    hist_start_year = roi["hist_year_start"]
    return fits_sar_range(cont_start_year, cont_months) and fits_sar_range(hist_start_year, hist_months)

def get_roi_months(roi: dict) -> Tuple[List[int], List[int]]:
    if "cont_months" in roi and "hist_months" in roi:
        return roi["cont_months"], roi["hist_months"]
    
    return get_months_from_range(roi["cont_month_start"], roi["cont_month_end"]), get_months_from_range(roi["hist_month_start"], roi["hist_month_end"])

def get_months_from_range(month_start: int, month_end: int) -> List[int]:
    months = []
    
    if month_start > month_end:
        for x in range(1, month_start):
            months.append(x)
        
        for y in range(month_end, 12):
            months.append(y)
    else: 
        for n in range(month_start, month_end):
            months.append(n)
    
    return months

def should_landsat(roi: dict, cont_months: List[int], hist_months: List[int]) -> bool:
    return roi.get("force_landsat", True) or not should_use_s2(roi["cont_year_start"], cont_months, roi["hist_year_start"], hist_months)

def get_cloud_limit(roi: dict) -> int:
    return roi.get("cloud_limit", default_cloud_limit)

def cont_imagery(roi: dict, buff_dist: int) -> Tuple[ee.Image, ee.Image, int]:
    cont_months, hist_months = get_roi_months(roi)
    return get_imagery(should_landsat(roi, cont_months, hist_months), buff_dist, roi.get("indices", default_indices), roi["polygon"], get_cloud_limit(roi), roi.get("inland_mang", False), roi.get("excludes", []), roi["cont_year_start"], roi["cont_year_end"], cont_months)
 
def hist_imagery(roi: dict, buff_dist: int) -> Tuple[ee.Image, ee.Image, int]:
    cont_months, hist_months = get_roi_months(roi)
    return get_imagery(should_landsat(roi, cont_months, hist_months), buff_dist, roi.get("indices", default_indices), roi["polygon"], get_cloud_limit(roi), roi.get("inland_mang", False), roi.get("excludes", []), roi["hist_year_start"], roi["hist_year_end"], hist_months)

def cont_imagery_collection(roi: dict, buff_dist: int) -> Tuple[ee.ImageCollection, ee.Geometry, List[str], int]:
    cont_months, hist_months = get_roi_months(roi)
    return get_imagery_collection(should_landsat(roi, cont_months, hist_months), buff_dist, roi.get("indices", default_indices), roi["polygon"], get_cloud_limit(roi), roi.get("inland_mang", False), roi.get("excludes", []), roi["cont_year_start"], roi["cont_year_end"], cont_months)

def hist_imagery_collection(roi: dict, buff_dist: int) -> Tuple[ee.ImageCollection, ee.Geometry, List[str], int]:
    cont_months, hist_months = get_roi_months(roi)
    return get_imagery_collection(should_landsat(roi, cont_months, hist_months), buff_dist, roi.get("indices", default_indices), roi["polygon"], get_cloud_limit(roi), roi.get("inland_mang", False), roi.get("excludes", []), roi["hist_year_start"], roi["hist_year_end"], hist_months)

def get_imagery_collection(landsat: bool, buff_dist: int, indices: List[str], poly: dict, cloud_limit: int, inland_mang: bool, excludes: List[dict], year1: int, year2: int, months: List[int]) -> Tuple[ee.ImageCollection, ee.Geometry, List[str], int]:
    roi_poly = ee.Geometry(poly)
    buffered_roi_poly, coast = buffered_coastline(roi_poly, buff_dist, inland_mang, excludes)
	
    murray = ee.ImageCollection('UQ/murray/Intertidal/v1_1/global_intertidal').mosaic()
    murray = murray.focalMin(1).focalMax(1)
	
    zone = murray.reduceToVectors(
        geometry = roi_poly,
        scale = 30,
        crs = murray.projection(),
        geometryType = 'polygon',
        eightConnected = False,
        bestEffort = True,
        maxPixels = 1e13,
    ).filter(ee.Filter.gt('count', 10)).geometry().simplify(75);
    
    images = None
    scale = None
    if landsat == True:
        images = get_landsat_imagery(buffered_roi_poly, cloud_limit, year1, year2, months, zone)
        scale = ls_scale
    else:
        images = get_sentinel2_imagery(buffered_roi_poly, cloud_limit, year1, year2, months, zone)
        scale = s2_scale
    
    return images, buffered_roi_poly, indices, scale

def get_landsat_imagery(buffered_roi: ee.Geometry, cloud_limit: int, year1: int, year2: int, months: List[int], tidal_zone: ee.Geometry) -> ee.ImageCollection:
    ls4 = ls4_imagery(buffered_roi, cloud_limit, year1, year2, months)
    ls5 = ls5_imagery(buffered_roi, cloud_limit, year1, year2, months)
    ls7 = ls7_imagery(buffered_roi, cloud_limit, year1, year2, months)
    ls8 = ls8_imagery(buffered_roi, cloud_limit, year1, year2, months)
    ls9 = ls9_imagery(buffered_roi, cloud_limit, year1, year2, months)
    
    renames = ee.List(ls_human_bands).cat([ls_tir_rename, ls_qa_pixel])
    
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
    
    swir1 = ee.String(ls_human_bands[4])
    imgs = clamp_band(imgs.map(ls_scale_factors).map(fix_float), swir1, renames)
    imgs = shore_refl(imgs, tidal_zone, buffered_roi, ls_scale)
    return imgs.map(ls_cloud_mask).select(ls_human_bands + tide_band_names)

def get_sentinel2_imagery(buffered_roi: ee.Geometry, cloud_limit: int, year1: int, year2: int, months: List[int], tidal_zone: ee.Geometry) -> ee.ImageCollection:
    s2 = sentinel2_imagery(buffered_roi, cloud_limit, year1, year2, months)
    
    renames = ee.List(s2_human_bands).add(s2_qa_pixel)
    imgs = ee.ImageCollection(s2).select(ee.List(s2_bands).add(s2_qa_pixel), renames).map(s2_scale_factors)
    imgs = shore_refl(imgs, tidal_zone, buffered_roi, s2_scale)
    return s2_cloud_mask(imgs).select(s2_human_bands + tide_band_names)

def get_imagery(landsat: bool, buff_dist: int, indices: List[str], poly: dict, cloud_limit: int, inland_mang: bool, excludes: List[dict], year1: int, year2: int, months: List[int]) -> Tuple[ee.Image, ee.Image, int]:
    imgs, buf_excl_roi, indices, scale = get_imagery_collection(landsat, buff_dist, indices, poly, cloud_limit, inland_mang, excludes, year1, year2, months)
    return mosaic_indices(imgs, buf_excl_roi, indices, scale)

def mosaic_indices(imgs: ee.ImageCollection, buffered_excluded_roi: ee.Geometry, indices: List[str], scale: int) -> Tuple[ee.Image, ee.Image, int]:
    high_tide = ee.ImageCollection(imgs).qualityMosaic("MNDWI")
    low_tide = ee.ImageCollection(imgs).qualityMosaic("inv_MNDWI")
    
    # slice off mndwi and inv_mndwi bands
    bnames = high_tide.bandNames().slice(0, -2)
    high_tide = high_tide.select(bnames).clip(buffered_excluded_roi)
    low_tide = low_tide.select(bnames).clip(buffered_excluded_roi)
    
    for idx in indices:
        if idx == 'CMRI':
            high_tide = add_cmri(high_tide)
            low_tide = add_cmri(low_tide)
        elif idx == 'MMRI':
            high_tide = add_mmri(high_tide)
            low_tide = add_mmri(low_tide)
        elif idx == 'MNDWI':
            high_tide = add_mndwi(high_tide)
            low_tide = add_mndwi(low_tide)
        elif idx == 'SAVI':
            high_tide = add_savi(high_tide)
            low_tide = add_savi(low_tide)
        elif idx == 'NDVI':
            high_tide = add_ndvi(high_tide)
            low_tide = add_ndvi(low_tide)
    
    return high_tide.float(), low_tide.float(), scale

def sentinel2_imagery(poly: ee.Geometry, cloud_limit: int, year1: int, year2: int, months: List[int]) -> ee.ImageCollection:
    return filter_collection(s2_dataset, poly, s2_cloud_property, cloud_limit, year1, year2, months)

def s2_scale_factors(img: ee.Image) -> ee.Image:
    optics = img.select(s2_human_bands).divide(10000)
    return img.addBands(optics, None, True)

def s2_cloud_mask(imgs: ee.ImageCollection) -> ee.ImageCollection:
    return imgs.linkCollection(ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED'), ['cs_cdf', 'cs']).map(s2_cloud_filter)

def s2_cloud_filter(img: ee.Image) -> ee.Image:
    return img.updateMask(img.select('cs_cdf').gte(0.70).And(img.select('cs').gte(0.70)))

def ls4_imagery(poly: ee.Geometry, cloud_limit: int, year1: int, year2: int, months: List[int]) -> ee.ImageCollection:
    return filter_collection(ls4_dataset, poly, ls_cloud_property, cloud_limit, year1, year2, months)

def ls5_imagery(poly: ee.Geometry, cloud_limit: int, year1: int, year2: int, months: List[int]) -> ee.ImageCollection:
    return filter_collection(ls5_dataset, poly, ls_cloud_property, cloud_limit, year1, year2, months)

def ls7_imagery(poly: ee.Geometry, cloud_limit: int, year1: int, year2: int, months: List[int]) -> ee.ImageCollection:
    if len(months) <= 0:
        return ee.ImageCollection([])
    
    monthsOverlap = months[0] <= 5
    overlaps = year1 < 2003 or (year1 == 2003 and monthsOverlap)
    if not overlaps:
        return ee.ImageCollection([])
    
    truncate = year2 > 2003 or (year2 == 2003 and monthsOverlap)
    
    ls7 = ee.ImageCollection(ls7_dataset)
    dateFiltered = ee.ImageCollection([])
    if truncate:
        fullYears = ee.ImageCollection([])
        if year1 < 2003:
            fullYears = ls7.filterDate(f'{year1}-01-01', f'2003-01-01')

        truncated = ls7.filterDate(f'2003-01-01', f'2003-05-30')

        dateFiltered = truncated.merge(fullYears)
    else:
        y2 = year2 + 1
        dateFiltered = ls7.filterDate(f'{year1}-01-01', f'{y2}-01-01')
    
    images = dateFiltered.filterBounds(poly) \
        .filter(ee.Filter.gt("CLOUD_COVER", cloud_limit).Not())
    
    return filter_months(images, months)

def ls8_imagery(poly: ee.Geometry, cloud_limit: int, year1: int, year2: int, months: List[int]) -> ee.ImageCollection:
    return filter_collection(ls8_dataset, poly, ls_cloud_property, cloud_limit, year1, year2, months)

def ls9_imagery(poly: ee.Geometry, cloud_limit: int, year1: int, year2: int, months: List[int]) -> ee.ImageCollection:
    return filter_collection(ls9_dataset, poly, ls_cloud_property, cloud_limit, year1, year2, months)

def filter_months(images: ee.ImageCollection, months: List[int]) -> ee.ImageCollection:
    filters = []
    for month in months:
        filters.append(ee.Filter.calendarRange(month, month, 'month'))
    
    return images.filter(ee.Filter.Or(*filters))

def filter_collection(dataset: str, poly: ee.Geometry, cloud_property: str, cloud_limit: int, year1: int, year2: int, months: List[int]) -> ee.ImageCollection:
    y2 = year2 + 1
    images = ee.ImageCollection(dataset).filterBounds(poly) \
        .filter(ee.Filter.gt(cloud_property, cloud_limit).Not()) \
        .filterDate(f'{year1}-01-01', f'{y2}-01-01')
    
    return filter_months(images, months)
 
def etm_to_oli(img: ee.Image) -> ee.Image:
    itcps = ee.Image.constant([0.0003, 0.0088, 0.0061, 0.0412, 0.0254, 0.0172]).multiply(10000)
    slopes = ee.Image.constant([0.8474, 0.8483, 0.9047, 0.8462, 0.8937, 0.9071])
    return img.select(ls_human_bands).multiply(slopes) \
            .add(itcps).round().toShort().addBands(img.select(ls_tir_rename, ls_qa_pixel))

def ls_scale_factors(img: ee.Image) -> ee.Image:
    optics = img.select(ls_human_bands).multiply(0.0000275).add(-0.2)
    thermals = img.select([ls_tir_rename]).multiply(0.00341802).add(149.0)
    return img.addBands(optics, None, True).addBands(thermals, None, True)

def fix_float(img: ee.Image) -> ee.Image:
    specCast = img.select(ls_human_bands).cast(ee.Dictionary.fromLists(ls_human_bands, ee.List.repeat('float', 6)))
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
            .filter(ee.Filter.date('2018-01-01', '2019-01-01')) \
            .mosaic().clip(poly) \
            .select('qa').eq(50)
    
    ts = 16
    if scale < 30:
        ts = 1
    def mndwi_map(img: ee.Image) -> ee.Image:
        mndwi = produce_mndwi(img)
        # use the MODIS land/water mask and cloud mask to mask out the land
        masked_mndwi = mndwi.updateMask(land_mask)
        # reduce the image to the buffered shoreline, calculating a MNDWI
        cumulative = masked_mndwi.reduceRegion(
            reducer = ee.Reducer.mean(),
            geometry = zone,
            scale = 100,
            maxPixels = 1e15,
            bestEffort = True,
            tileScale = ts,
        ).get('MNDWI')
        
        # input that value into the image metadata as the property 'MNDWI'
        cumulative = ee.Algorithms.If(cumulative, cumulative, -1)
        return img.set('MNDWI', ee.Number(cumulative))
    
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

def add_ndvi(img: ee.Image) -> ee.Image:
    return img.addBands(produce_ndvi(img))

def produce_ndvi(img: ee.Image) -> ee.Image:
    return img.expression('(B4 - B3)/(B4 + B3)', {'B4': img.select('NIR'), 'B3': img.select('Red')}).rename(['NDVI'])

def produce_mndwi(img: ee.Image) -> ee.Image:
    return img.expression('(B2 - B5)/(B2 + B5)', {'B2': img.select('Green'), 'B5': img.select('SWIR1')}).rename(['MNDWI'])

def produce_ndwi(img: ee.Image) -> ee.Image:
    return img.expression('(B2 - B4)/(B2 + B4)', {'B2': img.select('Green'), 'B4': img.select('NIR')}).rename(['NDWI'])

def produce_savi(img: ee.Image) -> ee.Image:
    return img.select('NIR').subtract(img.select('Red')).divide(img.select('NIR').add(img.select('Red')).add(0.5)).multiply(1.5).rename(['SAVI'])

def get_combined_sar_water_mask(roi: dict, buf_excl_roi: ee.Geometry) -> ee.Image:
    cont_months, hist_months = get_roi_months(roi)
    cont_mask = get_sar_water_mask(buf_excl_roi, roi["cont_year_start"], roi["cont_year_end"], cont_months)
    hist_mask = get_sar_water_mask(buf_excl_roi, roi["hist_year_start"], roi["hist_year_end"], hist_months)
    return cont_mask.add(hist_mask).gte(1)

def filter_sar_edges(img: ee.Image) -> ee.Image:
    vv = img.select('VV')
    pos_edge = vv.gte(1.0)
    neg_edge = vv.lte(-30.0)
    masked = img.mask().And(neg_edge.Not()).And(pos_edge.Not())
    return img.updateMask(masked)

def classifyWater(img: ee.Image) -> ee.Image:
    vv = img.select('VV')
    return vv.lt(-17).rename('Water')

# (mask out angles >= 45.23993) */
def maskAngLT452(image: ee.Image) -> ee.Image:
    ang = image.select(['angle'])
    return image.updateMask(ang.lt(45.23993)).set('system:time_start', image.get('system:time_start'))

# Function to mask out edges of images using angle.
# * (mask out angles <= 30.63993) */
def maskAngGT30(image: ee.Image) -> ee.Image:
    ang = image.select(['angle'])
    return image.updateMask(ang.gt(30.63993)).set('system:time_start', image.get('system:time_start'))
    
def get_sar_water_mask(buf_excl_roi: ee.Geometry, year1: int, year2: int, months: List[int]) -> ee.Image:
    y2 = year2 + 1
    s1 = ee.ImageCollection('COPERNICUS/S1_GRD') \
            .filterBounds(buf_excl_roi) \
            .filterDate(f'{year1}-01-01', f'{y2}-01-01') \
            .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV')) \
            .filter(ee.Filter.eq('instrumentMode', 'IW')) \
            .filter(ee.Filter.eq('resolution_meters', 10)) \
            .map(filter_sar_edges)
    
    s1 = filter_months(s1, months)
    s1 = s1.map(maskAngLT452).map(maskAngGT30).select('VV')
    s1 = s1.map(leeFilter).map(classifyWater)
    return s1.reduce(ee.Reducer.sum()).gt(1).add(1).eq(1)

# lee speckle filter implementation borrowed from:
# https://github.com/zibnix/gee_s1_ard/blob/main/javascript/speckle_filter.js#L2
def leeFilter(image: ee.Image) -> ee.Image:
    bandNames = image.bandNames().remove('angle')
    # S1-GRD images are multilooked 5 times in range
    enl = 5
    # Compute the speckle standard deviation
    eta = 1.0/math.sqrt(enl)
    eta = ee.Image.constant(eta)
    
    # MMSE estimator
    # Neighbourhood mean and variance
    oneImg = ee.Image.constant(1)
    
    reducers = ee.Reducer.mean().combine(
            reducer2 = ee.Reducer.variance(),
            sharedInputs = True
    )
    stats = image.select(bandNames).reduceNeighborhood(
            reducer = reducers,
            kernel = ee.Kernel.square(7/2, 'pixels'),
            optimization = 'window'
    )
    
    def add_mean(bandName: ee.String) -> ee.String:
        return ee.String(bandName).cat('_mean')
    
    def add_variance(bandName: ee.String) -> ee.String:
        return ee.String(bandName).cat('_variance')
    
    meanBand = bandNames.map(add_mean)
    varBand = bandNames.map(add_variance)
    
    z_bar = stats.select(meanBand)
    varz = stats.select(varBand)
    
    # Estimate weight 
    varx = (varz.subtract(z_bar.pow(2).multiply(eta.pow(2)))).divide(oneImg.add(eta.pow(2)))
    b = varx.divide(varz)
    
    # if b is negative set it to zero
    new_b = b.where(b.lt(0), 0)
    output = oneImg.subtract(new_b).multiply(z_bar.abs()).add(new_b.multiply(image.select(bandNames)))
    output = output.rename(bandNames).multiply(-1)
    return image.addBands(output, None, True)

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
        buffed = buffed.difference(ee.Geometry(exclude))
    
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

def should_use_s2(cont_start_year: int, cont_months: List[int], hist_start_year: int, hist_months: List[int]) -> bool:
    return fits_s2_range(cont_start_year, cont_months) and fits_s2_range(hist_start_year, hist_months)

def fits_s2_range(year: int, months: List[int]) -> bool:
    finalYearMaxLen = 13 - s2_start_month
    return (year > s2_start_year) or (year == s2_start_year and (len(months) >= finalYearMaxLen and months[0] >= s2_start_month))

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

def get_tidal_zone(roi: dict) -> int:
    return roi.get("tidal_zone", default_tidal_zone)

def cont_imagery(roi: dict, buff_dist: int) -> Tuple[ee.Image, ee.Image, int]:
    cont_months, hist_months = get_roi_months(roi)
    return get_imagery(should_landsat(roi, cont_months, hist_months), buff_dist, roi.get("indices", default_indices), roi["polygon"], get_cloud_limit(roi), get_tidal_zone(roi), roi.get("excludes", []), roi["cont_year_start"], roi["cont_year_end"], cont_months)
 
def hist_imagery(roi: dict, buff_dist: int) -> Tuple[ee.Image, ee.Image, int]:
    cont_months, hist_months = get_roi_months(roi)
    return get_imagery(should_landsat(roi, cont_months, hist_months), buff_dist, roi.get("indices", default_indices), roi["polygon"], get_cloud_limit(roi), get_tidal_zone(roi), roi.get("excludes", []), roi["hist_year_start"], roi["hist_year_end"], hist_months)

def cont_imagery_collection(roi: dict, buff_dist: int) -> Tuple[ee.ImageCollection, ee.Geometry, List[str], int]:
    cont_months, hist_months = get_roi_months(roi)
    return get_imagery_collection(should_landsat(roi, cont_months, hist_months), buff_dist, roi.get("indices", default_indices), roi["polygon"], get_cloud_limit(roi), get_tidal_zone(roi), roi.get("excludes", []), roi["cont_year_start"], roi["cont_year_end"], cont_months)

def hist_imagery_collection(roi: dict, buff_dist: int) -> Tuple[ee.ImageCollection, ee.Geometry, List[str], int]:
    cont_months, hist_months = get_roi_months(roi)
    return get_imagery_collection(should_landsat(roi, cont_months, hist_months), buff_dist, roi.get("indices", default_indices), roi["polygon"], get_cloud_limit(roi), get_tidal_zone(roi), roi.get("excludes", []), roi["hist_year_start"], roi["hist_year_end"], hist_months)

def get_imagery_collection(landsat: bool, buff_dist: int, indices: List[str], poly: dict, cloud_limit: int, tidal_zone: int, excludes: List[dict], year1: int, year2: int, months: List[int]) -> Tuple[ee.ImageCollection, ee.Geometry, List[str], int]:
    roi = ee.Geometry(poly)
    coast = coastline(roi)
    buffered_roi_poly = coast.buffer(buff_dist).intersection(roi)
    zone = coast.simplify(500).buffer(tidal_zone).simplify(500)
    
    images = None
    scale = None
    if landsat == True:
        images = get_landsat_imagery(buffered_roi_poly, cloud_limit, year1, year2, months, zone, excludes)
        scale = ls_scale
    else:
        images = get_sentinel2_imagery(buffered_roi_poly, cloud_limit, year1, year2, months, zone, excludes)
        scale = s2_scale
    
    return images, buffered_roi_poly, indices, scale

def get_landsat_imagery(buffered_roi: ee.Geometry, cloud_limit: int, year1: int, year2: int, months: List[int], tidal_zone: ee.Geometry, excludes: List[dict]) -> ee.ImageCollection:
    ls4 = ls4_imagery(buffered_roi, cloud_limit, year1, year2, months)
    ls5 = ls5_imagery(buffered_roi, cloud_limit, year1, year2, months)
    ls7 = ls7_imagery(buffered_roi, cloud_limit, year1, year2, months)
    ls8 = ls8_imagery(buffered_roi, cloud_limit, year1, year2, months)
    ls9 = ls9_imagery(buffered_roi, cloud_limit, year1, year2, months)
    
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
    
    for exclude in excludes:
        buffered_roi = buffered_roi.difference(exclude)
    
    swir1 = ee.String(optical_bands[4])
    imgs = clamp_band(imgs.map(ls_scale_factors).map(fix_float), swir1, renames)
    imgs = tide_bands(shore_refl(imgs, tidal_zone, buffered_roi, ls_scale))
    return imgs.map(ls_cloud_mask)

def get_sentinel2_imagery(buffered_roi: ee.Geometry, cloud_limit: int, year1: int, year2: int, months: List[int], tidal_zone: ee.Geometry, excludes: List[dict]) -> ee.ImageCollection:
    s2 = sentinel2_imagery(buffered_roi, cloud_limit, year1, year2, months)
    
    for exclude in excludes:
        buffered_roi = buffered_roi.difference(exclude)
    
    renames = ee.List(optical_bands).add(s2_qa_pixel)
    imgs = ee.ImageCollection(s2).select(ee.List(s2_bands).add(s2_qa_pixel), renames).map(s2_scale_factors)
    imgs = tide_bands(shore_refl(imgs, tidal_zone, buffered_roi, s2_scale))
    return s2_cloud_mask(imgs)

def get_imagery(landsat: bool, buff_dist: int, indices: List[str], poly: dict, cloud_limit: int, tidal_zone: int, excludes: List[dict], year1: int, year2: int, months: List[int]) -> Tuple[ee.Image, ee.Image, int]:
    imgs, buf_excl_roi, indices, scale = get_imagery_collection(landsat, buff_dist, indices, poly, cloud_limit, tidal_zone, excludes, year1, year2, months)
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

def sentinel2_imagery(poly: ee.Geometry, cloud_limit: int, year1: int, year2: int, months: List[int]) -> ee.ImageCollection:
    return filter_collection(s2_dataset, poly, s2_cloud_property, cloud_limit, year1, year2, months)

def s2_scale_factors(img: ee.Image) -> ee.Image:
    optics = img.select(optical_bands).divide(10000)
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
        .filterMetadata("CLOUD_COVER", "not_greater_than", cloud_limit)
    
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
        .filterMetadata(cloud_property, "not_greater_than", cloud_limit) \
        .filterDate(f'{year1}-01-01', f'{y2}-01-01')
    
    return filter_months(images, months)
 
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
    if scale < 30:
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

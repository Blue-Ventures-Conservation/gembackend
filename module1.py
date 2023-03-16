import ee
from typing import Dict, List, Tuple

buffers = {
    '1 km': 1000, '2.5 km': 2500, '5 km': 5000, '7.5 km': 7500, '10 km': 10000, '12.5 km': 12500,
    '15 km': 15000, '17.5 km': 17500, '20 km': 20000, '22.5 km': 22500, '25 km': 25000
}
cloudCoverLimit = 15
tidalZone = 1000
ls4_dataset = "LANDSAT/LT04/C02/T1_L2"
ls5_dataset = "LANDSAT/LT05/C02/T1_L2"
ls7_dataset = "LANDSAT/LE07/C02/T1_L2"
ls8_dataset = "LANDSAT/LC08/C02/T1_L2"
ls9_dataset = "LANDSAT/LC09/C02/T1_L2"

def known_mangroves() -> ee.Image:
    return ee.ImageCollection("LANDSAT/MANGROVE_FORESTS").reduce(ee.Reducer.mean())

def topo_dsm() -> ee.Image:
    dsm = ee.Image("JAXA/ALOS/AW3D30/V2_2").select("AVE_DSM").rename("elev")
    slp_img = ee.Terrain.slope(ee.Image(dsm).select("elev")).double().rename("slope")
    return dsm.addBands(slp_img)

def topo_mask(dsm: ee.Image, mangs: ee.Image) -> ee.Image:
    mang_elv = dsm.select('elev').updateMask(mangs).reduceRegion(
            reducer = ee.Reducer.percentile(percentiles = [99]),
            geometry = mangs.geometry(),
            scale = 30,
            maxPixels = 1e12,
            bestEffort = True
    )

    mang_slope = dsm.select('slope').updateMask(mangs).reduceRegion(
            reducer = ee.Reducer.percentile(percentiles = [99]),
            geometry = mangs.geometry(),
            scale = 30,
            maxPixels = 1e12,
            bestEffort = True
    )

    el_val = ee.Image.constant(mang_elv.get('elev'))
    slp_val = ee.Image.constant(mang_slope.get('slope'))

    return dsm.select('elev').lte(el_val).And(dsm.select('slope').lte(slp_val)).double()


# roi here should the dict equivalent of a geojson polygon
def coastline(poly: dict) -> ee.Geometry:
    # use the roi to clip the world boundary polygons
    area = ee.FeatureCollection('USDOS/LSIB/2013').filterBounds(ee.Geometry(poly)).geometry()
    
    # convert the polygon to a coordinate list
    area_coords = area.dissolve().coordinates().flatten()
    # use the coordinates to create a sting geometry
    area_point = ee.Geometry.MultiPoint(area_coords)
    
    # select points in roi and convert to coordinate list
    return area_point.intersection(ee.Geometry(poly), ee.ErrorMargin(1))

def area_chart(poly: dict) -> Dict[str, dict]:
    mang = known_mangroves()
    coast = coastline(poly).simplify(1000)
    # create an image collection of various buffered mangroves, using the distance list
    mangrove_buff = ee.Image(mang) \
        .addBands(mang.clip(coast.buffer(1000)).rename(['1'])) \
        .addBands(mang.clip(coast.buffer(2500)).rename(['2'])) \
        .addBands(mang.clip(coast.buffer(5000)).rename(['5'])) \
        .addBands(mang.clip(coast.buffer(10000)).rename(['10'])) \
        .addBands(mang.clip(coast.buffer(15000)).rename(['15'])) \
        .addBands(mang.clip(coast.buffer(20000)).rename(['20']))

    bands = mangrove_buff.bandNames().slice(1,8)
    mangrove_buff = mangrove_buff.select(bands)
    
    bands = ee.Image.pixelArea().addBands(mangrove_buff).bandNames().slice(1,8)
    proc_img = mangrove_buff.select(bands)
    
    sums = proc_img.reduceRegion(
        reducer = ee.Reducer.sum(),
        geometry = ee.Geometry(poly),
        scale = 30,
        maxPixels = 1e13,
        bestEffort = True
    ).getInfo()
    
    sums = dict(sorted(sums.items(), key=lambda x:x[1]))

    return {"sums": {"keys": list(sums.keys()), "vals": [int(x) for x in list(sums.values())]}, "buffers": {"keys": list(buffers.keys()), "vals": list(buffers.values())}}

class NoContemporaryImages(Exception):
    pass

class NoHistoricalImages(Exception):
    pass

def visualize_imagery(roi: dict, buff_dist: int) -> Dict[str, str]:
    try:
        hhot, hlot = hist_imagery(roi, buff_dist)
    except NoImages:
        raise NoHistoricalImages("")
    
    try:
        chot, clot = cont_imagery(roi, buff_dist)
    except NoImages:
        raise NoContemporaryImages("")

    vis = {'bands': ['B4', 'B5', 'B3'], 'min': 0, 'max': 0.27}
    
    chot_url = chot.getMapId(vis)["tile_fetcher"].url_format
    clot_url = clot.getMapId(vis)["tile_fetcher"].url_format
    hhot_url = hhot.getMapId(vis)["tile_fetcher"].url_format
    hlot_url = hlot.getMapId(vis)["tile_fetcher"].url_format
    
    return {
        "chot_url": chot_url,
        "clot_url": clot_url,
        "hhot_url": hhot_url,
        "hlot_url": hlot_url
    }

def final_mask(buff_dist: int, poly: dict, clot: ee.Image, hlot: ee.Image) -> ee.Image:
    coast = coastline(poly)
    poly = coast.buffer(buff_dist)
    mangs = known_mangroves().clip(poly)
    tmask = topo_mask(topo_dsm(), mangs)

    mndwi_cont = clot.normalizedDifference(['B5', 'B2']).gte(0.09)
    mndwi_hist = hlot.normalizedDifference(['B5', 'B2']).gte(0.09)
    h2o_mask = mndwi_cont.add(mndwi_hist).gt(1)

    return h2o_mask.multiply(tmask).eq(1)

def cont_imagery(roi: dict, buff_dist: int) -> Tuple[ee.ImageCollection, ee.ImageCollection]:
    return get_imagery(buff_dist, roi["indices"], roi["polygon"], roi["cont_year_start"], roi["cont_year_end"], roi["cont_month_start"], roi["cont_month_end"])
    
def hist_imagery(roi: dict, buff_dist: int) -> Tuple[ee.ImageCollection, ee.ImageCollection]:
    return get_imagery(buff_dist, roi["indices"], roi["polygon"], roi["hist_year_start"], roi["hist_year_end"], roi["hist_month_start"], roi["hist_month_end"])
    
class NoImages(Exception):
    pass

def get_imagery(buff_dist: int, indices: List[str], poly: dict, year1: int, year2: int, month1: int, month2: int) -> Tuple[ee.ImageCollection, ee.ImageCollection]:
    coast = coastline(poly)
    poly = coast.buffer(buff_dist)
    zone = coast.simplify(500).buffer(tidalZone).simplify(500)
    
    ls4 = ls4_imagery(poly, year1, year2, month1, month2)
    ls5 = ls5_imagery(poly, year1, year2, month1, month2)
    # ls7 = ls7_imagery(poly, year1, year2, month1, month2)
    ls8 = ls8_imagery(poly, year1, year2, month1, month2)
    ls9 = ls9_imagery(poly, year1, year2, month1, month2)
    
    # rename bands
    oli_imgs = ee.ImageCollection(ls8.merge(ls9)) \
            .select(['SR_B2','SR_B3','SR_B4','SR_B5','SR_B6','SR_B7','ST_B10','QA_PIXEL'], ['B1','B2','B3','B4','B5','B7','B6','pixel_qa'])
    
    # merge TM/ETM+ the collection
    tm_imgs = ee.ImageCollection(ls5.merge(ls4)) \
            .select(['SR_B1','SR_B2','SR_B3','SR_B4','SR_B5','SR_B7','ST_B6','QA_PIXEL'], ['B1','B2','B3','B4','B5','B7','B6','pixel_qa'])
    
    tm_imgs = tm_imgs.map(etm_to_oli)
    
    imgs = oli_imgs.merge(tm_imgs)
    
    if imgs.size().getInfo() <= 0:
        raise NoImages("")
    
    imgs = imgs.map(apply_scale_factors).map(fix_float).map(doubleOO).map(cloud_mask)
    imgs = tide_bands(shore_refl(imgs, zone, poly))
    
    high_tide = ee.ImageCollection(imgs).qualityMosaic("MNDWI").select(['B1','B2','B3','B4','B5','B6','B7'])
    low_tide = ee.ImageCollection(imgs).qualityMosaic("inv_MNDWI").select(['B1','B2','B3','B4','B5','B6','B7'])

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
    
    return high_tide.float().clip(poly), low_tide.float().clip(poly)


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
        .filterMetadata("CLOUD_COVER", "not_greater_than", cloudCoverLimit) \
        .filterDate(f'{year1}-01-01', f'{year2}-12-31') \
        .filter(ee.Filter.calendarRange(month1, month2, "month"))
    
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
        mndwi = ee.Image(img).expression('(B2 - B5)/(B2 + B5)', {'B2': img.select('B2'), 'B5': img.select('B5')}).rename(["MNDWI"])
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
        )
        
        # create single value to add to metatdata
        cum_sum = ee.List(cum_val.values()).reduce(ee.Reducer.sum())
        # input that value into the image metadata as the property 'MNDWI'
        return img.set('MNDWI', ee.Number(cum_sum))
    
    return ee.ImageCollection(imgs).map(mndwi_map)

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

def produce_savi(img: ee.Image) -> ee.Image:
    return img.select('B4').subtract(img.select('B3')).divide(img.select('B4').add(img.select('B3')).add(0.5)).multiply(1.5).rename(['SAVI'])

import ee
from typing import Tuple, Dict

from roi import cont_imagery, hist_imagery
from assets import asset_name

def chot_correlations(uid: str, key: str, num_label: str, roi: dict, buff_dist: int) -> Tuple[Dict[str, list], Dict[str, list]]:
    chot, _ = cont_imagery(roi, buff_dist)
    return pearson_correlation(chot, training_poly(uid, key, num_label))

def chot_correlations(uid: str, key: str, num_label: str, roi: dict, buff_dist: int) -> Tuple[Dict[str, list], Dict[str, list]]:
    _, clot = cont_imagery(roi, buff_dist)
    return pearson_correlation(clot, training_poly(uid, key, num_label))

def hhot_correlations(uid: str, key: str, num_label: str, roi: dict, buff_dist: int) -> Tuple[Dict[str, list], Dict[str, list]]:
    hhot, _ = hist_imagery(roi, buff_dist)
    return pearson_correlation(hhot, training_poly(uid, key, num_label))

def hlot_correlations(uid: str, key: str, num_label: str, roi: dict, buff_dist: int) -> Tuple[Dict[str, list], Dict[str, list]]:
    _, hlot = hist_imagery(roi, buff_dist)
    return pearson_correlation(hlot, training_poly(uid, key, num_label))

def training_poly(uid: str, key: str, num_label: str) -> ee.FeatureCollection:
   name = asset_name(uid, key) 
   return ee.FeatureCollection(name).sort(num_label)

def sample_image(img: ee.Image, t_poly: ee.FeatureCollection, num_label: str, char_label: str) -> ee.FeatureCollection:
    return img.sampleRegions(
        collection = t_poly,
        properties = [num_label, char_label],
        scale = 30,
        tileScale = 16
    )

def pearson_correlation(img: ee.Image, t_poly: ee.FeatureCollection) -> Dict[str, list]:
    bands = img.bandNames().remove('B6')
    corr = {'bands': []}
    
    def row(band: str) -> ee.List:
        return correlation_row(band, bands, img, t_poly)
    
    matrix = bands.map(row).getInfo()
    
    for r in matrix:
        band = r[0]
        corr['bands'].append(band)
        corr[band] = r[1:]

    return corr

def correlation_row(band: str, bands: ee.List, img: ee.Image, t_poly: ee.FeatureCollection) -> ee.List:
    out = ee.List([band])
    base = img.select([band], ['base'])
    
    def cell(b: str) -> ee.Number:
        return correlation_cell(b, base, img, t_poly)
    
    return out.cat(bands.map(cell))

def correlation_cell(band: str, base: ee.Image, img: ee.Image, t_poly: ee.FeatureCollection) -> ee.Number:
    return img.select([band]).addBands(base).reduceRegion(
        reducer = ee.Reducer.pearsonsCorrelation(),
        geometry = t_poly,
        scale = 30,
        maxPixels = 1e13,
        tileScale = 4
    ).get('correlation')

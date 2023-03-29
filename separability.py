import ee
from typing import Dict, List

from roi import chot_imagery, clot_imagery, hhot_imagery, hlot_imagery
from assets import asset_name

def chot_scatter(uid: str, key: str, num_label: str, char_label: str, roi: dict, buff_dist: int) -> List[dict]:
    return scatter_data(uid, key, num_label, char_label, chot_imagery(roi, buff_dist))

def clot_scatter(uid: str, key: str, num_label: str, char_label: str, roi: dict, buff_dist: int) -> List[dict]:
    return scatter_data(uid, key, num_label, char_label, clot_imagery(roi, buff_dist))

def hhot_scatter(uid: str, key: str, num_label: str, char_label: str, roi: dict, buff_dist: int) -> List[dict]:
    return scatter_data(uid, key, num_label, char_label, hhot_imagery(roi, buff_dist))

def hlot_scatter(uid: str, key: str, num_label: str, char_label: str, roi: dict, buff_dist: int) -> List[dict]:
    return scatter_data(uid, key, num_label, char_label, hlot_imagery(roi, buff_dist))

def scatter_data(uid: str, key: str, num_label: str, char_label: str, img: ee.Image) -> List[dict]:
    bands = img.bandNames().remove('B6').add(char_label)
    sample = sample_image(img, training_poly(uid, key, num_label), num_label, char_label)
    feats = sample.select(
        propertySelectors = bands,
        retainGeometry = False,
    ).toList(9999).getInfo()
    
    # this can be a large payload, so we remove unneeded values and round the floats
    # to reduce the amount of data we need to send
    props = []
    for feat in feats:
        prop = feat['properties']
        for k, v in prop.items():
            if k != char_label:
                prop[k] = round(v, 5)
        
        props.append(prop)
    
    return props

def chot_box_charts(uid: str, key: str, num_label: str, char_label: str, roi: dict, buff_dist: int) -> List[Dict[str, List[float]]]:
    return box_charts(uid, key, num_label, char_label, chot_imagery(roi, buff_dist))

def clot_box_charts(uid: str, key: str, num_label: str, char_label: str, roi: dict, buff_dist: int) -> List[Dict[str, List[float]]]:
    return box_charts(uid, key, num_label, char_label, clot_imagery(roi, buff_dist))

def hhot_box_charts(uid: str, key: str, num_label: str, char_label: str, roi: dict, buff_dist: int) -> List[Dict[str, List[float]]]:
    return box_charts(uid, key, num_label, char_label, hhot_imagery(roi, buff_dist))

def hlot_box_charts(uid: str, key: str, num_label: str, char_label: str, roi: dict, buff_dist: int) -> List[Dict[str, List[float]]]:
    return box_charts(uid, key, num_label, char_label, hlot_imagery(roi, buff_dist))

def box_charts(uid: str, key: str, num_label: str, char_label: str, img: ee.Image) -> List[Dict[str, List[float]]]:
    bands = img.bandNames().remove('B6')
    sample = sample_image(img, training_poly(uid, key, num_label), num_label, char_label)
    nums = sample.distinct(num_label).aggregate_array(num_label)
    chars = sample.distinct(char_label).aggregate_array(char_label)
    zipped = nums.zip(chars).sort(nums)
    
    def chart_data(cls: ee.List) -> ee.Dictionary:
        cls = ee.List(cls)
        return ee.Dictionary().set(cls.get(1), box_chart_data(cls.get(0), sample, bands, num_label))
    
    return zipped.map(chart_data).getInfo()

def box_chart_data(cls: ee.Number, sample: ee.FeatureCollection, bands: ee.List, num_label: str) -> ee.Dictionary:
    filtered = sample.filter(ee.Filter.eq(num_label, cls))
    dat = ee.Dictionary()
    dat = dat.set('mins', filtered.reduceColumns(ee.Reducer.min().forEach(bands), bands))
    dat = dat.set('maxs', filtered.reduceColumns(ee.Reducer.max().forEach(bands), bands))
    dat = dat.set('means', filtered.reduceColumns(ee.Reducer.mean().forEach(bands), bands))
    dat = dat.set('stds', filtered.reduceColumns(ee.Reducer.stdDev().forEach(bands), bands))

    def rotate(band: ee.String, prev: ee.Dictionary) -> ee.Dictionary:
        mini = ee.Number(ee.Dictionary(dat.get('mins')).get(band))
        maxi = ee.Number(ee.Dictionary(dat.get('maxs')).get(band))
        mean = ee.Number(ee.Dictionary(dat.get('means')).get(band))
        std = ee.Number(ee.Dictionary(dat.get('stds')).get(band))
        s1 = mean.subtract(std)
        s2 = mean.add(std)
        return ee.Dictionary(prev).set(band, ee.List([mini, s1, mean, s2, maxi]))
    
    return bands.iterate(rotate, ee.Dictionary())

def chot_correlations(uid: str, key: str, num_label: str, roi: dict, buff_dist: int) -> Dict[str, list]:
    return pearson_correlation(chot_imagery(roi, buff_dist), training_poly(uid, key, num_label))

def chot_correlations(uid: str, key: str, num_label: str, roi: dict, buff_dist: int) -> Dict[str, list]:
    return pearson_correlation(clot_imagery(roi, buff_dist), training_poly(uid, key, num_label))

def hhot_correlations(uid: str, key: str, num_label: str, roi: dict, buff_dist: int) -> Dict[str, list]:
    return pearson_correlation(hhot_imagery(roi, buff_dist), training_poly(uid, key, num_label))

def hlot_correlations(uid: str, key: str, num_label: str, roi: dict, buff_dist: int) -> Dict[str, list]:
    return pearson_correlation(hlot_imagery(roi, buff_dist), training_poly(uid, key, num_label))

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

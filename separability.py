import ee
from typing import Dict, List

from roi import chot_imagery, clot_imagery, hhot_imagery, hlot_imagery
from assets import asset_name

def chot_scatter(uid: str, key: str, num_label: str, char_label: str, roi: dict, buff_dist: int) -> Dict[str, List[Dict[str, float]]]:
    return scatter_data(uid, key, num_label, char_label, chot_imagery(roi, buff_dist))

def clot_scatter(uid: str, key: str, num_label: str, char_label: str, roi: dict, buff_dist: int) -> Dict[str, List[Dict[str, float]]]:
    return scatter_data(uid, key, num_label, char_label, clot_imagery(roi, buff_dist))

def hhot_scatter(uid: str, key: str, num_label: str, char_label: str, roi: dict, buff_dist: int) -> Dict[str, List[Dict[str, float]]]:
    return scatter_data(uid, key, num_label, char_label, hhot_imagery(roi, buff_dist))

def hlot_scatter(uid: str, key: str, num_label: str, char_label: str, roi: dict, buff_dist: int) -> Dict[str, List[Dict[str, float]]]:
    return scatter_data(uid, key, num_label, char_label, hlot_imagery(roi, buff_dist))

# Returns dict of class name to list of dicts of band name to value. Values are reflectance for landsat, or index values.
# Also contains an ordered list of classes at the root under 'classes'
def scatter_data(uid: str, key: str, num_label: str, char_label: str, img: ee.Image) -> Dict[str, List[Dict[str, float]]]:
    bands = img.bandNames().remove('B6')
    lbands = bands.add(char_label)
    sample = sample_image(img, training_poly(uid, key, num_label), num_label, char_label)
    feats = sample.select(
        propertySelectors = lbands,
        retainGeometry = False,
    ).toList(9999).getInfo()
    ordered = ordered_classes(sample, num_label, char_label)
    
    # this can be a large payload, so we remove unneeded values and round the floats
    # to reduce the amount of data we need to send
    props = {"classes": ordered, "bands": bands.getInfo()}
    for cls in ordered:
        props[cls] = []
    
    for feat in feats:
        prop = feat['properties']
        cls = prop.pop(char_label)
        for k, v in prop.items():
            prop[k] = round(v, 5)
        
        props[cls].append(prop)
    
    return props

def chot_box_charts(uid: str, key: str, num_label: str, char_label: str, roi: dict, buff_dist: int) -> Dict[str, Dict[str, List[float]]]:
    return box_charts(uid, key, num_label, char_label, chot_imagery(roi, buff_dist))

def clot_box_charts(uid: str, key: str, num_label: str, char_label: str, roi: dict, buff_dist: int) -> Dict[str, Dict[str, List[float]]]:
    return box_charts(uid, key, num_label, char_label, clot_imagery(roi, buff_dist))

def hhot_box_charts(uid: str, key: str, num_label: str, char_label: str, roi: dict, buff_dist: int) -> Dict[str, Dict[str, List[float]]]:
    return box_charts(uid, key, num_label, char_label, hhot_imagery(roi, buff_dist))

def hlot_box_charts(uid: str, key: str, num_label: str, char_label: str, roi: dict, buff_dist: int) -> Dict[str, Dict[str, List[float]]]:
    return box_charts(uid, key, num_label, char_label, hlot_imagery(roi, buff_dist))

# Returns dict of class name to dict of band name to list of 5 values. Values are: [min, s1, mean, s2, max].
# Also contains an ordered list of classes at the root under 'classes'
def box_charts(uid: str, key: str, num_label: str, char_label: str, img: ee.Image) -> Dict[str, Dict[str, List[float]]]:
    bands = img.bandNames().remove('B6')
    sample = sample_image(img, training_poly(uid, key, num_label), num_label, char_label)
    nums = sample.distinct(num_label).aggregate_array(num_label)
    chars = sample.distinct(char_label).aggregate_array(char_label)
    zipped = nums.zip(chars).sort(nums)
    ordered = ordered_zipped(zipped)
    
    def chart_data(cls: ee.List, prev: ee.Dictionary) -> ee.Dictionary:
        cls = ee.List(cls)
        return ee.Dictionary(prev).set(cls.get(1), box_chart_data(sample.filter(ee.Filter.eq(num_label, cls.get(0))), bands))
    
    d = zipped.iterate(chart_data, ee.Dictionary()).getInfo()
    d["classes"] = ordered
    d["bands"] = bands.getInfo()
    return d

def box_chart_data(filtered: ee.FeatureCollection, bands: ee.List) -> ee.Dictionary:
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

def ordered_classes(sample: ee.FeatureCollection, num_label: str, char_label: str) -> List[str]:
    nums = sample.distinct(num_label).aggregate_array(num_label)
    chars = sample.distinct(char_label).aggregate_array(char_label)
    return ordered_zipped(nums.zip(chars).sort(nums))
 
def ordered_zipped(zipped: ee.List) -> List[str]:
    zipped = zipped.getInfo()
    ordered = []
    for z in zipped:
        ordered.append(z[1])
    
    return ordered

def chot_correlations(uid: str, key: str, num_label: str, roi: dict, buff_dist: int) -> Dict[str, List[float]]:
    return pearson_correlation(chot_imagery(roi, buff_dist), training_poly(uid, key, num_label))

def chot_correlations(uid: str, key: str, num_label: str, roi: dict, buff_dist: int) -> Dict[str, List[float]]:
    return pearson_correlation(clot_imagery(roi, buff_dist), training_poly(uid, key, num_label))

def hhot_correlations(uid: str, key: str, num_label: str, roi: dict, buff_dist: int) -> Dict[str, List[float]]:
    return pearson_correlation(hhot_imagery(roi, buff_dist), training_poly(uid, key, num_label))

def hlot_correlations(uid: str, key: str, num_label: str, roi: dict, buff_dist: int) -> Dict[str, List[float]]:
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

# Returns a dict of band names to list of correlation values. Values are correlation between the band and the band at the indexed position.
# Also contains an ordered list of bands at the root under 'bands'
def pearson_correlation(img: ee.Image, t_poly: ee.FeatureCollection) -> Dict[str, List[float]]:
    bands = img.bandNames().remove('B6')
    local_bands = bands.getInfo()
    midpoint = int(len(local_bands)/2)
    half1 = bands.slice(0, midpoint)
    half2 = bands.slice(midpoint)
    
    corr = {"bands": local_bands}
    
    matrix = correlation_rows(half1, bands, img, t_poly) + correlation_rows(half2, bands, img, t_poly)

    for idx, r in enumerate(matrix):
        corr[local_bands[idx]] = [round(elem, 3) for elem in r]
    
    return corr

def correlation_rows(subset: ee.List, bands: ee.List, img: ee.Image, t_poly: ee.FeatureCollection) -> ee.List:
    def row(band: ee.String) -> ee.List:
        return correlation_row(band, bands, img, t_poly)

    return subset.map(row).getInfo()

def correlation_row(band: ee.String, bands: ee.List, img: ee.Image, t_poly: ee.FeatureCollection) -> ee.List:
    base = img.select([band], ['base'])
    
    def cell(b: str) -> ee.Number:
        return correlation_cell(img.select([b]).addBands(base), t_poly)
    
    return bands.map(cell)

def correlation_cell(img: ee.Image, t_poly: ee.FeatureCollection) -> ee.Number:
    return img.reduceRegion(
        reducer = ee.Reducer.pearsonsCorrelation(),
        geometry = t_poly,
        scale = 90,
        tileScale = 16
    ).get('correlation')

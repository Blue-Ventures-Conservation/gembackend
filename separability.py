import ee
from typing import Dict, List, Tuple

from enum import Enum
from imagery import cont_imagery, hist_imagery
from classification import sample_image, ordered_classes
from assets import asset_error, training_poly

class InvalidTimePeriod(Exception):
    pass

TimePeriod = Enum('TimePeriod', ['CONT_HIGH', 'CONT_LOW', 'HIST_HIGH', 'HIST_LOW'])

def iToTP(i: int) -> TimePeriod:
    try:
        return TimePeriod(i)
    except Exception:
        raise InvalidTimePeriod()

def scatter_chart(tpi: int, uid: str, key: str, num_label: str, char_label: str, roi: dict, buff_dist: int) -> Dict[str, List[Dict[str, float]]]:
    try:
        chot, clot, scale = cont_imagery(roi, buff_dist)
        hhot, hlot, _ = hist_imagery(roi, buff_dist)
        tp = iToTP(tpi)
        if tp == TimePeriod.CONT_HIGH:
            return scatter_chart_data(uid, key, num_label, char_label, chot, scale)
        if tp == TimePeriod.CONT_LOW:
            return scatter_chart_data(uid, key, num_label, char_label, clot, scale)
        if tp == TimePeriod.HIST_HIGH:
            return scatter_chart_data(uid, key, num_label, char_label, hhot, scale)
        if tp == TimePeriod.HIST_LOW:
            return scatter_chart_data(uid, key, num_label, char_label, hlot, scale)
    except Exception as e:
        raise asset_error(e)

# Returns dict of class name to list of dicts of band name to value. Values are reflectance for landsat, or index values.
# Also contains an ordered list of classes at the root under 'classes'
def scatter_chart_data(uid: str, key: str, num_label: str, char_label: str, img: ee.Image, scale: int) -> Dict[str, List[Dict[str, float]]]:
    bands = img.bandNames()
    cbands = bands.add(char_label)
    tpoly = training_poly(uid, key, num_label)
    sample = sample_image(img, tpoly, [num_label, char_label, "ID_Numeric", "id_numeric", "ID", "id"], scale, False)
    zprops = zipped_props(sample, num_label, char_label)
    
    def round_props(feat: ee.Feature) -> ee.Feature:
        def band_iter(band: ee.String, feat: ee.Feature):
            feat = ee.Feature(feat)
            return feat.set(band, ee.Number(feat.get(band)).multiply(1000).round().divide(1000))
        return bands.iterate(band_iter, feat)
    
    data = ee.Algorithms.If(sample.size().gte(zprops.size().multiply(5000)), ee.FeatureCollection(sample.map(round_props)).distinct(cbands), sample)
    feats = ee.FeatureCollection(data).toList(99999).getInfo()
    
    # this can be a large payload, so we remove unneeded values and round the floats
    # to reduce the amount of data we need to send
    ordered = ordered_classes(zprops.getInfo())
    props = {"classes": ordered, "bands": bands.getInfo()}
    for cls in ordered:
        props[cls] = []
    
    for feat in feats:
        prop = feat['properties']
        cls = prop.pop(char_label)
        for k, v in prop.items():
            prop[k] = round(v, 4)
        
        props[cls].append(prop)
    
    return props

def box_charts(tpi: int, uid: str, key: str, num_label: str, char_label: str, roi: dict, buff_dist: int) -> Dict[str, Dict[str, List[float]]]:
    try:
        chot, clot, scale = cont_imagery(roi, buff_dist)
        hhot, hlot, _ = hist_imagery(roi, buff_dist)
        tp = iToTP(tpi)
        if tp == TimePeriod.CONT_HIGH:
            return box_charts_data(uid, key, num_label, char_label, chot, scale)
        if tp == TimePeriod.CONT_LOW:
            return box_charts_data(uid, key, num_label, char_label, clot, scale)
        if tp == TimePeriod.HIST_HIGH:
            return box_charts_data(uid, key, num_label, char_label, hhot, scale)
        if tp == TimePeriod.HIST_LOW:
            return box_charts_data(uid, key, num_label, char_label, hlot, scale)
    except Exception as e:
        raise asset_error(e)

# Returns dict of class name to dict of band name to list of 5 values. Values are: [min, s1, mean, s2, max].
# Also contains an ordered list of classes at the root under 'classes'
def box_charts_data(uid: str, key: str, num_label: str, char_label: str, img: ee.Image, scale: int) -> Dict[str, Dict[str, List[float]]]:
    bands = img.bandNames()
    sample = sample_image(img, training_poly(uid, key, num_label), [num_label, char_label], scale, False)
    zipped = zipped_props(sample, num_label, char_label)
    ordered = ordered_classes(zipped.getInfo())
    
    local_bands = bands.getInfo()
    d = ee.Dictionary()
    for b in local_bands:
        byClass = {}
        for cls in ordered:
            byClass[cls] = []
        
        d = d.set(b, byClass)
    
    def chart_data(cls: ee.List, outer: ee.Dictionary) -> ee.Dictionary:
        cls = ee.List(cls)
        data = ee.Dictionary(box_chart_data(sample.filter(ee.Filter.eq(num_label, cls.get(0))), bands))
        
        def boxes(band: ee.String, inner: ee.Dictionary) -> ee.Dictionary:
            return box_chart_rotate(band, inner, data, cls.get(1))
        
        return data.keys().iterate(boxes, outer)
    
    byBand = zipped.iterate(chart_data, d).getInfo()
    for band, bandDat in byBand.items():
        seps = separability(bandDat)
        byBand[band]["separability"] = seps
    
    byBand["classes"] = ordered
    byBand["bands"] = local_bands
    
    return byBand

def box_chart_rotate(band: ee.String, prev: ee.Dictionary, data: ee.Dictionary, cls: ee.String) -> ee.Dictionary:
    vals = data.get(ee.String(band))
    byClass = ee.Dictionary(prev).get(ee.String(band))
    prev = ee.Dictionary(prev).set(ee.String(band), ee.Dictionary(byClass).set(cls, vals))
    return prev

def separability(bandDat: Dict[str, List[float]]) -> List[List[str]]:
    done = []
    seps = []
    for k, v in bandDat.items():
        done.append(k)
        std1 = v[1]
        std2 = v[3]
        for kk, vv in bandDat.items():
            if k == kk or kk in done:
                continue
            
            std3 = vv[1]
            std4 = vv[3]
            
            if not overgap(std1, std2, std3, std4):
                seps.append([k, kk])
    
    return seps

def overgap(std1, std2, std3, std4: float) -> bool:
    gap1 = std2 - std1
    gap2 = std4 - std3
    if std2 >= std4 and std1 <= std4:
        ol = std4 - std1
        if std1 < std3:
            ol = std4 - std3
        return overlap(gap1, gap2, ol)
    
    if std2 <= std4 and std2 >= std3:
        ol = std2 - std1
        if std1 < std3:
             ol = std2 - std3
        return overlap(gap1, gap2, ol)
    
    return False

def overlap(g1, g2, ol: float) -> bool:
    return ol > (0.25 * g1) or ol > (0.25 * g2)

def box_chart_data(filtered: ee.FeatureCollection, bands: ee.List) -> ee.Dictionary:
    dat = ee.Dictionary()
    dat = dat.set('mins', filtered.reduceColumns(ee.Reducer.min().forEach(bands), bands))
    dat = dat.set('maxs', filtered.reduceColumns(ee.Reducer.max().forEach(bands), bands))
    dat = dat.set('means', filtered.reduceColumns(ee.Reducer.mean().forEach(bands), bands))
    dat = dat.set('stds', filtered.reduceColumns(ee.Reducer.stdDev().forEach(bands), bands))
    
    def byBand(band: ee.String, prev: ee.Dictionary) -> ee.Dictionary:
        mini = ee.Number(ee.Dictionary(dat.get('mins')).get(band)).multiply(100000).round().divide(100000)
        maxi = ee.Number(ee.Dictionary(dat.get('maxs')).get(band)).multiply(100000).round().divide(100000)
        mean = ee.Number(ee.Dictionary(dat.get('means')).get(band))
        std = ee.Number(ee.Dictionary(dat.get('stds')).get(band))
        s1 = mean.subtract(std).multiply(100000).round().divide(100000)
        s2 = mean.add(std).multiply(100000).round().divide(100000)
        mean = mean.multiply(100000).round().divide(100000)
        return ee.Dictionary(prev).set(band, ee.List([mini, s1, mean, s2, maxi]))
    
    return bands.iterate(byBand, ee.Dictionary())

def correlation_matrix(tpi: int, uid: str, key: str, num_label: str, roi: dict, buff_dist: int) -> Dict[str, List[float]]:
    try:
        chot, clot, scale = cont_imagery(roi, buff_dist)
        hhot, hlot, _ = hist_imagery(roi, buff_dist)
        tp = iToTP(tpi)
        if tp == TimePeriod.CONT_HIGH:
            return pearson_correlation(chot, training_poly(uid, key, num_label))
        if tp == TimePeriod.CONT_LOW:
            return pearson_correlation(clot, training_poly(uid, key, num_label))
        if tp == TimePeriod.HIST_HIGH:
            return pearson_correlation(hhot, training_poly(uid, key, num_label))
        if tp == TimePeriod.HIST_LOW:
            return pearson_correlation(hlot, training_poly(uid, key, num_label))
    except Exception as e:
        raise asset_error(e)

# Returns a dict of band names to list of correlation values. Values are correlation between the band and the band at the indexed position.
# Also contains an ordered list of bands at the root under 'bands'
def pearson_correlation(img: ee.Image, t_poly: ee.FeatureCollection) -> Dict[str, List[float]]:
    bands = img.bandNames()
    local_bands = bands.getInfo()
    p1 = int(len(local_bands)/3)
    p2 = p1 + p1
    s1 = bands.slice(0, p1)
    s2 = bands.slice(p1, p2)
    s3 = bands.slice(p2)
    
    corr = {"bands": local_bands, "highly_correlated": 0.8, "moderately_correlated": 0.6}
    
    matrix = correlation_rows(s1, bands, img, t_poly) + correlation_rows(s2, bands, img, t_poly) + correlation_rows(s3, bands, img, t_poly)
    
    for idx, r in enumerate(matrix):
        corr[local_bands[idx]] = [round(elem, 3) for elem in r]
    
    return corr

def correlation_rows(subset: ee.List, bands: ee.List, img: ee.Image, t_poly: ee.FeatureCollection) -> ee.List:
    def row(band: ee.String) -> ee.List:
        return correlation_row(band, bands, img, t_poly)
    
    return subset.map(row).getInfo()

def correlation_row(band: ee.String, bands: ee.List, img: ee.Image, t_poly: ee.FeatureCollection) -> ee.List:
    fifth = bands.size().divide(5).int().add(1)
    
    base = img.select([band], ['base'])
    s1 = correlation_partial_row(base, bands.slice(0, fifth), img, t_poly)
    s2 = correlation_partial_row(base, bands.slice(fifth, fifth.multiply(2)), img, t_poly)
    s3 = correlation_partial_row(base, bands.slice(fifth.multiply(2), fifth.multiply(3)), img, t_poly)
    s4 = correlation_partial_row(base, bands.slice(fifth.multiply(3), fifth.multiply(4)), img, t_poly)
    s5 = correlation_partial_row(base, bands.slice(fifth.multiply(4), fifth.multiply(5)), img, t_poly)
    
    return ee.List([s1, s2, s3, s4, s5]).flatten()

def correlation_partial_row(base: ee.Image, bands_sublist: ee.List, img: ee.Image, t_poly: ee.FeatureCollection) -> ee.List:
    def cell(b: str) -> ee.Number:
        return correlation_cell(img.select([b]).addBands(base), t_poly)
    
    return bands_sublist.map(cell)

def correlation_cell(img: ee.Image, t_poly: ee.FeatureCollection) -> ee.Number:
    return img.reduceRegion(
        reducer = ee.Reducer.pearsonsCorrelation(),
        maxPixels = 1e13,
        geometry = t_poly,
        scale = 300,
        tileScale = 2,
    ).get('correlation')

# returns ee.List of ee.String
def zipped_props(sample: ee.FeatureCollection, num_label: str, char_label: str) -> ee.List:
    nums = sample.distinct(num_label).aggregate_array(num_label)
    chars = sample.distinct(char_label).aggregate_array(char_label)
    return nums.zip(chars).sort(nums)

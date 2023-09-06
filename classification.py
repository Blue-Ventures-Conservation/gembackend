import ee
import time

from typing import List, Tuple, Dict, Any

from project import tile_timeout
from roi import coastline, cont_imagery, hist_imagery, known_mangroves
from assets import MissingAsset, make_export, asset_error, training_poly, asset_dl_timeout

trees = 1000
splits = 1
leafpop = 1
bag = 0.75
nodes = None
seeds = 0

class ClassifierFailed(Exception):
    pass

def classification_error(e: Exception) -> Exception:
    e = asset_error(e)
    if type(e) is MissingAsset:
        return e
    elif "Classifier training failed" in str(e):
        return ClassifierFailed()
    else:
        return e

def classification_export(uid: str, vis: bool, cont_key: str, hist_key: str, use_cont_spec: bool, num_label: str, char_label: str, palette: List[str], roi: dict, buff_dist: int):
    try:
        cont_class, hist_class, coast, _ = combined_classification_lazy(uid, vis, cont_key, hist_key, use_cont_spec, num_label, char_label, palette, roi, buff_dist)
        
        cont_task = make_export(uid, cont_class, coast, "contemporary_classification")
        hist_task = make_export(uid, hist_class, coast, "historical_classification")

        return {
            "contemporary": cont_task,
            "historical": hist_task,
            "created_at": int(time.time()),
            "timeout": asset_dl_timeout
        }
    except Exception as e:
        raise asset_error(e)

def combined_classification(uid: str, cont_key: str, hist_key: str, use_cont_spec: bool, num_label: str, char_label: str, palette: List[str], roi: dict, buff_dist: int):
    try:
        cont_combo, hist_combo, cont_t_poly, hist_t_poly, coast = combined_classification_prep(uid, cont_key, hist_key, use_cont_spec, num_label, roi, buff_dist)
        cont_classification, cont_classes = classify_fully(cont_combo, cont_t_poly, coast, num_label, char_label, palette)
        hist_classification, hist_classes = classify_fully(hist_combo, hist_t_poly, coast, num_label, char_label, palette)

        if cont_classes != hist_classes:
            raise Exception("classes did not match between historical and contemporary CRAs during classification")
        
        return {
            "contemporary_classification": cont_classification,
            "historical_classification": hist_classification,
            "classes": cont_classes,
            "created_at": int(time.time()),
            "timeout": tile_timeout
        }
    except Exception as e:
        raise asset_error(e)

def combined_classification_lazy(uid: str, vis: bool, cont_key: str, hist_key: str, use_cont_spec: bool, num_label: str, char_label: str, palette: List[str], roi: dict, buff_dist: int) -> Tuple[ee.Image, ee.Image, ee.Geometry, Dict[str, int]]:
    cont_combo, hist_combo, cont_t_poly, hist_t_poly, coast = combined_classification_prep(uid, cont_key, hist_key, use_cont_spec, num_label, roi, buff_dist)
    cont_cmap, cont_classification = classify(vis, cont_combo, cont_t_poly, coast, num_label, char_label, palette)
    hist_cmap, hist_classification = classify(vis, hist_combo, hist_t_poly, coast, num_label, char_label, palette)
    if cont_cmap != hist_cmap:
        raise Exception("class maps did not match between historical and contemporary CRAs during classification")
    
    return cont_classification, hist_classification, coast, cont_cmap

def combined_classification_prep(uid: str, cont_key: str, hist_key: str, use_cont_spec: bool, num_label: str, roi: dict, buff_dist: int) -> Tuple[ee.Image, ee.Image, ee.FeatureCollection, ee.FeatureCollection, ee.Geometry]:
    coast = coastline(roi["polygon"])
    coast = coast.buffer(buff_dist)
    chot, clot = cont_imagery(roi, buff_dist)
    hhot, hlot = hist_imagery(roi, buff_dist)
    fmask = final_mask(coast, clot, hlot)
    chot = chot.updateMask(fmask)
    clot = clot.updateMask(fmask)
    hhot = hhot.updateMask(fmask)
    hlot = hlot.updateMask(fmask)
    cont_combo = chot.addBands(clot)
    hist_combo = hhot.addBands(hlot)
    
    if use_cont_spec:
        hist_combo = cont_combo

    ct_poly = training_poly(uid, cont_key, num_label)
    ht_poly = training_poly(uid, hist_key, num_label)
    return cont_combo, hist_combo, ct_poly, ht_poly, coast

def classify(vis: bool, combo: ee.Image, t_poly: ee.FeatureCollection, coast: ee.Geometry, num_label: str, char_label: str, palette: List[str]) -> Tuple[Dict[str, int], ee.Image]:
    _, cmap, classified, _, _, _ = classify_lazy(vis, combo, t_poly, coast, num_label, char_label, palette)
    return cmap, classified

def classify_lazy(vis: bool, combo: ee.Image, t_poly: ee.FeatureCollection, coast: ee.Geometry, num_label: str, char_label: str, palette: List[str]) -> Tuple[List[str], Dict[str, int], ee.Image, Any, ee.FeatureCollection, ee.FeatureCollection]:
    bands = combo.bandNames()
    zipped = zipped_props(t_poly, num_label, char_label).getInfo()
    cmap = class_map(zipped)
    classes = ordered_classes(zipped)
    sample = sample_image(combo, t_poly, num_label, char_label)
    
    sample = sample.randomColumn(seed = 1)
    training = sample.filter(ee.Filter.lt("random", 0.7))
    validation = sample.filter(ee.Filter.lt("random", 0.7))
    classifier = ee.Classifier.smileRandomForest(
        numberOfTrees = trees,
        variablesPerSplit = splits,
        minLeafPopulation = leafpop,
        bagFraction = bag,
        maxNodes = nodes,
        seed = seeds,
    ).train(
        features = training,
        classProperty = num_label,
        inputProperties = bands,
    )
    
    classified = combo.classify(classifier).clip(coast)

    if vis == True:
        v = visual(t_poly, num_label, palette)
        classified = classified.visualize(palette = v['palette'], min = v['min'], max = v['max'])
    
    return classes, cmap, classified, classifier, training, validation

def visual(t_poly: ee.FeatureCollection, num_label: str, palette: List[str]) -> dict:
    min_no = t_poly.reduceColumns(
        reducer = ee.Reducer.min(),
        selectors = [num_label]
    ).get("min")
    max_no = t_poly.reduceColumns(
        reducer = ee.Reducer.max(),
        selectors = [num_label]
    ).get("max")
    
    return {"min": min_no.getInfo(), "max": max_no.getInfo(), "palette": palette}

def classify_fully(combo: ee.Image, t_poly: ee.FeatureCollection, coast: ee.Geometry, num_label: str, char_label: str, palette: List[str]) -> Tuple[dict, List[str]]:
    classes, _, classified, classifier, training, validation = classify_lazy(False, combo, t_poly, coast, num_label, char_label, palette)

    train_accuracy = classifier.confusionMatrix()
    validated = validation.classify(classifier)
    test_accuracy = validated.errorMatrix(num_label, "classification")
    
    classification_url = classified.getMapId(visual(t_poly, num_label, palette))["tile_fetcher"].url_format
    
    return {
        "url": classification_url,
        "resubstitution_accuracy": float(train_accuracy.accuracy().getInfo()),
        "validation_accuracy": float(test_accuracy.accuracy().getInfo()),
    }, classes

def final_mask(coast: ee.Geometry, clot: ee.Image, hlot: ee.Image) -> ee.Image:
    mangs = known_mangroves().clip(coast)
    tmask = topo_mask(topo_dsm(), mangs)
    
    mndwi_cont = renamed_mndwi(clot).lt(0.09)
    mndwi_hist = renamed_mndwi(hlot).lt(0.09)
    h2o_mask = mndwi_cont.add(mndwi_hist).gt(1)
    
    return h2o_mask.multiply(tmask).eq(1)

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

def renamed_mndwi(img: ee.Image) -> ee.Image:
    return img.expression('(B2 - B5)/(B2 + B5)', {'B2': img.select('Green'), 'B5': img.select('Shortwave IR 1')}).rename(['MNDWI'])

def sample_image(img: ee.Image, t_poly: ee.FeatureCollection, num_label: str, char_label: str) -> ee.FeatureCollection:
    props = [num_label, char_label]
    
    if t_poly.aggregate_count("ID").eq(t_poly.size()).getInfo() == 1:
        props.append("ID")
    
    return img.sampleRegions(
        collection = t_poly,
        properties = props,
        scale = 30,
        tileScale = 16
    )

def zipped_props(sample: ee.FeatureCollection, num_label: str, char_label: str) -> List[str]:
    nums = sample.distinct(num_label).aggregate_array(num_label)
    chars = sample.distinct(char_label).aggregate_array(char_label)
    return nums.zip(chars).sort(nums)

def class_map(zipped: list) -> Dict[str, int]:
    cm = {}
    for z in zipped:
        cm[z[1]] = int(z[0])
    
    return cm

def ordered_classes(zipped: list) -> List[str]:
    ordered = []
    for z in zipped:
        ordered.append(z[1])
    
    return ordered

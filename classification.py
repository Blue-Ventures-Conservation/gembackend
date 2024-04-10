import ee
import time

from typing import List, Tuple, Dict, Any

from project import tile_timeout
from roi import known_mangroves
from imagery import cont_imagery_collection, hist_imagery_collection, mosaic_indices, produce_mndwi, produce_ndwi
from assets import MissingAsset, make_export, make_image_assets, asset_name, asset_exists, check_operation, asset_error, training_poly, asset_dl_timeout

trees = 1000
splits = 1
leafpop = 1
bag = 0.75
nodes = None
seeds = 0
default_min_avg = 0.5

cont_class_asset = "cont_class_{region_uuid}"
hist_class_asset = "hist_class_{region_uuid}"

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

def check_cache(uid: str, key: str) -> ee.Image:
    asset_id = asset_name(uid, key)
    if asset_exists(asset_id):
        return ee.Image(asset_id)
    else:
        return None

def check_for_cached_classified_imagery(uid: str, region_uuid: str) -> Tuple[str, str, ee.Image, ee.Image]:
    cont_key = cont_class_asset.format(region_uuid = region_uuid)
    hist_key = hist_class_asset.format(region_uuid = region_uuid)
    return cont_key, hist_key, check_cache(uid, cont_key), check_cache(uid, hist_key)

def get_cached_imagery_or_submit(uid: str, region_uuid: str, region: ee.Geometry, prev_cont_op: str, prev_hist_op: str, lazy_cont: ee.Image, lazy_hist: ee.Image, scale: int) -> Tuple[ee.Image, ee.Image, str, str]:
    cont_key, hist_key, cont, hist = check_for_cached_classified_imagery(uid, region_uuid)
    
    cont_op = prev_cont_op
    if cont is None:
        succeeded, err = check_operation(prev_cont_op)
        if err is not None or (succeeded and check_cache(uid, cont_key) is None):
            cont_op = make_image_assets(uid, [lazy_cont], [cont_key], region)[0]
    
    hist_op = prev_hist_op
    if hist is None:
        succeeded, err = check_operation(prev_hist_op)
        if err is not None or (succeeded and check_cache(uid, hist_key) is None):
            hist_op = make_image_assets(uid, [lazy_hist], [hist_key], region)[0]
    
    return cont, hist, cont_op, hist_op

def classification_export(uid: str, region_uuid: str, cont_key: str, hist_key: str, use_cont_spec: bool, num_label: str, char_label: str, palette: List[str], roi: dict, buff_dist: int):
    try:
        cont_class, hist_class, region, palette, _, scale = combined_classification_lazy(uid, cont_key, hist_key, use_cont_spec, num_label, char_label, palette, roi, buff_dist)
        _, _, cont_cached, hist_cached = check_for_cached_classified_imagery(uid, region_uuid)
        
        if cont_cached is not None:
            cont_class = cont_cached
         
        if hist_cached is not None:
            hist_class = hist_cached
        
        cont_t_poly = training_poly(uid, cont_key, num_label)
        v = visual(cont_t_poly, num_label, palette)
        cont_class = cont_classification.visualize(palette = v['palette'], min = v['min'], max = v['max'])
        
        hist_t_poly = training_poly(uid, hist_key, num_label)
        v = visual(hist_t_poly, num_label, palette)
        hist_class = hist_classification.visualize(palette = v['palette'], min = v['min'], max = v['max'])
        
        cont_task = make_export(uid, cont_class, region, "contemporary_classification", scale)
        hist_task = make_export(uid, hist_class, region, "historical_classification", scale)
        
        return {
            "contemporary": cont_task,
            "historical": hist_task,
            "created_at": int(time.time()),
            "timeout": asset_dl_timeout
        }
    except Exception as e:
        raise asset_error(e)

def combined_classification(uid: str, region_uuid: str, cont_key: str, hist_key: str, use_cont_spec: bool, num_label: str, char_label: str, palette: List[str], roi: dict, buff_dist: int):
    try:
        cont_combo, cont_sample, hist_combo, hist_sample, cont_t_poly, hist_t_poly, region, palette, scale = combined_classification_prep(uid, cont_key, hist_key, use_cont_spec, num_label, char_label, palette, roi, buff_dist)
        cont_classification, cont_classes = classify_fully(uid, region_uuid, cont_class_asset, region, cont_combo, cont_sample, cont_t_poly, coast, num_label, char_label, palette, scale)
        hist_classification, hist_classes = classify_fully(uid, region_uuid, hist_class_asset, region, hist_combo, hist_sample, hist_t_poly, coast, num_label, char_label, palette, scale)
        
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

def combined_classification_lazy(uid: str, cont_key: str, hist_key: str, use_cont_spec: bool, num_label: str, char_label: str, palette: List[str], roi: dict, buff_dist: int) -> Tuple[ee.Image, ee.Image, ee.Geometry, List[str], Dict[str, int], int]:
    cont_combo, cont_sample, hist_combo, hist_sample, cont_t_poly, hist_t_poly, region, palette, scale = combined_classification_prep(uid, cont_key, hist_key, use_cont_spec, num_label, char_label, palette, roi, buff_dist)
    _, cont_sorts, cont_classification, _, _, _ = classify_lazy(cont_combo, cont_sample, cont_t_poly, region, num_label, char_label)
    _, hist_sorts, hist_classification, _, _, _ = classify_lazy(hist_combo, hist_sample, hist_t_poly, region, num_label, char_label)
    if cont_sorts != hist_sorts:
        raise Exception("class maps did not match between historical and contemporary CRAs during classification")
    
    return cont_classification, hist_classification, region, palette, cont_sorts, scale

def combined_classification_prep(uid: str, cont_key: str, hist_key: str, use_cont_spec: bool, num_label: str, char_label: str, palette: List[str], roi: dict, buff_dist: int) -> Tuple[ee.Image, ee.Image, ee.FeatureCollection, ee.FeatureCollection, ee.Geometry, ee.Geometry, ee.Geometry, ee.List, int]:
    conts, buf_excl_roi, indices, scale = cont_imagery_collection(roi, buff_dist)
    cont_water = ee.ImageCollection(conts).filter(ee.Filter.gte('MNDWI', default_min_avg)).qualityMosaic('inv_MNDWI').clip(buf_excl_roi)

    hists, _, _, _ = hist_imagery_collection(roi, buff_dist)
    hist_water = ee.ImageCollection(hists).filter(ee.Filter.gte('MNDWI', default_min_avg)).qualityMosaic('inv_MNDWI').clip(buf_excl_roi)

    fmask = final_mask(buf_excl_roi, cont_water, hist_water)

    chot, clot = mosaic_indices(conts, buf_excl_roi, indices, scale)
    hhot, hlot = mosaic_indices(hists, buf_excl_roi, indices, scale)
    chot = chot.updateMask(fmask)
    clot = clot.updateMask(fmask)
    hhot = hhot.updateMask(fmask)
    hlot = hlot.updateMask(fmask)
    cont_combo = chot.addBands(clot)
    hist_combo = hhot.addBands(hlot)
    
    ct_poly = training_poly(uid, cont_key, num_label)
    ht_poly = training_poly(uid, hist_key, num_label)
    cont_sample = sample_image(cont_combo, ct_poly, num_label, char_label, scale)
    hist_sample = cont_sample
    if not use_cont_spec:
        hist_sample = sample_image(hist_combo, ht_poly, num_label, char_label, scale)
    
    expanded_colors = ee.List([])
    if palette is not None:
        def num_iter(next: ee.Number, carry: ee.Dictionary):
            carry = ee.Dictionary(carry)
            pos = ee.Number(carry.get('position'))
            color = ee.List(carry.get('colors')).get(pos)
            prev = ee.Number(carry.get('prev'))
            out = ee.List(carry.get('output'))
            diff = ee.Number(ee.Algorithms.If(pos.gt(0), ee.Number(next).subtract(prev), ee.Number(1)))
            out = out.cat(ee.List.repeat(color, diff))
            carry = carry.set('prev', ee.Number(next))
            carry = carry.set('output', out)
            carry = carry.set('position', pos.add(1))
            return carry
        
        first = ee.Dictionary({"position": ee.Number(0), "prev": ee.Number(-1), "colors": ee.List(palette), "output": ee.List([])})
        expanded_colors = ee.Dictionary(ct_poly.distinct(num_label).sort(num_label).aggregate_array(num_label).iterate(num_iter, first)).get('output')
    
    return cont_combo, cont_sample, hist_combo, hist_sample, ct_poly, ht_poly, buf_excl_roi, expanded_colors, scale

def classify_lazy(combo: ee.Image, sample: ee.FeatureCollection, t_poly: ee.FeatureCollection, region: ee.Geometry, num_label: str, char_label: str) -> Tuple[List[str], list, ee.Image, Any, ee.FeatureCollection, ee.FeatureCollection]:
    bands = combo.bandNames()
    sorts = ee.FeatureCollection(t_poly).distinct(num_label).sort(num_label);
    nums = sorts.aggregate_array(num_label);
    chars = sorts.aggregate_array(char_label);
    sorteds = ee.List([nums, chars]).getInfo()
    classes = ordered_classes(list(map(list, zip(sorteds[0], sorteds[1]))))
    
    sample = sample.randomColumn(seed = 1)
    training = sample.filter(ee.Filter.lt("random", 0.7))
    validation = sample.filter(ee.Filter.gte("random", 0.7))
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
    
    classified = combo.classify(classifier).clip(region)
     
    return classes, sorteds, classified, classifier, training, validation

def visual(t_poly: ee.FeatureCollection, num_label: str, palette: ee.List) -> dict:
    min_no = t_poly.reduceColumns(
        reducer = ee.Reducer.min(),
        selectors = [num_label]
    ).get("min")
    max_no = t_poly.reduceColumns(
        reducer = ee.Reducer.max(),
        selectors = [num_label]
    ).get("max")
    
    return ee.Dictionary({"min": min_no, "max": max_no, "palette": palette}).getInfo()

def classify_fully(uid: str, region_uuid: str, asset_fmt: str, region: ee.Geometry, combo: ee.Image, sample: ee.FeatureCollection, t_poly: ee.FeatureCollection, num_label: str, char_label: str, palette: ee.List, scale: int) -> Tuple[dict, List[str]]:
    classes, _, classified, classifier, training, validation = classify_lazy(combo, sample, t_poly, region, num_label, char_label)
    
    image_op = ""
    if region_uuid is not None:
        ops = make_image_assets(uid, [classified], [asset_fmt.format(region_uuid = region_uuid)], region)
        if len(ops) > 0:
            image_op = ops[0]
    
    train_accuracy = classifier.confusionMatrix()
    validated = validation.classify(classifier)
    test_accuracy = validated.errorMatrix(num_label, "classification")
    
    classification_url = classified.getMapId(visual(t_poly, num_label, palette))["tile_fetcher"].url_format
    
    train_acc = train_accuracy.accuracy().getInfo()
    test_acc = test_accuracy.accuracy().getInfo()
    
    return {
        "url": classification_url,
        "resubstitution_accuracy": float(train_acc),
        "validation_accuracy": float(test_acc),
        "image_op": image_op,
    }, classes

def final_mask(coast: ee.Geometry, clot: ee.Image, hlot: ee.Image) -> ee.Image:
    mangs = known_mangroves().clip(region)
    dsm = topo_dsm()
    tmask = topo_mask(dsm, 30, mangs)
    
    mndwi_cont = produce_mndwi(clot).lt(0.09)
    ndwi_cont = produce_ndwi(clot).lt(0.20)
    cont_water = mndwi_cont.add(ndwi_cont).gt(1)
    
    mndwi_hist = produce_mndwi(hlot).lt(0.09)
    ndwi_hist = produce_ndwi(hlot).lt(0.20)
    hist_water = mndwi_hist.add(ndwi_hist).gt(1)
    
    h2o_mask = cont_water.add(hist_water).gte(1)
    
    return h2o_mask.multiply(tmask).eq(1)

def topo_dsm() -> Tuple[ee.Image, int]:
    elev = ee.ImageCollection("JAXA/ALOS/AW3D30/V3_2").select("DSM")
    proj = elev.first().select(0).projection()
    dsm = elev.mosaic().setDefaultProjection(proj).rename("elev")
    slp_img = ee.Terrain.slope(ee.Image(dsm).select("elev")).double().rename("slope")
    return dsm.addBands(slp_img)

def topo_mask(dsm: ee.Image, scale: int, mangs: ee.Image) -> ee.Image:
    mang_elv = dsm.select('elev').updateMask(mangs).reduceRegion(
            reducer = ee.Reducer.percentile(percentiles = [99]),
            geometry = mangs.geometry(),
            scale = scale,
            maxPixels = 1e12,
            bestEffort = True
    )
    
    mang_slope = dsm.select('slope').updateMask(mangs).reduceRegion(
            reducer = ee.Reducer.percentile(percentiles = [99]),
            geometry = mangs.geometry(),
            scale = scale,
            maxPixels = 1e12,
            bestEffort = True
    )
    
    el_val = ee.Image.constant(mang_elv.get('elev'))
    slp_val = ee.Image.constant(mang_slope.get('slope'))
    
    return dsm.select('elev').lte(el_val).And(dsm.select('slope').lte(slp_val)).double()

def sample_image(img: ee.Image, t_poly: ee.FeatureCollection, num_label: str, char_label: str, scale: int) -> ee.FeatureCollection:
    props = [num_label, char_label]
    
    if t_poly.aggregate_count("ID").eq(t_poly.size()).getInfo() == 1:
        try:
            isANum = t_poly.first().getNumber("ID").getInfo()
            props.append("ID")
        except:
            pass
    
    return img.sampleRegions(
        collection = t_poly,
        properties = props,
        scale = scale,
        tileScale = 16
    )

def ordered_classes(zipped: list) -> List[str]:
    ordered = []
    for z in zipped:
        ordered.append(z[1])
    
    return ordered

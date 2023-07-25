import ee
import time

from typing import List

from project import tile_timeout
from roi import coastline, cont_imagery, hist_imagery, known_mangroves
from assets import asset_error, training_poly

trees = 1000
splits = 1
leafpop = 1
bag = 0.75
nodes = None
seeds = 0

def combined_classification(uid: str, cont_key: str, hist_key: str, use_cont_spec: bool, num_label: str, char_label: str, palette: List[str], roi: dict, buff_dist: int):
    try:
        coast = coastline(roi["polygon"])
        poly = coast.buffer(buff_dist)
        chot, clot = cont_imagery(roi, buff_dist)
        hhot, hlot = hist_imagery(roi, buff_dist)
        fmask = final_mask(buff_dist, roi["polygon"], clot, hlot)
        chot = chot.updateMask(fmask)
        clot = clot.updateMask(fmask)
        hhot = hhot.updateMask(fmask)
        hlot = hlot.updateMask(fmask)
        cont_combo = chot.addBands(clot)
        hist_combo = hhot.addBands(hlot)
        
        if use_cont_spec:
            hist_combo = cont_combo
        
        cont_classification, cont_classes = classify(cont_combo, training_poly(uid, cont_key, num_label), poly, num_label, char_label, palette)
        hist_classification, hist_classes = classify(hist_combo, training_poly(uid, hist_key, num_label), poly, num_label, char_label, palette)

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

def classify(combo: ee.Image, t_poly: ee.FeatureCollection, poly: ee.Geometry, num_label: str, char_label: str, palette: List[str]) -> dict:
    bands = combo.bandNames()
    classes = ordered_classes(zipped_props(t_poly, num_label, char_label))
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
    
    classified = combo.classify(classifier).clip(poly)
    
    min_no = t_poly.reduceColumns(
        reducer = ee.Reducer.min(),
        selectors = [num_label]
    ).get("min")
    max_no = t_poly.reduceColumns(
        reducer = ee.Reducer.max(),
        selectors = [num_label]
    ).get("max")
    
    train_accuracy = classifier.confusionMatrix()
    validated = validation.classify(classifier)
    test_accuracy = validated.errorMatrix(num_label, "classification")
    
    vis = {"min": min_no.getInfo(), "max": max_no.getInfo(), "palette": palette}
    classification_url = classified.getMapId(vis)["tile_fetcher"].url_format
    
    return {
        "url": classification_url,
        "resubstitution_accuracy": float(train_accuracy.accuracy().getInfo()),
        "validation_accuracy": float(test_accuracy.accuracy().getInfo()),
    }, classes

def final_mask(buff_dist: int, poly: dict, clot: ee.Image, hlot: ee.Image) -> ee.Image:
    coast = coastline(poly)
    poly = coast.buffer(buff_dist)
    mangs = known_mangroves().clip(poly)
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
    return img.sampleRegions(
        collection = t_poly,
        properties = [num_label, char_label],
        scale = 30,
        tileScale = 16
    )

def zipped_props(sample: ee.FeatureCollection, num_label: str, char_label: str) -> List[str]:
    nums = sample.distinct(num_label).aggregate_array(num_label)
    chars = sample.distinct(char_label).aggregate_array(char_label)
    return nums.zip(chars).sort(nums)

def ordered_classes(zipped: ee.List) -> List[str]:
    zipped = zipped.getInfo()
    ordered = []
    for z in zipped:
        ordered.append(z[1])
    
    return ordered

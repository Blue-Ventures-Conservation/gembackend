import ee
import time

from typing import List

from project import tile_timeout
from roi import coastline, final_mask, cont_imagery, hist_imagery
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

        cont_classification = classify(cont_combo, training_poly(uid, cont_key, num_label), poly, char_label, palette)
        hist_classification = classify(hist_combo, training_poly(uid, hist_key, num_label), poly, char_label, palette)

        return {
            "contemporary_classification": cont_classification,
            "historical_classification": hist_classification,
            "created_at": int(time.time()),
            "timeout": tile_timeout
        }
    except Exception as e:
        raise asset_error(e)

def classify(combo: ee.Image, t_poly: ee.FeatureCollection, poly: ee.Geometry, char_label: str, palette: List[str]) -> dict:
    bands = combo.bandNames()
    sample = combo.sampleRegions(
        collection = t_poly,
        properties = [char_label],
        scale = 30,
        tileScale = 16
    )
    
    sample = sample.randomColumn(seed = 1)
    training = sample.filter(ee.Filter.lt("random", 0.7))
    validation = sample.filter(ee.Filter.lt("random", 0.7))
    classifier = ee.Classifier.smileRandomForest(
        numberOfTree = trees,
        variablesPerSplit = splits,
        minLeafPopulation = leafpop,
        bagFraction = bag,
        maxNodes = nodes,
        seed = seeds,
    ).train(
        features = training,
        classProperty = label,
        inputProperties = bands,
    )
    
    classified = combo.classify(classifier).clip(poly)
    
    min_no = t_poly.reduceColumns(
        reducer = ee.Reducer.min(),
        selectors = [char_label]
    ).get("min")
    maxno = t_poly.reduceColumns(
        reducer = ee.Reducer.max(),
        selectors = [char_label]
    ).get("max")
    
    train_accuracy = classifier.confusionMatrix()
    validated = validation.classify(classifier)
    test_accuracy = validated.errorMatrix(char_label, "classification")
    
    vis = {"min": min_no.getInfo(), "max": max_no.getInfo(), "palette": palette}
    classification_url = classified.getMapId(vis)["tile_fetcher"].url_format
    
    return {
        "url": classification_url,
        "resubstitution_accuracy": train_accuracy.accuracy(),
        "validation_accuracy": test_accuracy.accuracy(),
    }

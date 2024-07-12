import ee
import time

from typing import List, Tuple

from project import tile_timeout
from classification import check_for_classified_imagery, combined_classification_lazy
from assets import asset_error, make_export, asset_dl_timeout

def dynamics_export(uid: str, region_uuid: str, target_classes: List[str], combined_name: str, red: str, green: str, blue: str, cont_key: str, hist_key: str, use_cont_spec: bool, num_label: str, char_label: str, roi: dict, buff_dist: int):
    try:
        class_num, _, cont_class, hist_class, coast, sortedValues, sortedNames = combine_classes(uid,region_uuid, target_classes, combined_name, cont_key, hist_key, use_cont_spec, num_label, char_label, roi, buff_dist)
        classImgs = class_images(cont_class, hist_class, sortedValues)
        _, lmask, pmask, gmask = region_stats(True, coast, class_num, classImgs, sortedValues, sortedNames)
        
        lmask = lmask.visualize(palette = red)
        pmask = pmask.visualize(palette = green)
        gmask = gmask.visualize(palette = blue)
        ltask = make_export(uid, lmask, coast, "loss")
        ptask = make_export(uid, pmask, coast, "persistence")
        gtask = make_export(uid, gmask, coast, "gain")
        
        return {
            "loss": ltask,
            "persistence": ptask,
            "gain": gtask,
            "created_at": int(time.time()),
            "timeout": asset_dl_timeout
        }
    except Exception as e:
        raise asset_error(e)

def get_dynamics(uid: str, region_uuid: str, target_classes: List[str], combined_name: str, sub_regions: List[dict], red: str, green: str, blue: str, cont_key: str, hist_key: str, use_cont_spec: bool, num_label: str, char_label: str, roi: dict, buff_dist: int):
    try:
        class_num, tpos, cont_class, hist_class, roi_geo, sortedValues, sortedNames = combine_classes(uid, region_uuid, target_classes, combined_name, cont_key, hist_key, use_cont_spec, num_label, char_label, roi, buff_dist)
        classImgs = class_images(cont_class, hist_class, sortedValues)
        rstats, lmask, pmask, gmask  = region_stats(False, roi_geo, class_num, classImgs, sortedValues, sortedNames)
        
        output = {
            "name": roi["name"],
            "stats": {
                "name": roi["name"],
                "contemporary_area": rstats[tpos]["cont"],
                "historical_area": rstats[tpos]["hist"],
                "loss": rstats[tpos]["loss"],
                "persistence": rstats[tpos]["persistence"],
                "gain": rstats[tpos]["gain"],
                "all_classes": rstats,
            },
            "loss_url": lpg_url(lmask, red),
            "persistence_url": lpg_url(pmask, green),
            "gain_url": lpg_url(gmask, blue),
            "created_at": int(time.time()),
            "timeout": tile_timeout,
            "sub_region_stats": []
        }
        
        for sr in sub_regions:
            stats, _, _, _ = region_stats(False, ee.Geometry(sr["geometry"]), class_num, classImgs, sortedValues, sortedNames)
            output["sub_region_stats"].append({"name": sr["name"], "contemporary_area": stats[tpos]["cont"], "historical_area": stats[tpos]["hist"], "loss": stats[tpos]["loss"], "persistence": stats[tpos]["persistence"], "gain": stats[tpos]["gain"], "all_classes": stats})
        
        return output
    except Exception as e:
        raise asset_error(e)

def class_images(cont_class: ee.Image, hist_class: ee.Image, sortedValues: List[int]) -> ee.List:
    classImgs = ee.List([])
    for n in sortedValues:
        classImgs = classImgs.add(ee.Dictionary({
            "cont": cont_class.eq(n),
            "hist": hist_class.eq(n)
        }))
    return classImgs

def combine_classes(uid: str, region_uuid: str, target_classes: List[str], combined_name: str, cont_key: str, hist_key: str, use_cont_spec: bool, num_label: str, char_label: str, roi: dict, buff_dist: int) -> Tuple[int, int, ee.Dictionary, ee.Image, ee.Image, ee.Geometry, List[int], List[str]]:
    cont_class, hist_class, coast, sorts = combined_classification_lazy(uid, False, cont_key, hist_key, use_cont_spec, num_label, char_label, None, roi, buff_dist)
    cont_class, hist_class = check_for_classified_imagery(uid, region_uuid, coast, True, cont_class, hist_class)
    sortedValues = sorts[0]
    sortedNames = sorts[1]
    
    if len(target_classes) <= 0:
        raise Exception("No target classes provided")
    
    class_name = target_classes[0]
    tpos = sortedNames.index(class_name)
    class_num = sortedValues[tpos]
    
    if len(target_classes) > 1:
        sortedNames[tpos] = combined_name
        cont_combo = cont_class.eq(class_num).multiply(class_num)
        hist_combo = hist_class.eq(class_num).multiply(class_num)
        cont_neg = cont_class.neq(class_num)
        hist_neg = hist_class.neq(class_num)
        
        for idx, tc in enumerate(target_classes):
            if idx == 0:
                continue
            
            i = sortedNames.index(tc)
            cn = sortedValues[i]
            del(sortedValues[i])
            del(sortedNames[i])
            cont_combo = cont_combo.add(cont_class.eq(cn).multiply(class_num))
            hist_combo = hist_combo.add(hist_class.eq(cn).multiply(class_num))
            cont_neg = cont_neg.And(cont_class.neq(cn))
            hist_neg = hist_neg.And(hist_class.neq(cn))
        
        cont_class = cont_class.multiply(cont_neg).add(cont_combo)
        hist_class = hist_class.multiply(hist_neg).add(hist_combo)
     
    return class_num, sortedValues.index(class_num), cont_class, hist_class, coast, sortedValues, sortedNames

def region_stats(masksOnly: bool, geo: ee.Geometry, class_num: int, classImgs: ee.Dictionary, sortedValues: List[int], sortedNames: List[str]) -> Tuple[List[dict], ee.Image, ee.Image, ee.Image]:
    def contHist(pos):
        cimgs = ee.Dictionary(classImgs.get(pos))
        cont = ee.Image(cimgs.get("cont"))
        hist = ee.Image(cimgs.get("hist"))
        return cont, hist
    
    tloss = None
    tpers = None
    tgain = None
    fetched = []
    toFetch = []
    
    # loop through classes and get all stats for each
    for p1, num in enumerate(sortedValues):
        label = sortedNames[p1]
        cont, hist = contHist(p1)
        
        to = ee.List([])
        frm = ee.List([])
        # to/from for all classes
        for p2, nm in enumerate(sortedValues):
            if p1 == p2:
                continue
            
            cc, hc = contHist(p2)
            lab = sortedNames[p2]
            
            to = to.add(ee.Dictionary({
                "name": lab,
                "area": maskArea(cont.And(hc).selfMask(), geo)
            }))
            frm = frm.add(ee.Dictionary({
                "name": lab,
                "area": maskArea(hist.And(cc).selfMask(), geo)
            }))
        
        contArea = maskArea(cont.selfMask(), geo)
        histArea = maskArea(hist.selfMask(), geo)
        lossMask = hist.subtract(cont).eq(1).selfMask()
        lossArea = maskArea(lossMask, geo)
        perMask = hist.And(cont).selfMask()
        perArea = maskArea(perMask, geo)
        gainMask = cont.subtract(hist).eq(1).selfMask()
        gainArea = maskArea(gainMask, geo)
        
        if class_num == num:
            tloss = lossMask
            tpers = perMask
            tgain = gainMask
        
        if not masksOnly:
            data = {
                "name": label,
                "loss": lossArea,
                "persistence": perArea,
                "gain": gainArea,
                "hist": histArea,
                "cont": contArea,
                "conversions": {
                    "to": to,
                    "from": frm,
                }
            }
            
            toFetch.append(data)
            if len(toFetch) >= 2:
                fetched = fetched.extend(ee.List(toFetch).getInfo())
                toFetch.clear()
    
    if len(toFetch) > 0:
        fetched = fetched.extend(ee.List(toFetch).getInfo())
        toFetch.clear()
    
    return fetched, tloss, tpers, tgain

def lpg_url(mask: ee.Image, color: str) -> str:
    vis = {"palette": color}
    return mask.getMapId(vis)["tile_fetcher"].url_format

def maskArea(mask: ee.Image, geo: ee.Geometry) -> ee.Number:
    return ee.Number(ee.Image.pixelArea().updateMask(mask).reduceRegion(
            reducer = ee.Reducer.sum(),
            geometry = geo,
            scale = 30,
            maxPixels = 1e13,
            bestEffort = True,
    ).get("area")).round()

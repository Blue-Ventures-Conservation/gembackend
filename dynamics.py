import ee
import time

from typing import List

from project import tile_timeout
from classification import combined_classification_lazy
from assets import asset_error, make_export, asset_dl_timeout

def dynamics_export(uid: str, vis: bool, target_class: str, red: str, green: str, blue: str, cont_key: str, hist_key: str, use_cont_spec: bool, num_label: str, char_label: str, roi: dict, buff_dist: int):
    try:
        _, _, lmask, pmask, gmask, coast = dynamics_masks(uid, target_class, cont_key, hist_key, use_cont_spec, num_label, char_label, roi, buff_dist)

        if vis == True:
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

def get_dynamics(uid: str, target_class: str, sub_regions: List[dict], red: str, green: str, blue: str, cont_key: str, hist_key: str, use_cont_spec: bool, num_label: str, char_label: str, roi: dict, buff_dist: int):
    try:
        ctarget, htarget, lmask, pmask, gmask, coast = dynamics_masks(uid, target_class, cont_key, hist_key, use_cont_spec, num_label, char_label, roi, buff_dist)
        
        roi_lpg = lpg_do(ctarget, htarget, lmask, pmask, gmask, coast)
        
        output = {
                "name": roi["name"],
                "stats": {
                    "contemporary_area": roi_lpg["contemporary_area"],
                    "historical_area": roi_lpg["historical_area"],
                    "loss": roi_lpg["loss"],
                    "persistence": roi_lpg["persistence"],
                    "gain": roi_lpg["gain"],
                },
                "loss_url": lpg_url(lmask, red),
                "persistence_url": lpg_url(pmask, green),
                "gain_url": lpg_url(gmask, blue),
                "created_at": int(time.time()),
                "timeout": tile_timeout,
                "sub_region_stats": []
        }
        
        for sr in sub_regions:
            name = sr["name"]
            lpg = lpg_do(ctarget, htarget, lmask, pmask, gmask, ee.Geometry(sr["geometry"]))
            output["sub_region_stats"].append({"name": name, "contemporary_area": lpg["contemporary_area"], "historical_area": lpg["historical_area"], "loss": lpg["loss"], "persistence": lpg["persistence"], "gain": lpg["gain"]})
        
        return output
    except Exception as e:
        raise asset_error(e)

def dynamics_masks(uid: str, target_class: str, cont_key: str, hist_key: str, use_cont_spec: bool, num_label: str, char_label: str, roi: dict, buff_dist: int):
    cont_class, hist_class, coast, class_map = combined_classification_lazy(uid, False, cont_key, hist_key, use_cont_spec, num_label, char_label, None, roi, buff_dist)
    
    class_no = class_map.get(target_class)
    if class_no == None:
        raise Exception("Target class not found in the CRA")
    
    ctarget = cont_class.eq(class_no).clip(coast)
    htarget = hist_class.eq(class_no).clip(coast)
    lmask = htarget.subtract(ctarget).selfMask().rename('loss')
    pmask = htarget.And(ctarget).selfMask().rename('persistence')
    gmask = ctarget.subtract(htarget).selfMask().rename('gain')
    ctarget = ctarget.selfMask()
    htarget = htarget.selfMask()
    
    return ctarget, htarget, lmask, pmask, gmask, coast

def lpg_url(mask: ee.Image, color: str) -> str:
    vis = {"palette": color}
    return mask.getMapId(vis)["tile_fetcher"].url_format

def lpg_do(cont_mask: ee.Image, hist_mask: ee.Image, loss_mask: ee.Image, persist_mask: ee.Image, gain_mask: ee.Image, geo: ee.Geometry) -> dict:
    ctotal = lpg_reduce(geo, cont_mask)
    htotal = lpg_reduce(geo, hist_mask)
    loss = lpg_reduce(geo, loss_mask)
    persist = lpg_reduce(geo, persist_mask)
    gain = lpg_reduce(geo, gain_mask)
    
    return {
        "contemporary_area": ctotal,
        "historical_area": htotal,
        "loss": loss,
        "persistence": persist,
        "gain": gain,
    }

def lpg_reduce(geo: ee.Geometry, mask: ee.Image) -> float:
    return ee.Image.pixelArea().updateMask(mask).reduceRegion(
            reducer = ee.Reducer.sum(),
            geometry = geo,
            scale = 30,
            maxPixels = 1e13,
            bestEffort = True,
            tileScale = 8,
    ).get("area").getInfo()

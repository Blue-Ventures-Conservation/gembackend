import ee

from typing import List

from project import tile_timeout
from classification import combined_classification_lazy
from assets import asset_error

red = "DD4425"
green = "25DDAA"
blue = "25AADD"

def get_dynamics(uid: str, target_class: str, sub_regions: List[dict], cont_key: str, hist_key: str, use_cont_spec: bool, num_label: str, char_label: str, roi: dict, buff_dist: int):
    try:
        cont_class, hist_class, coast, class_map = combined_classification_lazy(uid, cont_key, hist_key, use_cont_spec, num_label, char_label, roi, buff_dist)
         
        class_no = class_map.get(target_class)
        if class_no == None:
            raise Exception("Target class not found in the CRA")
        
        sub_regions = [] + sub_regions
        
        ctarget = cont_class.eq(class_no)
        htarget = hist_class.eq(class_no)
        
        roi_lpg = lpg_do(ctarget, htarget, coast)
        
        output = {
                "name": roi["name"],
                "stats": {
                    "gain": roi_lpg["gain"].getInfo(),
                    "loss": roi_lpg["loss"].getInfo(),
                    "persistence": roi_lpg["persistence"].getInfo(),
                },
                "gain_url": lpg_url(roi_lpg["gain_mask"], blue),
                "loss_url": lpg_url(roi_lpg["loss_mask"], red),
                "persistence_url": lpg_url(roi_lpg["persistence_mask"], green),
                "sub_region_stats": []
        }
        
        for sr in sub_regions:
            name = sr["name"]
            lpg = lpg_do(ctarget, htarget, ee.Geometry(sr["geometry"]))
            output["sub_region_stats"].append({"gain": lpg["gain"].getInfo(), "loss": lpg["loss"].getInfo(), "persistence": lpg["persistence"].getInfo()})
        
        return output
    except Exception as e:
        raise asset_error(e)

def lpg_url(mask: ee.Image, color: str) -> str:
    vis = {"palette": color}
    return mask.getMapId(vis)["tile_fetcher"].url_format

def lpg_do(ctarget: ee.Image, htarget: ee.Image, geo: ee.Geometry) -> dict:
    gain_mask = ctarget.subtract(htarget).eq(1).selfMask()
    loss_mask = htarget.subtract(ctarget).eq(1).selfMask()
    persist_mask = htarget.eq(1).And(ctarget.eq(1)).selfMask()
    
    gain = lpg_reduce(geo, gain_mask)
    loss = lpg_reduce(geo, loss_mask)
    persist = lpg_reduce(geo, persist_mask)
    
    return {
        "gain_mask": gain_mask,
        "loss_mask": loss_mask,
        "persist_mask": persist_mask,
        "gain": gain,
        "loss": loss,
        "persist": persist,
    }

def lpg_reduce(geo: ee.Geometry, mask: ee.Image) -> ee.Number:
    ee.Number(ee.Image.pixelArea().updateMask(mask).reduceRegion(
            reducer = ee.Reducer.sum(),
            geometry = geo,
            scale = 30,
            maxPixels = 1e13,
            bextEffort = True,
    ).get("area"))

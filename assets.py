import ee, logging, uuid

from typing import Tuple, List
import time
import project

asset_users_path = 'projects/{project_id}/assets/users/'
asset_uid_path = asset_users_path+'{uid}'
asset_users_table_path = asset_users_path+'{uid}/{key}'
asset_default_bucket = '{project_id}.appspot.com'
asset_user_shps = 'gs://{bucket}/users/{uid}/shps/{key}.zip'
asset_user_downloads = 'users/{uid}/downloads/{name}_{slug}'
# 47 hours x 60 min x 60 min
asset_dl_timeout = 47 * 60 * 60

class MissingAsset(Exception):
    pass

def make_export(uid: str, img: ee.Image, region: ee.Geometry, name: str) -> str:
    slug = uuid.uuid4().hex
    fprefix = asset_user_downloads.format(uid = uid, name = name, slug = slug)
    bucket = asset_default_bucket.format(project_id = project.project_id)
    task = ee.batch.Export.image.toCloudStorage(
        fileNamePrefix = fprefix,
        bucket = bucket,
        image = img,
        region = region,
        scale = 30,
        maxPixels = 1e13,
    )
    task.start()
    
    return {
        'task': task.status()['name'],
        'path': fprefix + ".tif"
    }

def make_image_assets(uid: str, imgs: List[ee.Image], keys: List[str], region: ee.Geometry, wait: bool) -> List[str]:
    if not create_user_asset_folder(uid):
        return None
    
    assets = []
    ops = []
    for i, img in enumerate(imgs):
        key = keys[i]
        asset_id = asset_name(uid, key)
        
        task = ee.batch.Export.image.toAsset(
            image = img,
            assetId = asset_id,
            region = region,
            scale = 30,
            maxPixels = 1e13,
        )
        task.start()
        assets.append(asset_id)
        ops.append(task.status()['name'])
    
    if wait:
        for i, key in enumerate(keys):
            op = ops[i]
            if not await_asset(uid, key, op):
                return None
    
    return assets

def asset_error(e: Exception) -> Exception:
    estr = str(e)
    if "Collection asset" in estr and "not found." in estr:
        return MissingAsset()
    else:
        return e

def training_poly(uid: str, key: str, num_label: str) -> ee.FeatureCollection:
   name = asset_name(uid, key)
   return ee.FeatureCollection(name).sort(num_label)

def create_user_asset_folder(uid: str) -> bool:
    path = asset_uid_path.format(project_id=project.project_id, uid = uid)
    if folder_exists(path):
        return True
    
    try:
        ee.data.createAsset({'type': ee.data.ASSET_TYPE_FOLDER}, path)
        return True
    except Exception as e:
        if "Cannot overwrite" in str(e):
            return True
        else:
            return False

def upload_table_asset(uid: str, key: str) -> Tuple[str, bool]:
    if not create_user_asset_folder(uid):
        return "", False

    name = asset_name(uid, key)
    if asset_exists(name):
        return "", True

    try:
        shp = asset_user_shps.format(bucket = asset_default_bucket.format(project_id=project.project_id), uid = uid, key = key)
        result = ee.data.startTableIngestion(request_id = ee.data.newTaskId()[0], params = {'name': name, 'sources': [{'uris': [shp], 'charset': 'UTF-8'}]})
        return result['name'], True
    except:
        return "", False

def await_asset(uid: str, key: str, op: str) -> bool:
    name = asset_name(uid, key)
    if asset_exists(name):
        return True
    
    while True:
        ok, err = check_operation(op)
        if err is not None:
            logging.error(err)
            return False
        
        if ok:
            return asset_exists(name)
        
        time.sleep(10)

def check_operation(name: str) -> Tuple[bool, str]:
    try:
        result = ee.data.getOperation(name)
        state = result['metadata']['state']
        pending = state == 'PENDING'
        running = state == 'RUNNING'
        
        if pending or running:
            return False, None
        
        succeeded = state == 'SUCCEEDED'
        
        if succeeded:
            return True, None
        
        message = 'Unknown error'
        if state == 'FAILED':
            message = result['error']['message']
        
        return False, f'Upload operation failed: {message}'
    except Exception as e:
        return False, str(e)

def asset_exists(name: str) -> bool:
    try:
        ee.data.getAsset(name)
        return True
    except:
        return False

def folder_exists(path: str) -> bool:
    try:
        ee.data.listAssets({'parent': path})
        return True
    except:
        return False

def asset_name(uid: str, key: str) -> str:
    return asset_users_table_path.format(project_id=project.project_id, uid = uid, key = key)

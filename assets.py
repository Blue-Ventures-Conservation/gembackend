import ee, logging

from typing import Tuple
from time import sleep
import project

asset_users_path = 'projects/{project_id}/assets/users/'
asset_uid_path = asset_users_path+'{uid}'
asset_users_table_path = asset_users_path+'{uid}/{key}'
asset_user_shps = 'gs://{project_id}.appspot.com/users/{uid}/shps/{key}.zip'

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
        shp = asset_user_shps.format(project_id=project.project_id, uid = uid, key = key)
        result = ee.data.startTableIngestion(request_id = ee.data.newTaskId()[0], params = {'name': name, 'sources': [{'uris': [shp], 'charset': 'UTF-8'}]})
        return result['name'], True
    except:
        return "", False

def await_table_upload(uid: str, key: str, op: str) -> bool:
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
        
        sleep(10)

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

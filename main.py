import os, argparse, ee

import logging
import pprint
from typing import Dict, List, Callable, Any
from inspect import signature
from functools import wraps
from flask import Flask, request, abort, jsonify
from firebase_admin import auth, credentials, initialize_app, storage
from google.auth import compute_engine
import project
from access import *
from roi import *
from assets import *
from separability import *

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False
firebase_app = None
accessor = None

# debug vars
is_debug = True
debug_uid = None
debug_email = None

# https://developers.google.com/earth-engine/guides/service_account#use-a-default-service-account
# set up earth engine and firebase if we're in prod
if "gunicorn" in os.environ.get("SERVER_SOFTWARE", ""): # prod
    firebase_app = initialize_app()
    project.project_id = firebase_app.project_id
    accessor = Accessor()
    ee.Initialize(compute_engine.Credentials(scopes=['https://www.googleapis.com/auth/earthengine']))
    is_debug = False

def token_check(func):
    @wraps(func)
    def wrapper():
        fail = None
        try:
            token = request.headers["Authorization"].split()[1]
            decoded_token = auth.verify_id_token(token, app=firebase_app, check_revoked=True)
            email = decoded_token['email']
            uid = decoded_token['uid']
        except Exception as ex:
            fail = ex
        
        if fail is not None:
            if is_debug:
                uid = debug_uid
                email = debug_email
                print("debug error:", fail, "using uid:", uid, "using email:", email)
            else:
                abort(401) # raise HTTPException

        if not accessor.is_allowed(email):
            abort(403)

        if len(signature(func).parameters) == 1:
            return func(uid)
        else:
            return func()
    
    return wrapper

@app.route("/")
@token_check
def hello_world():
    name = os.environ.get("NAME", "World")
    return "Hello {}!".format(name)

@app.route("/upload_cra", methods=["POST"])
@token_check
def upload_table_route(uid: str):
    content = request.json
    key = content["key"]
    name, success = upload_table_asset(uid, key)
    return jsonify({'key': key, 'success': success, 'name': name})

@app.route("/await_cra_upload", methods=["POST"])
@token_check
def await_table_upload_route(uid: str):
    content = request.json
    success = await_table_upload(uid, content["key"], content["name"])
    return jsonify({'success': success})

@app.route("/area_chart", methods=["POST"])
@token_check
def area_chart_route():
    content = request.json
    chart_data = area_chart(content["polygon"])
    return jsonify(chart_data)

@app.route("/ls_imagery", methods=["POST"])
@token_check
def ls_imagery_route():
    try:
        content = request.json
        visuals = visualize_imagery(content, content["buff_dist"])
    except Exception as e:
        return "", error_check(e)
    
    return jsonify(visuals)

@app.route("/box_chart", methods=["POST"])
@token_check
def box_route(uid: str):
    try:
        content = request.json
        data = box_charts(content["time_period"], uid, content["storage_key"], content["num_label"], content['char_label'], content["roi"], content["roi"]["buff_dist"])
    except Exception as e:
        return "", error_check("/box_chart", content, e)
    
    return jsonify(data)

@app.route("/scatter_chart", methods=["POST"])
@token_check
def scatter_route(uid: str):
    try:
        content = request.json
        data = scatter_chart(content["time_period"], uid, content["storage_key"], content["num_label"], content['char_label'], content["roi"], content["roi"]["buff_dist"])
    except Exception as e:
        return "", error_check("/scatter_chart", content, e)
    
    return jsonify(data)

@app.route("/correlation_chart", methods=["POST"])
@token_check
def corr_route(uid: str):
    try:
        content = request.json
        data = correlation_matrix(content["time_period"], uid, content["storage_key"], content["num_label"], content["roi"], content["roi"]["buff_dist"])
    except Exception as e:
        return "", error_check("/correlation_chart", content, e)
    
    return jsonify(data)

def error_check(route: str, content: dict, e: Exception) -> str:
    t = type(e)
    if t is NoContemporaryImages:
        return "400 no contemporary images"
    if t is NoHistoricalImages:
        return "400 no historical images"
    if t is MissingAsset:
        return "400 missing asset"
    elif t is InvalidTimePeriod:
        return "400 invalid time period"
    else:
        logging.error("Uncaught exception: {}:\n\n{}\n\n{}".format(route, pprint.pformat(content), e))
        return "500"

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--uid", help = "the uid to use in debug mode when auth isn't provided")
    parser.add_argument("--email", help = "the email to use in debug mode when auth isn't provided")
    parser.add_argument("--sa", help = "the service account email to use in debug mode")
    parser.add_argument("--saf", help = "the service account credentials JSON file to use in debug mode")
    args = parser.parse_args()
    
    ee.Initialize(ee.ServiceAccountCredentials(args.sa, args.saf))
    firebase_app = initialize_app(credentials.Certificate(args.saf))
    project.project_id = firebase_app.project_id
    accessor = Accessor()
    debug_uid = args.uid
    debug_email = args.email
    
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

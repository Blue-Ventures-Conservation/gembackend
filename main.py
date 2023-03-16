import os, argparse, ee

from inspect import signature
from functools import wraps
from flask import Flask, request, abort, jsonify
from firebase_admin import auth, credentials, initialize_app
from google.auth import compute_engine
from module1 import *
from assets import *

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False
firebase_app = None

# debug vars
is_debug = True
args = None

# https://developers.google.com/earth-engine/guides/service_account#use-a-default-service-account
def setup():
    if "gunicorn" in os.environ.get("SERVER_SOFTWARE", ""): # prod
        firebase_app = initialize_app()
        ee.Initialize(compute_engine.Credentials(scopes=['https://www.googleapis.com/auth/earthengine']))
        is_debug = False

# set up earth engine and firebase if we're in prod
setup()

def token_check(func):
    @wraps(func)
    def wrapper():
        fail = None
        try:
            token = request.headers["Authorization"].split()[1]
            decoded_token = auth.verify_id_token(token, app=firebase_app, check_revoked=True)
            uid = decoded_token['uid']
        except Exception as ex:
            fail = ex
        
        if fail is not None:
            if is_debug:
                uid = args.uid
                print("debug error:", fail, "using uid:", uid)
            else:
                abort(401) # raise HTTPException

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

@app.route("/upload_table")
@token_check
def upload_table_route(uid: str):
    content = request.json
    success = await_table_upload(uid, content["key"])
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
    content = request.json
    try:
        visuals = visualize_imagery(content, content["buff_dist"])
    except NoHistoricalImages:
        return "No historical images", 400
    except NoContemporaryImages:
        return "No contemporary images", 400
    
    return jsonify(visuals)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--uid", help = "the uid to use in debug mode when auth isn't provided")
    parser.add_argument("--sa", help = "the service account email to use in debug mode")
    parser.add_argument("--saf", help = "the service account credentials JSON file to use in debug mode")
    args = parser.parse_args()
    
    ee.Initialize(ee.ServiceAccountCredentials(args.sa, args.saf))
    firebase_app = initialize_app(credentials.Certificate(args.saf))
    
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

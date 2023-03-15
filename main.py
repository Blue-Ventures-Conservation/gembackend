import os
import ee

from functools import wraps
from flask import Flask, request, abort, jsonify
from firebase_admin import auth, credentials, initialize_app
from google.auth import compute_engine
from module1 import *

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

service_account = 'firebase-adminsdk-sea34@gem-project-378721.iam.gserviceaccount.com'
service_account_file = 'firebase_service_account.json'
firebase_app = None

# https://developers.google.com/earth-engine/guides/service_account#use-a-default-service-account
def setup():
    if "gunicorn" in os.environ.get("SERVER_SOFTWARE", ""): # prod
        firebase_app = initialize_app()
        init_gee(compute_engine.Credentials(scopes=['https://www.googleapis.com/auth/earthengine']))
    else: # locally running, debug server
        init_gee(ee.ServiceAccountCredentials(service_account, service_account_file))
        firebase_app = initialize_app(credentials.Certificate(service_account_file))

# set up earth engine and firebase, based on the local environment
setup()

def token_check(func):
    @wraps(func)
    def wrapper():
        try:
            token = request.headers["Authorization"].split()[1]
            decoded_token = auth.verify_id_token(token, app=firebase_app, check_revoked=True)
            func(decoded_token['uid'])
        except Exception as ex:
            abort(401)
    
    return wrapper

@app.route("/")
@token_check
def hello_world():
    name = os.environ.get("NAME", "World")
    return "Hello {}!".format(name)

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
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

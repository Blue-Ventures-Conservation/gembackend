import os

from flask import Flask, request, jsonify
from gee import *

app = Flask(__name__)


@app.route("/")
def hello_world():
    name = os.environ.get("NAME", "World")
    return "Hello {}!".format(name)

@app.route("/area_chart", methods=["POST"])
def area_chart_route():
    content = request.json
    chart_data = area_chart(content["polygon"])
    return jsonify(chart_data)

@app.route("/ls_imagery", methods=["POST"])
def ls_imagery_route():
    content = request.json
    try:
        serialized = serialize_imagery(content, content["buff_dist"])
    except NoHistoricalImages:
        return "No historical images", 400
    except NoContemporaryImages:
        return "No contemporary images", 400
    
    return jsonify(serialized)

if __name__ == "__main__":
    init_gee()
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

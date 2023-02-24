# GEM Backend

Code for the backend of the GEM app, to be run in Goole Cloud Run. Using python 3.9.2.

### Running the server locally

It is recommended to use `venv` when installing dependencies:
https://docs.python.org/3/library/venv.html

Create the `venv` environment:
`python3 -m venv .`

Then you can activate the environment:
`source bin/activate`


And install the dependencies:
`pip3 install -r requirements.txt`


Exit the `venv` environment when done:
`deactivate`

With the venv active, you can run a development version of the server like so:
`python main.py`


### POST the ROI to the `roi` endpoint

There is some sample input in the `roi_input.json` file.

You can post that to the local server like so, using curl:
```curl
curl -X POST -H "Content-Type: application/json" -d @roi_input.json http://localhost:8080/roi
```

### Uploading CRAs

CRA shapefiles are added to the Firebase default bucket, under a user-specific path, by the app.

When installing Google Earth Engine's python API, a command line tool is also installed that helps
make managing assets a little easier. When a CRA is needed for some task, the bucket path to that
CRA will be sent to the server by the app, and the server can then upload that CRA into GEE by
shelling out to the command line tool with a command similar to this:
`earthengine --service_account_file=firebase_service_account.json upload table --asset_id=projects/gem-project-378721/assets/CRAs/users/ABC123/SDGS1243123ASDF gs://gem-project-378721.appspot.com/users/ABC123/SDGS1243123ASDF_MyCRA.zip`

If the user is a new one, we first create a new folder for that user like so:
`earthengine --service_account_file=firebase_service_account.json create folder projects/gem-project-378721/assets/CRAs/users/ABC123`

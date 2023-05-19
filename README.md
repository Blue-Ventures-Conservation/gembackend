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

### IAM principal roles

The backend uses a Firebase Admin SDK service account for pretty much everything. When Firebase is setup on a project, this service account is created automatically.

We manually create the credentials for this service account, and that is what is in the `firebase_service_account.json` file referenced in a few places.
This file can only be downloaded once, but it is also available in Google Cloud's Secret Manager, which is in the Security section of the interface.

In addition to creating the credentials, we also edit the roles for this principal in IAM by add the role: `Earth Engine Resource Admin`

Earth Engine itself also wants to know about your cloud project, and you can link them up here:
https://cloud.google.com/earth-engine

This will enable the Google Earth Engine API for the project, and create a project in Google Earth Engine with the same name, and an assets folder:
`projects/project_name/assets`

### Cloud Run Deploy

We run the server in GCloud's [Cloud Run service](https://cloud.google.com/run), which is a serverless technology that should save money
when the GEM is not in use, which should be most of the time.

We build and deploy using the `gcloud` cli, essentially following the instructions [here](https://firebase.google.com/docs/hosting/cloud-run#python).

The Cloud Run service is called `gembackend`, managed under the Firebase project `GEM Project`. This project is owned by `courtland.fowler@blueventures.org`.

The only changes from the default settings for this service are lengthening the timeout from 300 to 600 seconds, and setting the firebase sdk admin service account
as the service account for the service under the security tab when editing and deploying.

Cloud Run creates a service URL for the service. This URL is probably safe to deploy with for now.

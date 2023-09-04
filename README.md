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
curl -v -H "Content-Type: application/json" -d @roi_input.json http://127.0.0.1:8080/roi
```

### IAM principal roles

The backend uses a Firebase Admin SDK service account for pretty much everything. When Firebase is setup on a project, this service account is created automatically.

We manually create the credentials for this service account in the form of a `firebase_service_account.json` file that is added to gitignore and should never be committed to git.
This file can only be downloaded once, but it is also available in Google Cloud's Secret Manager, which is in the Security section of the interface.

The service account credentials file `firebase_service_account.json` is only used when running the server locally. In production, these credentials are avilable to the running
service automatically and the JSON file is not included in the Dockerfile for this reason (see the `Cloud Run Deploy` section below for more).

In addition to creating the credentials, we also edit the roles for this principal in IAM to add the role: `Earth Engine Resource Admin`

Earth Engine itself also wants to know about your cloud project, and you can link them up here:
https://cloud.google.com/earth-engine

This will enable the Google Earth Engine API for the project, and create a project in Google Earth Engine with the same project ID, and an assets folder:
`projects/{PROJECT_ID}/assets`

To get the `PROJECT_ID`, view project settings in the firebase console.

### Cloud Run Deploy

We run the server in GCloud's [Cloud Run service](https://cloud.google.com/run), which is a serverless technology that should save money
when the GEM is not in use, which should be most of the time.

We build and deploy using the `gcloud` cli, essentially following the instructions [here](https://firebase.google.com/docs/hosting/cloud-run#python).

To get the `PROJECT_ID`, view project settings in the firebase console.

From the root directory that contains the Dockerfile, build the project and submit it to GCloud Container Registry:
```
gcloud builds submit --tag gcr.io/{PROJECT_ID}/gembackend
```

And then to deploy to cloud run:
```
gcloud run deploy --image gcr.io/{PROJECT_ID}/gembackend
```

We currently use `me-west1` for the location of this deploy, which is the closest location to Eastern Africa and Madagascar.

The Cloud Run service is called `gembackend`, managed under the Firebase project `GEM Project`. This project is owned by `courtland.fowler@blueventures.org`.

The only changes from the default settings for this service are lengthening the timeout from 300 to 600 seconds, and setting the firebase sdk admin service account
as the service account for the service under the security tab when editing and deploying.

Cloud Run creates a service URL for the service. This URL is probably safe to deploy with for now.

### Cloud Storage

We use Google Cloud Storage to manage files on behalf of users, things like CRAs.

We also use GCS to handle downloads of images from GEE, as a temporary storage location from which the imagery
can be downloaded to users' local devices. These files are subject to a lifecycle rule, that has been set
on the default bucket in the gcloud console enforcing a lifetime of 1 day for these files, afterwhich they are deleted.

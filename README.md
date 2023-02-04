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


### POST the ROI to the `roi` endpoint

There is some sample input in the `roi_input.json` file.

You can post that to the local server like so, using curl:
```curl
curl -X POST -H "Content-Type: application/json" -d @roi_input.json http://localhost:8080/roi
```

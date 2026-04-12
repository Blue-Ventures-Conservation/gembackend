# Use the official lightweight Python image.
# https://hub.docker.com/_/python
FROM python:3.9-slim

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True

ENV APP_HOME /app
WORKDIR $APP_HOME

# Copy dependency manifest
COPY requirements.txt ./

# Install production dependencies.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential
RUN pip install --no-cache-dir -r requirements.txt

# Copy local code to the container image.
COPY main.py ./
COPY access.py ./
COPY project.py ./
COPY roi.py ./
COPY assets.py ./
COPY imagery.py ./
COPY classification.py ./
COPY separability.py ./
COPY dynamics.py ./

# Run the web service on container startup. Here we use the gunicorn
# webserver, with one worker process and 8 threads.
# For environments with multiple CPU cores, increase the number of workers
# to be equal to the cores available.
# Timeout is set to 0 to disable the timeouts of the workers to allow Cloud Run to handle instance scaling.
# We use gevent workers because most of the work is I/O bound, and these workers will do non-blocking I/O.
# The recommended number of workers is (2*CPU)+1, and we have one core, so workers=3.
CMD exec gunicorn --worker-class gevent --worker-connections 100 --workers 3 --bind :$PORT --timeout 0 main:app

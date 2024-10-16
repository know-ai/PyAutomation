#!/bin/sh

gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 --worker-connections 100 -b 0.0.0.0:8050 wsgi:server


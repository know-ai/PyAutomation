#!/bin/sh

CERTFILE=${CERT_FILE:-""}
KEYFILE=${KEY_FILE:-""}
WORKER_CONNECTIONS=${WORKER_CONNECTIONS:-100}
WORKERS=${WORKERS:-1}
THREADS=${THREADS:-10}
PORT=${PORT:-8050}

if [ -f "$CERTFILE" ];
    
then

    echo "\033[36m[INFO]\033[m - Reading $CERTFILE file"
    echo "\033[32m[OK]\033[m - $CERTFILE Readed"

    if [ -f "$KEYFILE" ];
    
    then

        echo "\033[36m[INFO]\033[m - Reading $KEYFILE file"
        echo "\033[32m[OK]\033[m - $KEYFILE Readed"
        echo "\033[32m[OK]\033[m - Worker connections: $WORKER_CONNECTIONS"
        echo "\033[32m[OK]\033[m - Number of workers: $WORKERS"
        gunicorn -c gunicorn.conf.py -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w $WORKERS --worker-connections $WORKER_CONNECTIONS --certfile=$CERTFILE --keyfile=$KEYFILE --threads $THREADS -b 0.0.0.0:$PORT wsgi:server
        
    else
        echo "\033[33m[WARNING]\033[m - $KEYFILE Not Found service without SSL Certificate"
        echo "\033[32m[OK]\033[m - Worker connections: $WORKER_CONNECTIONS"
        echo "\033[32m[OK]\033[m - Number of workers: $WORKERS"
        gunicorn -c gunicorn.conf.py -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w $WORKERS --worker-connections $WORKER_CONNECTIONS --threads $THREADS -b 0.0.0.0:$PORT wsgi:server
    fi

else

    echo "\033[33m[WARNING]\033[m - $CERTFILE Not Found service without SSL Certificate"
    echo "\033[32m[OK]\033[m - Worker connections: $WORKER_CONNECTIONS"
    echo "\033[32m[OK]\033[m - Number of workers: $WORKERS"
    gunicorn -c gunicorn.conf.py -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w $WORKERS --worker-connections $WORKER_CONNECTIONS --threads $THREADS -b 0.0.0.0:$PORT wsgi:server

fi


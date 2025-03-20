FROM python:3.10.12-alpine

WORKDIR /app

LABEL author="KnowAI"

LABEL description="PyAutomation System"

RUN apk update && apk add curl util-linux

# Instalar dependencias necesarias para compilar numpy (sin libexecinfo-dev)
RUN apk add --no-cache \
    build-base \
    musl-dev \
    gfortran \
    openblas-dev \
    linux-headers \
    && ln -s /usr/include/locale.h /usr/include/xlocale.h

    
RUN pip3 install --upgrade pip
RUN pip3 install setuptools wheel


COPY . .
COPY requirements.txt requirements.txt

RUN pip3 install -r requirements.txt

RUN chmod +x ./docker-entrypoint.sh

ENV PORT=8050
ENV OPCUA_SERVER_PORT=53530

EXPOSE ${PORT}
EXPOSE ${OPCUA_SERVER_PORT}

ENTRYPOINT ["./docker-entrypoint.sh"]

HEALTHCHECK --interval=5s --timeout=10s --start-period=55s \
  CMD curl -f --retry 5 --max-time 15 --retry-delay 5 --retry-max-time 60 "http://127.0.0.1:${PORT}/api/healthcheck/" || \
      curl -f --retry 5 --max-time 15 --retry-delay 5 --retry-max-time 60 "https://127.0.0.1:${PORT}/api/healthcheck/" || exit 1
 
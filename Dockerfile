# Build stage: git is needed only to fetch the pinned git dependency in
# requirements.txt, so it lives here and never reaches the runtime image.
FROM python:3.11.17-slim-trixie AS build
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install -U pip
# Install into a standalone prefix that is copied onto /usr/local below, so the
# runtime image has the same interpreter and site-packages layout as before.
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11.17-slim-trixie
RUN apt-get update && apt-get upgrade -y && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /install /usr/local

RUN useradd --system --uid 10001 --user-group --no-create-home app

WORKDIR /app
COPY . .
# The bot creates logs/ in its working directory at startup (util/logging_config.py).
RUN mkdir -p /app/logs && chown app:app /app/logs

USER app

#HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 CMD curl -f http://localhost:8000/live || exit 1

ENTRYPOINT ["python", "main.py"]

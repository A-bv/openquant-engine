# Hugging Face Space — build and serve the OpenQuant FastAPI engine.
#
# The Space holds only this Dockerfile and a README; it clones the engine at
# build time, installs it as a package, and serves it. To ship a new version,
# hit "Factory rebuild" on the Space — it pulls the latest main. No secrets,
# no payment method.
FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN git clone --depth 1 https://github.com/A-bv/openquant-engine.git . \
    && pip install --no-cache-dir ".[api]"

# The container runs as a non-root user on HF; make the fetch cache writable.
RUN mkdir -p /app/data/cache && chmod -R 777 /app/data

EXPOSE 7860
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "7860"]

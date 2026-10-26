# Minimal disposable toolbox for the owned loopback HTTP analysis only.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl bash \
 && rm -rf /var/lib/apt/lists/*
CMD ["sleep", "infinity"]

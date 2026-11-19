# Sandbox image: runs a PR's tests. No repo dependencies are installed (no network at run time).
FROM python:3.12-slim
RUN pip install --no-cache-dir pytest==9.2.0 \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin runner
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
USER 10001:10001
WORKDIR /src

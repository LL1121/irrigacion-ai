FROM python:3.11-slim

RUN pip install --no-cache-dir python-docx==1.1.2 \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin sandboxuser

WORKDIR /tmp

USER sandboxuser

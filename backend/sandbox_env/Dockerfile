FROM python:3.11-slim

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin sandboxuser

WORKDIR /tmp

USER sandboxuser

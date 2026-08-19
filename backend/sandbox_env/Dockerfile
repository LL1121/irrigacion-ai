FROM python:3.11-slim

RUN pip install --no-cache-dir \
        python-docx==1.1.2 \
        requests==2.32.3 \
        httpx==0.28.1 \
        beautifulsoup4==4.12.3 \
        lxml==5.3.0 \
        pandas==2.2.3 \
        numpy==2.1.3 \
        openpyxl==3.1.5 \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin sandboxuser

WORKDIR /tmp

USER sandboxuser

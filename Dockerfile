FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    ocrmypdf ghostscript tesseract-ocr tesseract-ocr-eng qpdf unpaper pngquant \
    potrace \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt /srv/requirements.txt

RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r /srv/requirements.txt

COPY app /srv/app
COPY engine /srv/engine

ENV JOBS_DIR=/data/jobs
RUN mkdir -p /data/jobs

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

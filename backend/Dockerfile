FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PIP_DEFAULT_TIMEOUT=300

RUN echo "[global]" > /etc/pip.conf \
 && echo "index-url = ${PIP_INDEX_URL}" >> /etc/pip.conf \
 && echo "trusted-host = mirrors.aliyun.com" >> /etc/pip.conf \
 && echo "timeout = 300" >> /etc/pip.conf \
 && echo "retries = 10" >> /etc/pip.conf

COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY . .

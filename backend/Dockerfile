FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PIP_DEFAULT_TIMEOUT=180

COPY requirements.txt .
RUN pip install -i "${PIP_INDEX_URL}" --trusted-host mirrors.aliyun.com --upgrade pip \
 && pip install -i "${PIP_INDEX_URL}" --trusted-host mirrors.aliyun.com --no-cache-dir -r requirements.txt

COPY . .

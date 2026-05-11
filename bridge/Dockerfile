FROM python:3.12-slim
WORKDIR /app

# 国内/Hetzner 等链路访问 PyPI 易超时：默认阿里云镜像；海外构建可传 --build-arg PIP_INDEX_URL=https://pypi.org/simple/
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PIP_DEFAULT_TIMEOUT=180

COPY requirements.txt .
RUN pip install -i "${PIP_INDEX_URL}" --trusted-host mirrors.aliyun.com --upgrade pip \
 && pip install -i "${PIP_INDEX_URL}" --trusted-host mirrors.aliyun.com --no-cache-dir -r requirements.txt

COPY main.py .
EXPOSE 9000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]

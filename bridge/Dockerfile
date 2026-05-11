FROM python:3.12-slim
WORKDIR /app

# 国内访问 PyPI CDN（files.pythonhosted.org）易超时：默认走阿里云镜像。
# 服务器若仍出现 ReadTimeoutError + host=files.pythonhosted.org，说明构建用的是旧 Dockerfile（未 git pull）或未 --no-cache。
# 海外构建：docker compose build --build-arg PIP_INDEX_URL=https://pypi.org/simple/ bridge
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

COPY main.py .
EXPOSE 9000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]

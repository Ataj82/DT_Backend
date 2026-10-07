# If Docker Hub is blocked, you can use Runflare's registry mirror by changing this to:
# FROM docker.runflare.com/library/python:3.11-slim
FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing .pyc files and keep stdout unbuffered
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN set -eux; \
    rm -f /etc/apt/sources.list; \
    rm -f /etc/apt/sources.list.d/debian.sources; \
    rm -f /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources || true; \
    . /etc/os-release; \
    echo "deb http://mirror.arvancloud.ir/debian ${VERSION_CODENAME} main contrib non-free non-free-firmware" > /etc/apt/sources.list; \
    echo "deb http://mirror.arvancloud.ir/debian ${VERSION_CODENAME}-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list; \
    echo "deb http://mirror.arvancloud.ir/debian-security ${VERSION_CODENAME}-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list && \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*
# ---------------------------------------------------
# PyPI Index Configuration (Official PyPI + Aliyun Fallback)
# ---------------------------------------------------
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_EXTRA_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
ENV PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL}
ENV PIP_DEFAULT_TIMEOUT=100
ENV PIP_TRUSTED_HOST="pypi.org files.pythonhosted.org mirrors.aliyun.com"

# Copy only requirements first to cache the pip install step
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . /app/
# Expose the internal port
EXPOSE 7000
ENV PYTHONPATH=/app

# Start Uvicorn directly
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7000"]

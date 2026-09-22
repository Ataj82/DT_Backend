# If Docker Hub is blocked, you can use Runflare's registry mirror by changing this to:
# FROM docker.runflare.com/library/python:3.11-slim
FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing .pyc files and keep stdout unbuffered
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN set -eux;     rm -f /etc/apt/sources.list;     rm -f /etc/apt/sources.list.d/debian.sources;     rm -f /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources || true;     . /etc/os-release;     echo "deb http://mirror-linux.runflare.com/debian ${VERSION_CODENAME} main contrib non-free non-free-firmware" > /etc/apt/sources.list;     echo "deb http://mirror-linux.runflare.com/debian ${VERSION_CODENAME}-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list;     echo "deb http://security.debian.org/debian-security ${VERSION_CODENAME}-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list
# ---------------------------------------------------
# Set Runflare Mirror for pip
# ---------------------------------------------------
ENV PIP_INDEX_URL=https://pypi.devneeds.ir/simple/


# Copy only requirements first to cache the pip install step
COPY requirements.txt .

# Install dependencies using the mirror
RUN pip install --no-cache-dir --upgrade pip &&     pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . /app/
# Expose the internal port
EXPOSE 7000
ENV PYTHONPATH=/app

# Start Uvicorn directly
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7000"]

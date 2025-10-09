FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app
COPY . /app

# Устанавливаем системные зависимости: git для pip+git, build tools и SSL/ffi headers
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    gcc \
    libssl-dev \
    libffi-dev \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Обновляем pip и ставим pyaes из GitHub перед Telethon
RUN python -m pip install --upgrade pip setuptools wheel \
 && pip install --no-cache-dir git+https://github.com/ricmoo/pyaes.git@master#egg=pyaes \
 && pip install --no-cache-dir -r requirements.txt

ENV PYTHONUNBUFFERED=1
CMD ["python", "main.py"]

FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN python -m pip install --upgrade pip setuptools wheel \
 && pip install --no-cache-dir git+https://github.com/ricmoo/pyaes.git@master#egg=pyaes \
 && pip install --no-cache-dir -r requirements.txt

ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]

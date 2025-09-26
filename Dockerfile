FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --upgrade pip setuptools wheel \
 && pip install -r requirements.txt
ENV PLAY=""
ENV CHANNEL=""
ENV ADMIN_ID=""
CMD ["bash", "start.sh"]

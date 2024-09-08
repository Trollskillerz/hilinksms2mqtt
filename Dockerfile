FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY huawei_sms_mqtt_bridge.py .
COPY .env .

CMD ["python", "huawei_sms_mqtt_bridge.py"]

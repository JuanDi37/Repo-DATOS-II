import os
import json
import uuid
import datetime

from flask import Flask, request, jsonify
from flask_cors import CORS
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST, REGISTRY
import pika
import boto3
from pydantic import ValidationError

from validation import (
    ImpressionPayload, ClickPayload, ConversionPayload
)

# --------- Prometheus metrics ----------
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'http_status'])
REQUEST_LATENCY = Histogram('http_request_latency_seconds', 'Latency of HTTP requests', ['method', 'endpoint'])
ad_impressions = Counter('api_ad_impressions_total', 'Total ad impressions', ['campaign', 'ad', 'state'])
ad_clicks      = Counter('api_ad_clicks_total', 'Total ad clicks', ['campaign', 'ad', 'state'])
ad_conversions = Counter('api_ad_conversions_total', 'Total ad conversions', ['campaign', 'ad', 'state'])

# --------- Flask init ----------
app = Flask(__name__)
CORS(app)

# --------- RabbitMQ persistent connection ----------
RABBIT_HOST = os.getenv('RABBITMQ_HOST', 'rabbitmq')
_rabbit_conn = None
_rabbit_ch   = None

def get_rabbit_channel():
    global _rabbit_conn, _rabbit_ch
    if not _rabbit_conn or _rabbit_conn.is_closed:
        params = pika.ConnectionParameters(host=RABBIT_HOST, heartbeat=600, blocked_connection_timeout=300)
        _rabbit_conn = pika.BlockingConnection(params)
        _rabbit_ch   = _rabbit_conn.channel()
    return _rabbit_ch

def publish_to_queue(queue_name, payload):
    ch = get_rabbit_channel()
    ch.queue_declare(queue=queue_name, durable=True)
    try:
        ch.basic_publish(
            exchange='',
            routing_key=queue_name,
            body=json.dumps(payload),
            properties=pika.BasicProperties(delivery_mode=2)
        )
    except Exception:
        # dead-letter queue
        dlq = f'{queue_name}-dlq'
        ch.queue_declare(queue=dlq, durable=True)
        ch.basic_publish(
            exchange='', routing_key=dlq,
            body=json.dumps(payload),
            properties=pika.BasicProperties(delivery_mode=2)
        )

# --------- S3 (MinIO) ----------
S3_BUCKET = os.getenv('S3_BUCKET', 'raw-events')
s3 = boto3.client(
    's3',
    endpoint_url=os.getenv('S3_ENDPOINT_URL'),
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_REGION')
)
try:
    s3.head_bucket(Bucket=S3_BUCKET)
except:
    s3.create_bucket(Bucket=S3_BUCKET)

def store_raw(event_type, payload):
    now = datetime.datetime.utcnow()
    key = f"{event_type}/{now:%Y/%m/%d/%H%M%S}_{uuid.uuid4()}.json"
    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=json.dumps(payload), ContentType='application/json')

# --------- Decorator for metrics ----------
from functools import wraps
def monitor(path):
    def deco(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            method = request.method
            with REQUEST_LATENCY.labels(method, path).time():
                try:
                    resp = f(*args, **kwargs)
                except Exception:
                    REQUEST_COUNT.labels(method, path, '500').inc()
                    raise
            status = resp[1] if isinstance(resp, tuple) else resp.status_code
            REQUEST_COUNT.labels(method, path, str(status)).inc()
            return resp
        return wrapped
    return deco

# --------- Endpoints ----------

@app.route('/metrics')
def metrics():
    return generate_latest(REGISTRY), 200, {'Content-Type': CONTENT_TYPE_LATEST}

@app.route('/api/events/impression', methods=['POST'])
@monitor('/api/events/impression')
def impression():
    try:
        model   = ImpressionPayload(**request.get_json())
        payload = json.loads(model.json())
    except ValidationError as e:
        return jsonify({'error': e.errors()}), 400

    for ad in payload['ads']:
        ad_impressions.labels(
            campaign=ad['campaign']['campaign_id'],
            ad=ad['ad']['ad_id'],
            state=payload['state']
        ).inc()

    publish_to_queue('impression', payload)
    store_raw('impression', payload)
    return jsonify({'status': 'ok'}), 200

@app.route('/api/events/click', methods=['POST'])
@monitor('/api/events/click')
def click():
    try:
        model   = ClickPayload(**request.get_json())
        payload = json.loads(model.json())
    except ValidationError as e:
        return jsonify({'error': e.errors()}), 400

    ad_clicks.labels(
        campaign=payload['clicked_ad']['ad_id'],
        ad=payload['clicked_ad']['ad_id'],
        state=payload['user_info']['state']
    ).inc()

    publish_to_queue('click', payload)
    store_raw('click', payload)
    return jsonify({'status': 'ok'}), 200

@app.route('/api/events/conversion', methods=['POST'])
@monitor('/api/events/conversion')
def conversion():
    try:
        model   = ConversionPayload(**request.get_json())
        payload = json.loads(model.json())
    except ValidationError as e:
        return jsonify({'error': e.errors()}), 400

    ad_conversions.labels(
        campaign='unknown',
        ad=payload['conversion_attributes']['items'][0]['product_id'],
        state=payload['user_info']['state']
    ).inc()

    publish_to_queue('conversion', payload)
    store_raw('conversion', payload)
    return jsonify({'status': 'ok'}), 200

@app.route('/')
def health():
    return jsonify({'status': 'healthy'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

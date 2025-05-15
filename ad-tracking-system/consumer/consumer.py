import os
import json
import time
import ipaddress
import pika
from prometheus_client import Counter, start_http_server

from aggregator import Aggregator

# Métricas Prometheus para el consumer
IMPR_C  = Counter('consumer_impressions_total',   'Impressions consumed')
CLICK_C = Counter('consumer_clicks_total',        'Clicks consumed')
CONV_C  = Counter('consumer_conversions_total',   'Conversions consumed')

# Inicializa el agregador (flush cada 60s por defecto)
agg = Aggregator(interval=60)

def connect_rabbitmq(retries: int = 10, delay: int = 3):
    """Intenta conectarse a RabbitMQ con reintentos."""
    params = pika.ConnectionParameters(host=os.getenv('RABBITMQ_HOST', 'rabbitmq'))
    for attempt in range(1, retries + 1):
        try:
            conn = pika.BlockingConnection(params)
            print("Conectado a RabbitMQ")
            return conn
        except pika.exceptions.AMQPConnectionError:
            print(f"RabbitMQ no disponible, reintentando en {delay}s ({attempt}/{retries})")
            time.sleep(delay)
    raise RuntimeError("No se pudo conectar a RabbitMQ tras varios intentos")

def callback(ch, method, props, body):
    data = json.loads(body)
    ev_type = method.routing_key  # "impression" | "click" | "conversion"

    # Estado
    state = data.get('state') or data.get('user_info', {}).get('state', 'unknown')
    # Search keyword
    keyword = data.get('search_keywords', '')

    # IP range /24
    raw_ip = data.get('user_ip') or data.get('user_info', {}).get('user_ip')
    if raw_ip:
        try:
            net = ipaddress.ip_network(f"{raw_ip}/24", strict=False)
            ip_range = str(net)
        except ValueError:
            ip_range = 'invalid'
    else:
        ip_range = 'unknown'

    if ev_type == 'impression':
        for ad in data['ads']:
            agg.add(
                'impression',
                state,
                ip_range,
                ad['campaign']['campaign_id'],
                ad['ad']['ad_id'],
                keyword
            )
        IMPR_C.inc()

    elif ev_type == 'click':
        ad = data['clicked_ad']
        agg.add(
            'click',
            state,
            ip_range,
            data['impression_id'],
            ad['ad_id'],
            keyword
        )
        CLICK_C.inc()

    else:  # conversion
        item = data['conversion_attributes']['items'][0]
        campaign = data.get('campaign_id', data.get('impression_id'))
        agg.add(
            'conversion',
            state,
            ip_range,
            campaign,
            item['product_id'],
            keyword,
            value=data.get('conversion_value', 0.0)
        )
        CONV_C.inc()

    ch.basic_ack(delivery_tag=method.delivery_tag)

def main():
    # 1) Exponer métricas Prometheus en el puerto 8000
    start_http_server(8000)

    # 2) Conectar a RabbitMQ con reintentos
    conn = connect_rabbitmq()
    ch   = conn.channel()

    # 3) Declarar colas y configurar consumo
    for queue in ['impression', 'click', 'conversion']:
        ch.queue_declare(queue=queue, durable=True)
        ch.basic_qos(prefetch_count=1)
        ch.basic_consume(queue=queue, on_message_callback=callback)

    print("Consumer corriendo, exponiendo métricas en :8000")
    ch.start_consuming()

if __name__ == '__main__':
    main()

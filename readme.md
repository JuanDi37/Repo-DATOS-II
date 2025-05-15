# Ad Tracking Analytics System

## Overview

Este proyecto implementa un sistema de tracking, procesamiento y análisis en tiempo real de eventos de publicidad digital. Está compuesto por:

* **API** (Flask + Gunicorn) con 3 endpoints REST para recibir eventos de impresión, clic y conversión. Valida payloads con Pydantic.
* **RabbitMQ** para encolado asíncrono de eventos, con colas dedicadas (`impression`, `click`, `conversion`) y dead-letter queues.
* **Consumer & Aggregator** (Python) que consume de RabbitMQ, agrega métricas por minuto, estado, rango IP `/24`, campaña, anuncio y palabra clave, y calcula CTR / CR / revenue.
* **TimescaleDB** (PostgreSQL + TimescaleDB) para almacenar métricas agregadas en una hypertable `ad_metrics`.
* **MinIO** (S3-compatible) para persistir los eventos crudos en JSON, particionados por fecha.
* **Prometheus** para recolectar métricas del API, del consumer y de la profundidad de colas (exporter de RabbitMQ).
* **Grafana** para visualizar dashboards:

  * Métricas por IP-range en la última hora.
  * Profundidad de las colas de RabbitMQ.
  * CTR, conversion rate, throughput.

## Estructura del Repositorio

```
├── api
│   ├── app.py           # API Flask + Pydantic
│   ├── validation.py    # Modelos Pydantic
│   ├── requirements.txt
│   └── Dockerfile
├── consumer
│   ├── consumer.py      # Lógica de consumo + flush a TSDB
│   ├── aggregator.py    # Clase Aggregator con ip_range
│   ├── requirements.txt
│   └── Dockerfile
├── tsdb
│   └── init_timescaledb.sql  # SQL para crear hypertable con ip_range
├── reporting
│   ├── sample_queries.sql    # Consultas de ejemplo
│   └── sample_*.json         # Payloads de prueba
├── prometheus
│   └── prometheus.yml        # Configuración de scrape
├── docker-compose.yml
└── .env                       # Variables de entorno
```

## 1. API Endpoints

Todos los endpoints validan con Pydantic, actualizan métricas Prometheus y envían a RabbitMQ + MinIO.

### a) Impresión

* **Ruta**: `POST /api/events/impression`
* **Payload**: `ImpressionPayload`
* **Flujos**:

  1. Validación del JSON.
  2. `ad_impressions_total` en Prometheus.
  3. `publish_to_queue("impression", payload)`.
  4. `store_raw("impression", payload)` en S3-partitioned.
  5. Respuesta `200 {"status":"ok"}`.

### b) Clic

* **Ruta**: `POST /api/events/click`
* **Payload**: `ClickPayload`
* **Flujos** similares: incrementa `ad_clicks_total`, encola y almacena raw.

### c) Conversión

* **Ruta**: `POST /api/events/conversion`
* **Payload**: `ConversionPayload`
* **Flujos**: incrementa `ad_conversions_total`, encola y almacena raw.

## 2. Cola (RabbitMQ)

* Colas: `impression`, `click`, `conversion` (durables).
* Dead-letter: si `basic_publish` falla, reencola en `${queue}-dlq`.
* `consumer` espera con `connect_rabbitmq()` con reintentos.

## 3. Consumer & Aggregator

### consumer.py

```python
# Conexión y retry a RabbitMQ
conn = connect_rabbitmq()
# Métricas Prometheus: consumer_*_total
# Consumo de colas y callback
```

### aggregator.py

```python
class Aggregator:
    data keyed by (bucket_minuto, state, ip_range, campaign, ad, keyword)
    flush() cada 60s → INSERT a TimescaleDB con columnas:
      time, state, ip_range, campaign_id, ad_id, search_keyword,
      impression_count, click_count, conversion_count, revenue, ctr, conversion_rate
```

* **IP-range**: extraído de `user_ip` en `/24` con `ipaddress.ip_network`.

## 4. TimescaleDB

* **init\_timescaledb.sql**:

  ```sql
  CREATE EXTENSION IF NOT EXISTS timescaledb;
  CREATE TABLE ad_metrics (
    time TIMESTAMPTZ NOT NULL,
    state TEXT,
    ip_range TEXT,
    campaign_id TEXT,
    ad_id TEXT,
    search_keyword TEXT,
    impression_count BIGINT,
    click_count BIGINT,
    conversion_count BIGINT,
    revenue DOUBLE PRECISION,
    ctr DOUBLE PRECISION,
    conversion_rate DOUBLE PRECISION
  );
  SELECT create_hypertable('ad_metrics','time');
  ```
* **ALTER** existente: `ADD COLUMN IF NOT EXISTS ip_range TEXT;`.

## 5. Raw Events en S3 (MinIO)

* Bucket: `raw-events`.
* Ruta: `/{event_type}/YYYY/MM/DD/HHMMSS_uuid.json`.
* Acceso UI: [http://localhost:9001](http://localhost:9001) (minioadmin/minioadmin).

## 6. Observabilidad (Prometheus + Grafana)

### prometheus.yml

```yaml
scrape_configs:
  - job_name: api       # api:5000/metrics
  - job_name: consumer  # consumer:8000/metrics
  - job_name: rabbitmq-queues  # exporter:9419/metrics
  - job_name: minio     # minio metrics endpoint
```

### rabbitmq-exporter

* Servicio en docker-compose, expone métricas de colas.

### Grafana Dashboards

* **TimescaleDB Panel**: SQL `GROUP BY ip_range` en última hora.
* **RabbitMQ Panel**: `sum(rabbitmq_queue_messages_ready) by(queue)`.
* **API Rate**: `sum(rate(api_ad_impressions_total[1m]))`.

## 7. Deploy & Test

1. `docker-compose up -d --build`
2. Inicializar TSDB: `psql -f tsdb/init_timescaledb.sql` y `ALTER TABLE… ADD COLUMN ip_range`.
3. Enviar payloads de `reporting/sample_*.json` con curl/Invoke-WebRequest.
4. Esperar flush (60s).
5. Ver raw en MinIO, métricas en Prometheus UI y Grafana.

## 8. Sample Queries

Archivo `reporting/sample_queries.sql` con ejemplos de:

* Dashboard última hora (time\_bucket 1m)
* Resumen diario
* Performance por keyword
* Performance geográfica

---

**¡El sistema está listo para producción!**

* API escalable (Gunicorn)
* Colas distribuidas (RabbitMQ)
* TSDB optimizada (TimescaleDB)
* Raw events en S3 (MinIO)
* Observabilidad completa (Prometheus + Grafana)
* Manejo de errores y DLQ

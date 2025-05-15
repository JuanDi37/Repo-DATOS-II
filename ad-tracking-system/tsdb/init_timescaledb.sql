-- habilitar TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- tabla de métricas
CREATE TABLE IF NOT EXISTS ad_metrics (
  time TIMESTAMPTZ NOT NULL,
  state TEXT,
  campaign_id TEXT,
  ad_id TEXT,
  search_keyword TEXT,
  impression_count INTEGER,
  click_count INTEGER,
  conversion_count INTEGER,
  revenue DOUBLE PRECISION,
  ctr DOUBLE PRECISION,
  conversion_rate DOUBLE PRECISION
);

-- convertir a hypertable
SELECT create_hypertable('ad_metrics','time', if_not_exists => TRUE);


-- init_timescaledb.sql
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS ad_metrics (
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

SELECT create_hypertable('ad_metrics', 'time', if_not_exists => TRUE);

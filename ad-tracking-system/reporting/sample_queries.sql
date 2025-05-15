-- 1) Dashboard última hora (agrupado por minuto)
SELECT
  time_bucket('1 minute', time) AS minute,
  SUM(impression_count)::int AS impressions,
  SUM(click_count)::int       AS clicks,
  SUM(conversion_count)::int  AS conversions
FROM ad_metrics
WHERE time > NOW() - INTERVAL '1 hour'
GROUP BY minute
ORDER BY minute;

-- 2) Resumen diario
SELECT
  date_trunc('day', time) AS day,
  SUM(impression_count)::int AS impressions,
  SUM(click_count)::int       AS clicks,
  SUM(conversion_count)::int  AS conversions,
  SUM(revenue)               AS total_revenue
FROM ad_metrics
WHERE time > NOW() - INTERVAL '7 days'
GROUP BY day
ORDER BY day;

-- 3) Performance por keyword (último día)
SELECT
  search_keyword,
  SUM(impression_count) AS impressions,
  SUM(click_count)       AS clicks,
  CASE WHEN SUM(impression_count)>0
    THEN SUM(click_count)::float/SUM(impression_count)
    END AS ctr
FROM ad_metrics
WHERE time > NOW() - INTERVAL '1 day'
GROUP BY search_keyword
ORDER BY ctr DESC
LIMIT 10;

-- 4) Performance geográfica (por estado)
SELECT
  state,
  SUM(impression_count) AS impressions,
  SUM(click_count)       AS clicks,
  SUM(conversion_count)  AS conversions
FROM ad_metrics
WHERE time > NOW() - INTERVAL '7 days'
GROUP BY state
ORDER BY impressions DESC;

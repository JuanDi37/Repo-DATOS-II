import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
import os
import psycopg2
import ipaddress

# Conexión TSDB (TimescaleDB)
conn = psycopg2.connect(
    host=os.getenv('TSDB_HOST'),
    port=os.getenv('TSDB_PORT'),
    dbname=os.getenv('TSDB_DB'),
    user=os.getenv('TSDB_USER'),
    password=os.getenv('TSDB_PASSWORD')
)
conn.autocommit = True
cur = conn.cursor()

class Aggregator:
    def __init__(self, interval=60):
        self.interval = interval
        self.lock = threading.Lock()
        # clave = (bucket_time, state, ip_range, campaign, ad, keyword)
        self.data = defaultdict(lambda: {'impr':0, 'click':0, 'conv':0, 'rev':0.0})
        threading.Thread(target=self._flusher, daemon=True).start()

    def _bucket(self):
        now = datetime.utcnow()
        # bucket al minuto exacto
        return now.replace(second=0, microsecond=0)

    def add(self, event_type, state, ip_range, campaign, ad, keyword, value=0.0):
        key = (self._bucket(), state, ip_range, campaign, ad, keyword)
        with self.lock:
            if event_type == 'impression':
                self.data[key]['impr'] += 1
            elif event_type == 'click':
                self.data[key]['click'] += 1
            elif event_type == 'conversion':
                self.data[key]['conv'] += 1
                self.data[key]['rev'] += value

    def _flusher(self):
        while True:
            time.sleep(self.interval)
            cutoff = self._bucket() - timedelta(seconds=self.interval)
            to_flush = {}
            with self.lock:
                for k, v in list(self.data.items()):
                    if k[0] <= cutoff:
                        to_flush[k] = v
                        del self.data[k]
            for (ts, state, ip_range, camp, ad, kw), counts in to_flush.items():
                impr = counts['impr']
                clk  = counts['click']
                conv = counts['conv']
                rev  = counts['rev']
                ctr  = clk / impr if impr else 0.0
                cr   = conv / clk if clk else 0.0
                # Inserta en TSDB incluyendo ip_range
                cur.execute(
                    """
                    INSERT INTO ad_metrics
                      (time, state, ip_range, campaign_id, ad_id, search_keyword,
                       impression_count, click_count, conversion_count, revenue, ctr, conversion_rate)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (ts, state, ip_range, camp, ad, kw,
                     impr, clk, conv, rev, ctr, cr)
                )

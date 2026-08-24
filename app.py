from __future__ import annotations

import logging
import os
import threading

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
from flask import Flask, jsonify, render_template_string

from engine import monitor

app = Flask(__name__)

HTML = """<!doctype html>
<html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Simple Logic</title><style>
body{font-family:Inter,system-ui,sans-serif;background:#0b1020;color:#e8edf7;margin:0}.wrap{max-width:980px;margin:0 auto;padding:32px 20px}.hero{display:flex;justify-content:space-between;gap:20px;align-items:end}.muted{color:#9eabc4}.card{background:#141c31;border:1px solid #293655;border-radius:16px;padding:20px;margin-top:18px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px}.metric{font-size:28px;font-weight:700}.label{color:#9eabc4;font-size:13px;text-transform:uppercase;letter-spacing:.08em}.pill{display:inline-block;border-radius:999px;padding:6px 10px;background:#203a63;color:#bfe0ff}.json{white-space:pre-wrap;word-break:break-word;font-family:ui-monospace,monospace;color:#c9d8f5}.ok{color:#7ee2a8}</style></head>
<body><main class='wrap'><div class='hero'><div><h1>Simple Logic</h1><p class='muted'>NSE F&O option scalp monitor</p></div><span class='pill'>LTIM excluded</span></div>
<div class='card grid'><div><div class='label'>Status</div><div id='status' class='metric'>Loading</div></div><div><div class='label'>Universe</div><div id='symbols' class='metric'>-</div></div><div><div class='label'>Live rows</div><div id='live_rows' class='metric'>-</div></div><div><div class='label'>Provider</div><div id='provider' class='metric' style='font-size:18px'>-</div></div><div><div class='label'>Trade date</div><div id='date' class='metric' style='font-size:18px'>-</div></div></div>
<div class='card'><h2>Latest signal</h2><div id='candidate' class='json'>No qualifying candidate yet.</div></div>
<div class='card'><h2>Open position</h2><div id='position' class='json'>No open position.</div></div>
<div class='card'><p class='muted'>Live universe: 207 workbook stocks minus LTIM. Day-start report: 09:15 IST. EOD report: 15:40 IST. Rules: 09:30–11:30 IST, VWAP/day high or low confirmation, OI change below -4%, spread below 1.5, volume above 1.5× average, and alerts for every qualifying stock. Duplicate unchanged setups are suppressed while active. This tool generates alerts only and does not place orders.</p><p class='muted'>Last cycle: <span id='cycle'>-</span></p></div>
<script>async function refresh(){try{const d=await fetch('/api/status').then(r=>r.json());document.getElementById('status').textContent=d.status;document.getElementById('symbols').textContent=d.symbols;document.getElementById('provider').textContent=d.provider;document.getElementById('live_rows').textContent=d.live_rows||0;document.getElementById('date').textContent=d.trade_date||'-';document.getElementById('candidate').textContent=d.candidate?JSON.stringify(d.candidate,null,2):'No qualifying candidate yet.';document.getElementById('position').textContent=d.position?JSON.stringify(d.position,null,2):'No open position.';document.getElementById('cycle').textContent=d.last_cycle||'-'}catch(e){document.getElementById('status').textContent='offline'}}refresh();setInterval(refresh,15000)</script></main></body></html>"""


@app.get('/')
def home():
    return render_template_string(HTML)


@app.get('/health')
def health():
    return jsonify({'status': 'ok', 'service': 'simple-logic', 'monitor': monitor.status()['status']}), 200


@app.get('/api/status')
def status():
    return jsonify(monitor.status())


if __name__ == '__main__':
    threading.Thread(target=monitor.run, daemon=True, name='simple-logic-monitor').start()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '10000')))

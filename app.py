"""Free Render web wrapper for the NSE signal engine.

The /health endpoint is intended for UptimeRobot. The signal loop runs in a
background thread while Flask serves the health check on Render's PORT.
"""
import os
import threading
from flask import Flask, jsonify
import engine

app = Flask(__name__)

@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "nse-scalper-engine"}), 200

def run_engine():
    try:
        engine.main()
    except Exception:
        engine.logger.exception("Signal engine stopped")

if __name__ == "__main__":
    threading.Thread(target=run_engine, daemon=True, name="signal-engine").start()
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

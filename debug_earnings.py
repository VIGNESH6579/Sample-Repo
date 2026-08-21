import requests
import sys

sys.path.insert(0, "/home/ubuntu/nse_scalper")
from fetch_earnings import fetch_one, FO_LIQUID

sess = requests.Session()
for s in FO_LIQUID[:8]:
    sym, qe = fetch_one(s, sess)
    print(sym, "->", qe)

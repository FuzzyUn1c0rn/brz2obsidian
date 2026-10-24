"""Serve the synthetic GUI prototype locally; no vault access or persistence."""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import webbrowser

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--port", type=int, default=8766)
parser.add_argument("--no-open", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parent
url = f"http://127.0.0.1:{args.port}/?variant=A"
handler = partial(SimpleHTTPRequestHandler, directory=str(root))
with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
    print(f"GUI prototype: {url}", flush=True)
    print("Synthetic data only. Ctrl+C stops the server.", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

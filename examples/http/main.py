import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json

parser = argparse.ArgumentParser()
parser.add_argument('--host', required=True)
parser.add_argument('--port', required=True, type=int)
args = parser.parse_args()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = json.dumps({'ok': True, 'service': 'device-cli-demo'}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

print(f'Listening on {args.host}:{args.port}', flush=True)
HTTPServer((args.host, args.port), Handler).serve_forever()

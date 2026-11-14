"""Local test server for the phone app with the same cross-origin isolation headers the Android app sends."""
import http.server, sys, functools
class H(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".mjs": "text/javascript", ".wasm": "application/wasm"}
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        super().end_headers()
    def log_message(self, *a): pass
port = int(sys.argv[1]) if len(sys.argv) > 1 else 8088
http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(H, directory=sys.argv[2] if len(sys.argv) > 2 else "www")).serve_forever()

"""Attrappe des KI-Gateways für die Oberflächentests: beantwortet /v1/messages mit einem festen Rezept
im Schema der App und /key/info mit einem Budget. Ruft keine echte KI auf."""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8767

ANSWER = {
    "found": True,
    "title": "Linsensuppe",
    "servings": 4,
    "duration_min": 45,
    "size": "klein",
    "steps": ["Zwiebel würfeln und andünsten", "Linsen und Brühe dazu, 20 Minuten kochen"],
    "tags": ["vegetarisch"],
    "ingredients": [
        {"line": "250 g rote Linsen", "amount": 250, "unit": "g", "name": "Rote Linsen", "note": None},
        {"line": "1 Zwiebel", "amount": 1, "unit": "Stück", "name": "Zwiebel", "note": None},
        {"line": "Salz und Pfeffer", "amount": None, "unit": None, "name": "Salz", "note": None},
        {"line": "Salz und Pfeffer", "amount": None, "unit": None, "name": "Pfeffer", "note": None},
    ],
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/key/info"):
            return self._json({"info": {"spend": 0.42, "max_budget": 5}})
        if self.path == "/health":
            return self._json({"ok": True})
        self._json({"error": "unbekannt"}, 404)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("content-length", 0)))
        if not self.path.startswith("/v1/messages"):
            return self._json({"error": "unbekannt"}, 404)
        content = json.loads(raw or b"{}").get("messages", [{}])[0].get("content", [])
        has_image = any(isinstance(c, dict) and c.get("type") == "image" for c in content)
        # Bei Fotos: Gerichtsbild oben links auf dem ersten Foto, wie auf tests/kochbuchseite.jpg
        dish = {"image": 1, "left": 100, "top": 50, "right": 600, "bottom": 350, "rotation": 0} if has_image else None
        answer = {**ANSWER, "dish_photo": dish}
        self._json(
            {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "rezept-extraktion",
                "content": [{"type": "text", "text": json.dumps(answer, ensure_ascii=False)}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 900, "output_tokens": 400},
            }
        )


ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

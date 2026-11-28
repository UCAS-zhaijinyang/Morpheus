"""Serve the enterprise document corpus and read-only scenario views over loopback."""
from __future__ import annotations

import argparse
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from enterprise_retrieval import KnowledgeBase, validate_change, validate_result

_RETRIEVE_PATH = "/retrieve"
_MAX_REQUEST_BYTES = 64 * 1024
_MAX_RESPONSE_BYTES = 1024 * 1024


def _validate_request(request: Any) -> None:
    if not isinstance(request, dict) or set(request) not in (
            {"card_id", "query"}, {"card_id", "query", "changed"},
            {"card_id", "query", "changed", "mechanism"}):
        raise ValueError("expected card_id, query and optional change with a retrieval mechanism")
    card_id, query = request["card_id"], request["query"]
    if not isinstance(card_id, str) or not 1 <= len(card_id) <= 128:
        raise ValueError("invalid card_id")
    if not isinstance(query, str) or len(query) > 16_384:
        raise ValueError("invalid query")
    mechanism = request.get("mechanism")
    if "mechanism" in request and (not isinstance(mechanism, str) or not request["changed"]):
        raise ValueError("expected a retrieval mechanism and changed work-card fact")
    validate_change(request.get("changed"), mechanism)


class _Handler(BaseHTTPRequestHandler):
    timeout = 10

    def log_message(self, *_args: Any) -> None:
        pass

    def do_POST(self) -> None:
        if self.path != _RETRIEVE_PATH:
            self.send_error(404)
            return
        if self.headers.get_content_type() != "application/json":
            self.send_error(415)
            return
        try:
            size = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            size = -1
        if not 0 <= size <= _MAX_REQUEST_BYTES:
            self.send_error(413)
            return
        try:
            request = json.loads(self.rfile.read(size))
            _validate_request(request)
            documents = self.server.knowledge_base.retrieve(
                request["card_id"], request["query"], request.get("changed"), request.get("mechanism")
            )
            payload = json.dumps({"documents": documents}, ensure_ascii=False).encode("utf-8")
        except (ValueError, RecursionError):
            self.send_error(400, "Invalid retrieval request")
            return
        if len(payload) > _MAX_RESPONSE_BYTES:
            self.send_error(500, "Retrieval result exceeds response limit")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class RagServer(ThreadingHTTPServer):
    def __init__(self, knowledge_base: KnowledgeBase, port: int):
        if not 0 <= port <= 65535:
            raise ValueError("port must be between 0 and 65535")
        self.knowledge_base = knowledge_base
        super().__init__(("127.0.0.1", port), _Handler)


class LocalRagClient:
    """Query a single local service. Every call owns its HTTP connection."""

    def __init__(self, base_url: str):
        url = urlsplit(base_url)
        if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"}
                or url.username is not None or url.password is not None
                or url.path not in {"", "/"} or url.query or url.fragment):
            raise ValueError("RAG URL must be a loopback HTTP origin")
        self.host = "127.0.0.1" if url.hostname == "localhost" else url.hostname
        self.port = url.port if url.port is not None else 80

    def retrieve(self, card_id: str, query: str, changed: dict | None = None,
                 mechanism: str | None = None) -> list[dict]:
        request = {"card_id": card_id, "query": query}
        if changed is not None:
            request["changed"] = changed
        if mechanism is not None:
            request["mechanism"] = mechanism
        _validate_request(request)
        body = json.dumps(request, ensure_ascii=False).encode("utf-8")
        if len(body) > _MAX_REQUEST_BYTES:
            raise ValueError("RAG request exceeds size limit")
        connection = HTTPConnection(self.host, self.port, timeout=10)
        try:
            connection.request("POST", _RETRIEVE_PATH, body, {"Content-Type": "application/json"})
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError(f"RAG service returned HTTP {response.status}")
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
        except (OSError, HTTPException) as error:
            raise ValueError("RAG service unavailable or incomplete response") from error
        finally:
            connection.close()
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise ValueError("RAG result exceeds size limit")
        try:
            payload = json.loads(raw)
        except (ValueError, RecursionError) as error:
            raise ValueError("RAG service returned invalid JSON") from error
        if not isinstance(payload, dict) or set(payload) != {"documents"}:
            raise ValueError("RAG response must contain documents")
        documents = payload["documents"]
        if not isinstance(documents, list) or len(documents) > 3:
            raise ValueError("RAG response must contain at most three document rows")
        document_ids = set()
        for row in documents:
            validate_result(row, card_id)
            if row["document_id"] in document_ids:
                raise ValueError("RAG service returned duplicate document IDs")
            document_ids.add(row["document_id"])
        return documents


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve Morpheus enterprise documents over loopback.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--corpus", type=Path)
    args = parser.parse_args(argv)
    try:
        with RagServer(KnowledgeBase.from_file(args.corpus), args.port) as server:
            print(f"http://127.0.0.1:{server.server_port}", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError) as error:
        parser.exit(1, f"RAG service failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

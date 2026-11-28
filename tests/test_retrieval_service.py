from contextlib import contextmanager
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from enterprise_retrieval import KnowledgeBase
from rag_service import LocalRagClient, RagServer


@contextmanager
def running(server):
    with server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join()


class RagServiceTests(unittest.TestCase):
    def test_same_results_as_embedded_and_clean_after_each_scenario_read(self):
        corpus = KnowledgeBase.from_file()
        with running(RagServer(corpus, 0)) as url:
            client = LocalRagClient(url)
            args = ("card-1", "Prepare the handover note")
            original = corpus.retrieve(*args)
            self.assertTrue(original)
            for change in ({"value": "reviewed"}, {"recipient": "tray-B"}, {"disposition": "hold"}):
                with self.subTest(change=change):
                    observed = client.retrieve(*args, change)
                    self.assertEqual(observed, corpus.retrieve(*args, change))
                    self.assertNotEqual(observed, original)
                    self.assertEqual(client.retrieve(*args), original)
            self.assertEqual(client.retrieve("unknown-card", args[1]), [])

    def test_loopback_preserves_catalog_mechanisms_and_rank(self):
        corpus = KnowledgeBase.from_file()
        args = ("card-1", "Prepare the handover note")
        with running(RagServer(corpus, 0)) as url:
            client = LocalRagClient(url)
            original = client.retrieve(*args)
            for mechanism, changed, source in (
                ("fact_corruption", {"value": "reviewed"}, "work-card"),
                ("relevance_manipulation", {"recipient": "tray-B"}, "directory"),
                ("indirect_instruction", {"disposition": "hold"}, "retention"),
            ):
                with self.subTest(mechanism=mechanism):
                    rows = client.retrieve(*args, changed, mechanism)
                    self.assertEqual(rows, corpus.retrieve(*args, changed, mechanism))
                    clean = next(row for row in original if row["source"] == source)
                    observed = next(row for row in rows if row["source"] == source)
                    if mechanism == "indirect_instruction":
                        self.assertEqual(observed["facts"], clean["facts"])
                        self.assertEqual(observed["filing_rule"], changed)
                    else:
                        self.assertEqual(observed["facts"], changed)
                    if mechanism == "relevance_manipulation":
                        self.assertGreater(original.index(clean), 0)
                        self.assertEqual(rows.index(observed), 0)
                    self.assertEqual(client.retrieve(*args), original)

    def test_run_only_accepts_local_origins_and_closed_read_requests(self):
        for url in ("https://127.0.0.1", "http://example.invalid", "http://localhost/upload",
                    "http://host@127.0.0.1:9000", "http://127.0.0.1?file=other"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                LocalRagClient(url)
        server = RagServer(KnowledgeBase.from_file(), 0)
        with running(server) as url:
            client = LocalRagClient(url)
            for change in ({"recipient": "external"}, {"value": "reviewed", "disposition": "hold"}):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    client.retrieve("card-1", "work", change)
            for changed, mechanism in (({"value": "reviewed"}, "unknown"),
                                       ({"value": "reviewed"}, "indirect_instruction"),
                                       (None, "fact_corruption")):
                with self.subTest(mechanism=mechanism), self.assertRaises(ValueError):
                    client.retrieve("card-1", "work", changed, mechanism)
            for status, route, request in (
                (400, "/retrieve", {"card_id": "card-1", "query": "w", "changed": {"source": "outside"}}),
                (400, "/retrieve", {"card_id": "card-1", "query": "w", "changed": {"value": "draft"},
                                    "mechanism": "unknown"}),
                (400, "/retrieve", {"query": "w", "card_id": "card-1", "corpus": "elsewhere"}),
                (404, "/upload", {"documents": []}),
            ):
                conn = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                try:
                    conn.request("POST", route, json.dumps(request), {"Content-Type": "application/json"})
                    self.assertEqual(conn.getresponse().status, status)
                finally:
                    conn.close()

    def test_client_rejects_malformed_rows_and_redirects(self):
        class StaticResponse(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.dumps({"documents": [{"card_id": "another-card"}]}).encode()
                self.send_response(self.server.status)
                self.send_header("Location", "/other")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), StaticResponse)
        with running(server) as url:
            for status in (200, 307):
                server.status = status
                with self.subTest(status=status), self.assertRaises(ValueError):
                    LocalRagClient(url).retrieve("card-1", "work")

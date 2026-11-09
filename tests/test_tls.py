import hashlib
import json
import select
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import requests

from ifixit_client import IFixitAPIClient


@unittest.skipUnless(shutil.which("openssl"), "TLS integration tests require OpenSSL")
class TLSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.root = Path(cls.directory.name)

        def openssl(*args):
            subprocess.run(
                ["openssl", *args], cwd=cls.root, check=True, capture_output=True
            )

        for name in ["ca", "other-ca"]:
            openssl(
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-keyout",
                name + ".key",
                "-out",
                name + ".pem",
                "-subj",
                "/CN=" + name,
                "-addext",
                "basicConstraints=critical,CA:TRUE",
                "-addext",
                "keyUsage=critical,keyCertSign,cRLSign",
            )
        openssl(
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            "server.key",
            "-out",
            "server.csr",
            "-subj",
            "/CN=localhost",
        )
        (cls.root / "extensions.txt").write_text(
            "subjectAltName=DNS:localhost\nbasicConstraints=critical,CA:FALSE\n"
            "keyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n"
            "authorityKeyIdentifier=keyid,issuer\nsubjectKeyIdentifier=hash\n"
        )
        openssl(
            "x509",
            "-req",
            "-in",
            "server.csr",
            "-CA",
            "ca.pem",
            "-CAkey",
            "ca.key",
            "-CAcreateserial",
            "-out",
            "server.pem",
            "-days",
            "1",
            "-extfile",
            "extensions.txt",
        )
        der = ssl.PEM_cert_to_DER_cert((cls.root / "server.pem").read_text())
        cls.fingerprint = hashlib.sha256(der).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    @contextmanager
    def server(self, statuses=(200,), redirect=None):
        received = []

        class QuietServer(ThreadingHTTPServer):
            daemon_threads = False

            def handle_error(self, request, client_address):
                pass

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                length = int(self.headers.get("Content-Length", 0))
                if length:
                    self.rfile.read(length)
                received.append(self.command)
                status = statuses[min(len(received) - 1, len(statuses) - 1)]
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                if redirect is not None:
                    self.send_header("Location", redirect)
                self.end_headers()
                self.wfile.write(json.dumps({"ok": status == 200}).encode())

            do_POST = do_GET

            def log_message(self, *args):
                pass

        server = QuietServer(("127.0.0.1", 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.root / "server.pem", self.root / "server.key")
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield "https://localhost:%d" % server.server_port, received
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def client(self, url, **kwargs):
        kwargs.setdefault("retries", 0)
        client = IFixitAPIClient(**kwargs)
        client.BASE_URL = url
        self.addCleanup(client.session.close)
        return client

    def test_private_ca_is_untrusted_by_default(self):
        with self.server() as (url, received):
            with self.assertRaises(requests.exceptions.SSLError):
                self.client(url)._request("GET", "/test")
            self.assertEqual(received, [])

    def test_custom_ca_works_with_environment_proxy_ignored(self):
        with (
            self.server() as (url, received),
            patch.dict(
                "os.environ",
                {
                    "HTTPS_PROXY": "http://127.0.0.1:9",
                    "NO_PROXY": "",
                    "no_proxy": "",
                },
            ),
        ):
            result = self.client(url, ca_bundle=self.root / "ca.pem")._request(
                "GET", "/test"
            )
            self.assertEqual(result, {"ok": True})
            self.assertEqual(received, ["GET"])

    def test_matching_pin_and_ca_succeed(self):
        colon_pin = ":".join(
            self.fingerprint[index : index + 2].upper() for index in range(0, 64, 2)
        )
        with self.server() as (url, received):
            result = self.client(
                url, ca_bundle=self.root / "ca.pem", certificate_fingerprint=colon_pin
            )._request("GET", "/test")
            self.assertEqual(result, {"ok": True})
            self.assertEqual(received, ["GET"])

    def test_wrong_pin_fails_before_an_http_request(self):
        wrong = ("0" if self.fingerprint[0] != "0" else "1") + self.fingerprint[1:]
        with self.server() as (url, received):
            with self.assertRaises(requests.exceptions.SSLError):
                self.client(
                    url, ca_bundle=self.root / "ca.pem", certificate_fingerprint=wrong
                )._request("GET", "/test")
            self.assertEqual(received, [])

    def test_matching_pin_does_not_override_ca_validation(self):
        with self.server() as (url, received):
            with self.assertRaises(requests.exceptions.SSLError):
                self.client(
                    url,
                    ca_bundle=self.root / "other-ca.pem",
                    certificate_fingerprint=self.fingerprint,
                )._request("GET", "/test")
            self.assertEqual(received, [])

    def test_matching_pin_does_not_override_hostname_validation(self):
        with self.server() as (url, received):
            with self.assertRaises(requests.exceptions.SSLError):
                self.client(
                    url.replace("localhost", "127.0.0.1"),
                    ca_bundle=self.root / "ca.pem",
                    certificate_fingerprint=self.fingerprint,
                )._request("GET", "/test")
            self.assertEqual(received, [])

    def test_pin_rejects_redirect_to_http(self):
        with self.server(statuses=(302,), redirect="http://127.0.0.1:9/no-tls") as (
            url,
            received,
        ):
            with self.assertRaises(requests.exceptions.SSLError):
                self.client(
                    url,
                    ca_bundle=self.root / "ca.pem",
                    certificate_fingerprint=self.fingerprint,
                )._request("GET", "/test")
            self.assertEqual(received, ["GET"])

    def test_read_request_retries_without_a_proxy(self):
        with self.server(statuses=(503, 200)) as (url, received):
            result = self.client(
                url, ca_bundle=self.root / "ca.pem", retries=1
            )._request("GET", "/test")
            self.assertEqual(result, {"ok": True})
            self.assertEqual(received, ["GET", "GET"])

    def test_post_is_not_automatically_repeated(self):
        with self.server(statuses=(503, 200)) as (url, received):
            with self.assertRaises(requests.exceptions.HTTPError):
                self.client(url, ca_bundle=self.root / "ca.pem", retries=1)._request(
                    "POST", "/test", json={}
                )
            self.assertEqual(received, ["POST"])

    def test_pin_and_custom_ca_work_through_an_opt_in_proxy(self):
        class TunnelHandler(BaseHTTPRequestHandler):
            def do_CONNECT(self):
                host, port = self.path.rsplit(":", 1)
                with socket.create_connection((host, int(port)), timeout=2) as upstream:
                    self.send_response(200)
                    self.end_headers()
                    while True:
                        readable, _, _ = select.select(
                            [self.connection, upstream], [], [], 2
                        )
                        if not readable:
                            return
                        for source in readable:
                            data = source.recv(65536)
                            if not data:
                                return
                            destination = (
                                upstream
                                if source is self.connection
                                else self.connection
                            )
                            destination.sendall(data)

            def log_message(self, *args):
                pass

        proxy = ThreadingHTTPServer(("127.0.0.1", 0), TunnelHandler)
        proxy.daemon_threads = False
        thread = threading.Thread(target=proxy.serve_forever)
        thread.start()
        proxy_url = "http://127.0.0.1:%d" % proxy.server_port
        try:
            with (
                self.server() as (url, received),
                patch.dict(
                    "os.environ",
                    {
                        "HTTPS_PROXY": proxy_url,
                        "https_proxy": proxy_url,
                        "NO_PROXY": "",
                        "no_proxy": "",
                    },
                ),
            ):
                result = self.client(
                    url,
                    proxy=True,
                    ca_bundle=self.root / "ca.pem",
                    certificate_fingerprint=self.fingerprint,
                )._request("GET", "/test")
                self.assertEqual(result, {"ok": True})
                self.assertEqual(received, ["GET"])
        finally:
            proxy.shutdown()
            proxy.server_close()
            thread.join(timeout=2)

# -*- coding: utf-8 -*-
import http.server
import socketserver
import os
import sys
import re

PORT = 8080
DIRECTORY = r"D:\SIH 2026\ML"

class RangeHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def do_GET(self):
        range_header = self.headers.get('Range')
        if not range_header:
            return super().do_GET()
        
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            return super().do_GET()

        try:
            file_size = os.path.getsize(path)
            range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
            if not range_match:
                return super().do_GET()

            start = int(range_match.group(1))
            end_str = range_match.group(2)
            end = int(end_str) if end_str else file_size - 1

            if start >= file_size or start > end:
                self.send_error(416, "Requested Range Not Satisfiable")
                return

            end = min(end, file_size - 1)
            content_length = end - start + 1

            self.send_response(206, "Partial Content")
            content_type = self.guess_type(path)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
            self.send_header('Content-Length', str(content_length))
            self.end_headers()

            with open(path, 'rb') as f:
                f.seek(start)
                bytes_to_send = content_length
                chunk_size = 64 * 1024
                while bytes_to_send > 0:
                    read_len = min(chunk_size, bytes_to_send)
                    data = f.read(read_len)
                    if not data:
                        break
                    self.wfile.write(data)
                    bytes_to_send -= len(data)
        except (ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:
            print("Error in do_GET:", e)
            pass

    def end_headers(self):
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

if __name__ == '__main__':
    with ThreadedHTTPServer(("0.0.0.0", PORT), RangeHTTPRequestHandler) as httpd:
        print(f"Serving multithreaded HTTP with Range support on 0.0.0.0 port {PORT} (http://localhost:{PORT}/)...", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass

"""Gumroad OAuth 一次性回调服务器

捕获授权码 → 换取 access token → 写入 config。
"""

import json
import urllib.parse
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

CLIENT_ID = "uZJYClSltx6QagqrAiEm_6msEAHau3LIT67ZQ_puaOA"
CLIENT_SECRET = "IviJgrdToR3yU_tvQPxNjUf1rdcFW4hazERaaC1gW6Y"
REDIRECT_URI = "http://localhost:8085/callback"
PORT = 8085

AUTH_URL = (
    f"https://gumroad.com/oauth/authorize"
    f"?client_id={CLIENT_ID}"
    f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
    f"&scope=view_sales"
)


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/callback":
            qs = urllib.parse.parse_qs(parsed.query)
            code = qs.get("code", [None])[0]

            if code:
                # 用 code 换 access token
                token = self._exchange_code(code)
                if token:
                    msg = "Token saved! Close this window."
                    print(f"\nACCESS_TOKEN={token}")
                else:
                    msg = "Token exchange failed"
            else:
                msg = f"No code received. Query: {parsed.query}"

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<html><body><h2>{msg}</h2></body></html>".encode())
            return

        # Default: redirect to auth
        self.send_response(302)
        self.send_header("Location", AUTH_URL)
        self.end_headers()

    def _exchange_code(self, code: str):
        try:
            data = urllib.parse.urlencode({
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": code,
                "redirect_uri": REDIRECT_URI,
            }).encode()

            req = urllib.request.Request(
                "https://api.gumroad.com/oauth/token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
                token = result.get("access_token", "")
                if token:
                    # 保存到 shell 可直接 source 的文件
                    with open("/tmp/gumroad_token.sh", "w") as f:
                        f.write(f'export GUMROAD_ACCESS_TOKEN="{token}"\n')
                    print(f"Token saved to /tmp/gumroad_token.sh")
                    print(f"Run: source /tmp/gumroad_token.sh")
                return token or None
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else str(e)
            print(f"Token exchange failed: HTTP {e.code} — {body}")
            return None
        except Exception as e:
            print(f"Token exchange error: {e}")
            return None

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print("  Gumroad OAuth Server")
    print(f"  Opening browser with auth URL...")
    print(f"{'='*60}\n")

    import webbrowser
    webbrowser.open(AUTH_URL)
    print(f"  If browser doesn't open, visit:\n  {AUTH_URL}\n")
    print(f"  Waiting for authorization on port {PORT}...\n")

    server = HTTPServer(("localhost", PORT), CallbackHandler)
    try:
        server.handle_request()  # 只处理一次请求
    except KeyboardInterrupt:
        pass
    server.server_close()

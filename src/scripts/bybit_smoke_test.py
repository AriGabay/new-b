"""
bybit_smoke_test.py — Bybit V5 API connectivity diagnostic

Tests each layer of the Bybit connection stack independently:
  Layer 1: DNS resolution for api.bybit.com
  Layer 2: TCP connectivity to api.bybit.com:443
  Layer 3: TLS handshake (is the cert for bybit.com, or a proxy?)
  Layer 4: HTTP request to /v5/market/kline
  Layer 5: Response parsing (retCode, result.list)
  Layer 6: BybitAdapter integration test (uses the actual adapter class)

Usage:
  cd /Users/arigabay/Code/new-b/src
  python scripts/bybit_smoke_test.py

Expected output in clean environment:
  [PASS] Layer 1: DNS resolved api.bybit.com -> <real_ip>
  [PASS] Layer 2: TCP connected to api.bybit.com:443
  [PASS] Layer 3: TLS certificate CN=*.bybit.com (not proxied)
  [PASS] Layer 4: HTTP 200 from /v5/market/kline
  [PASS] Layer 5: Parsed 3 BTCUSDT bars
  [PASS] Layer 6: BybitAdapter returned 3 OHLCVBar objects

Exit codes:
  0 = all layers pass
  1 = at least one layer failed (environment blocked)
  2 = code defect (unexpected exception type)

Environment failure signatures:
  - Layer 1 resolves to 127.0.0.1 → local proxy is intercepting
  - Layer 3 cert CN != *.bybit.com → man-in-the-middle (proxy SSL inspection)
  - Layer 4 returns 404 → wrong path or proxy does not recognise the path
  - Layer 4 returns 403 → geo-block or IP restriction
  - Connection refused → no local proxy and no internet
"""
from __future__ import annotations

import asyncio
import json
import socket
import ssl
import sys
import traceback
from pathlib import Path

# Make src/ importable when running as script
sys.path.insert(0, str(Path(__file__).parent.parent))

BYBIT_HOST = "api.bybit.com"
BYBIT_PORT = 443
KLINES_PATH = "/v5/market/kline"
TEST_SYMBOL = "BTCUSDT"
TEST_INTERVAL = "60"
TEST_LIMIT = 3


def check_layer_1_dns() -> tuple[bool, str]:
    """DNS resolution."""
    try:
        ip = socket.gethostbyname(BYBIT_HOST)
        if ip == "127.0.0.1":
            return False, f"ENVIRONMENT FAILURE: {BYBIT_HOST} resolves to 127.0.0.1 — local proxy is intercepting DNS"
        return True, f"Resolved {BYBIT_HOST} -> {ip}"
    except socket.gaierror as e:
        return False, f"DNS resolution failed: {e}"


def check_layer_2_tcp() -> tuple[bool, str]:
    """TCP connectivity."""
    try:
        sock = socket.create_connection((BYBIT_HOST, BYBIT_PORT), timeout=10)
        sock.close()
        return True, f"TCP connected to {BYBIT_HOST}:{BYBIT_PORT}"
    except OSError as e:
        return False, f"TCP connection failed: {e}"


def check_layer_3_tls() -> tuple[bool, str]:
    """TLS certificate check."""
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(
            socket.create_connection((BYBIT_HOST, BYBIT_PORT), timeout=10),
            server_hostname=BYBIT_HOST,
        ) as ssock:
            cert = ssock.getpeercert()
            subject = dict(x[0] for x in cert.get("subject", ()))
            cn = subject.get("commonName", "unknown")
            issuer = dict(x[0] for x in cert.get("issuer", ()))
            issuer_o = issuer.get("organizationName", "unknown")

            if "bybit" not in cn.lower():
                return False, (
                    f"ENVIRONMENT FAILURE: Certificate CN={cn!r} is not bybit.com. "
                    f"Issuer: {issuer_o}. A local proxy is performing SSL inspection."
                )
            return True, f"TLS certificate CN={cn}, issuer={issuer_o}"
    except ssl.SSLError as e:
        return False, f"TLS handshake failed: {e}"
    except OSError as e:
        return False, f"Connection failed: {e}"


def check_layer_4_http() -> tuple[bool, str, bytes]:
    """HTTP request."""
    try:
        import http.client
        conn = http.client.HTTPSConnection(BYBIT_HOST, timeout=15)
        path = (
            f"{KLINES_PATH}?category=linear&symbol={TEST_SYMBOL}"
            f"&interval={TEST_INTERVAL}&limit={TEST_LIMIT}"
        )
        conn.request("GET", path, headers={"User-Agent": "bybit-smoke-test/1.0"})
        resp = conn.getresponse()
        body = resp.read()
        conn.close()

        if resp.status != 200:
            return False, f"HTTP {resp.status} — expected 200", body
        return True, f"HTTP {resp.status} OK ({len(body)} bytes)", body
    except Exception as e:
        return False, f"HTTP request failed: {e}", b""


def check_layer_5_parse(body: bytes) -> tuple[bool, str]:
    """Response parsing."""
    try:
        if not body:
            return False, "Empty response body"
        data = json.loads(body)
        ret_code = data.get("retCode", -1)
        if ret_code != 0:
            return False, f"retCode={ret_code} retMsg={data.get('retMsg', '?')}"
        klines = data.get("result", {}).get("list", [])
        if not klines:
            return False, "result.list is empty"
        return True, f"Parsed {len(klines)} kline rows, first ts={klines[0][0]}"
    except json.JSONDecodeError as e:
        return False, f"JSON parse error: {e} — body snippet: {body[:200]!r}"


async def check_layer_6_adapter() -> tuple[bool, str]:
    """BybitAdapter integration."""
    try:
        from data.bybit import BybitAdapter
        adapter = BybitAdapter()
        await adapter.setup()
        try:
            bars = await adapter.fetch_bars(
                symbol=TEST_SYMBOL, interval=TEST_INTERVAL, limit=TEST_LIMIT
            )
            if not bars:
                return False, "BybitAdapter returned empty list"
            bar = bars[0]
            return True, (
                f"BybitAdapter returned {len(bars)} OHLCVBar(s). "
                f"First: {bar.symbol} {bar.timestamp} close={bar.close}"
            )
        finally:
            await adapter.teardown()
    except Exception as e:
        return False, f"BybitAdapter error: {type(e).__name__}: {e}"


def print_result(layer: str, passed: bool, detail: str) -> None:
    status = "[PASS]" if passed else "[FAIL]"
    print(f"  {status} {layer}: {detail}")


async def main() -> int:
    print(f"Bybit Connectivity Smoke Test")
    print(f"Target: https://{BYBIT_HOST}{KLINES_PATH}")
    print(f"Symbol: {TEST_SYMBOL} | Interval: {TEST_INTERVAL} | Limit: {TEST_LIMIT}")
    print()

    all_passed = True

    # Layer 1
    ok, msg = check_layer_1_dns()
    print_result("Layer 1 DNS", ok, msg)
    all_passed = all_passed and ok

    # Layer 2 — skip if DNS failed
    if ok:
        ok2, msg2 = check_layer_2_tcp()
        print_result("Layer 2 TCP", ok2, msg2)
        all_passed = all_passed and ok2
    else:
        print_result("Layer 2 TCP", False, "SKIPPED — DNS failed")
        all_passed = False
        ok2 = False

    # Layer 3 TLS
    if ok2:
        ok3, msg3 = check_layer_3_tls()
        print_result("Layer 3 TLS", ok3, msg3)
        all_passed = all_passed and ok3
    else:
        print_result("Layer 3 TLS", False, "SKIPPED — TCP failed")
        all_passed = False
        ok3 = False

    # Layer 4 HTTP
    ok4, msg4, body = check_layer_4_http()
    print_result("Layer 4 HTTP", ok4, msg4)
    all_passed = all_passed and ok4

    # Layer 5 Parse (only if HTTP passed)
    if ok4:
        ok5, msg5 = check_layer_5_parse(body)
        print_result("Layer 5 Parse", ok5, msg5)
        all_passed = all_passed and ok5
    else:
        print_result("Layer 5 Parse", False, "SKIPPED — HTTP failed")
        all_passed = False

    # Layer 6 Adapter
    ok6, msg6 = await check_layer_6_adapter()
    print_result("Layer 6 Adapter", ok6, msg6)
    all_passed = all_passed and ok6

    print()
    if all_passed:
        print("RESULT: ALL LAYERS PASS — Bybit REST API is accessible")
        return 0
    else:
        print("RESULT: ONE OR MORE LAYERS FAILED")
        print()
        print("Diagnosis guide:")
        print("  DNS resolves to 127.0.0.1 → VPN or local proxy is intercepting")
        print("  TLS cert CN != *.bybit.com → Proxy is doing SSL inspection")
        print("  HTTP 404 → Proxy does not recognise the path (common with VPNs)")
        print("  HTTP 403 → Geo-block or IP restriction")
        print("  Connection refused → No internet / firewall")
        print()
        print("To run in a clean environment:")
        print("  1. Disable any VPN or proxy")
        print("  2. cd /Users/arigabay/Code/new-b/src && python scripts/bybit_smoke_test.py")
        print("  3. Or use a cloud VM without VPN restrictions")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

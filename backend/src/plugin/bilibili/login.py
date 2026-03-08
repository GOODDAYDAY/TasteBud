"""Bilibili QR code login — scan with mobile app to get cookies.

Flow:
  1. Request a QR code from Bilibili API
  2. Display it in the terminal
  3. Poll until the user scans it
  4. Save the session cookies to disk
"""

from __future__ import annotations

import asyncio
import io
import sys
import time
from pathlib import Path

import httpx

# Fix Windows console encoding for Unicode QR display
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from plugin.bilibili.auth import save_cookie

_GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
}


def _print_qr_ascii(url: str) -> None:
    """Print a QR code to the terminal using ASCII blocks.

    Uses the `qrcode` library if available, otherwise prints the raw URL.
    """
    try:
        import qrcode  # type: ignore[import-untyped]

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)

        # Build ASCII representation using Unicode block characters
        matrix = qr.get_matrix()
        lines: list[str] = []
        for r in range(0, len(matrix) - 1, 2):
            line = ""
            for c in range(len(matrix[r])):
                top = matrix[r][c]
                bot = matrix[r + 1][c] if r + 1 < len(matrix) else False
                if top and bot:
                    line += "\u2588"  # full block
                elif top:
                    line += "\u2580"  # upper half
                elif bot:
                    line += "\u2584"  # lower half
                else:
                    line += " "
            lines.append(line)
        print("\n".join(lines))
    except ImportError:
        print("  (install `qrcode` for terminal QR display: uv add qrcode)")
        print(f"  Open this URL in browser to get QR code:\n  {url}")


async def qr_login(cookie_path: Path | None = None) -> dict[str, str] | None:
    """Interactive QR code login flow.

    Returns the saved cookies on success, or None if cancelled/failed.
    """
    async with httpx.AsyncClient(headers=_HEADERS, timeout=30.0) as client:
        # 1. Generate QR code
        resp = await client.get(_GENERATE_URL)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            print(f"  Failed to generate QR code: {data.get('message')}")
            return None

        qr_url = data["data"]["url"]
        qrcode_key = data["data"]["qrcode_key"]

        # 2. Display QR code
        print("\n  Please scan this QR code with the Bilibili mobile app:\n")
        _print_qr_ascii(qr_url)
        print("\n  Waiting for scan...")

        # 3. Poll for result
        start = time.monotonic()
        timeout = 180  # 3 minutes

        while time.monotonic() - start < timeout:
            await asyncio.sleep(2)

            resp = await client.get(_POLL_URL, params={"qrcode_key": qrcode_key})
            resp.raise_for_status()
            poll_data = resp.json()

            code = poll_data.get("data", {}).get("code", -1)

            if code == 0:
                # Success — extract cookies from response
                print("  Login successful!")
                cookies = _extract_cookies(resp)
                if cookies:
                    saved_path = save_cookie(cookies, cookie_path)
                    print(f"  Cookies saved to: {saved_path}")
                    return cookies
                print("  Warning: login succeeded but no cookies received.")
                return None

            if code == 86038:
                print("  QR code expired. Please try again.")
                return None

            if code == 86090:
                # Scanned, waiting for confirmation
                elapsed = int(time.monotonic() - start)
                sys.stdout.write(f"\r  Scanned! Please confirm on your phone... ({elapsed}s)")
                sys.stdout.flush()
            else:
                # 86101 = not scanned yet
                elapsed = int(time.monotonic() - start)
                sys.stdout.write(f"\r  Waiting for scan... ({elapsed}s)")
                sys.stdout.flush()

        print("\n  Timeout. Please try again.")
        return None


def _extract_cookies(resp: httpx.Response) -> dict[str, str]:
    """Extract cookies from the login response."""
    cookies: dict[str, str] = {}

    # From response JSON (some cookies come in the response body)
    data = resp.json().get("data", {})
    refresh_token = data.get("refresh_token", "")
    if refresh_token:
        cookies["refresh_token"] = refresh_token

    # From Set-Cookie headers
    for cookie in resp.cookies.jar:
        cookies[cookie.name] = cookie.value

    # From the URL parameters (Bilibili sometimes puts tokens in redirect URL)
    url = data.get("url", "")
    if "?" in url:
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        for key in ("DedeUserID", "DedeUserID__ckMd5", "SESSDATA", "bili_jct"):
            if key in params:
                cookies[key] = params[key][0]

    return cookies


def main() -> None:
    """CLI entry point for QR login."""
    print("=== Bilibili QR Code Login ===")
    result = asyncio.run(qr_login())
    if result:
        print(f"\n  Done! Got {len(result)} cookie(s).")
    else:
        print("\n  Login failed or cancelled.")


if __name__ == "__main__":
    main()

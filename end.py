import os
import json
import time
import requests
from flask import Flask, request, jsonify
from danger_ffjwt import guest_to_jwt  # only needed function

app = Flask(__name__)

# Developer credit
DEV_CREDIT = "@EndingGamer"
DEV_TELEGRAM = "t.me/https:TE4M_ENDING_77"

# ---------- Version fetching with simple TTL cache ----------
_versions_cache = {
    "ob_version": "OB52",
    "client_version": "1.120.1",
    "last_fetch": 0
}

def get_versions():
    """Fetch latest OB & client versions from GitHub, cache for 1 hour."""
    global _versions_cache
    now = time.time()
    if now - _versions_cache["last_fetch"] > 3600:
        try:
            resp = requests.get(
                "https://raw.githubusercontent.com/dangerapix/danger-ffjwt/main/versions.json",
                timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                _versions_cache["ob_version"] = data.get("ob_version", "OB52")
                _versions_cache["client_version"] = data.get("client_version", "1.120.1")
                _versions_cache["last_fetch"] = now
        except Exception:
            # Keep existing/default versions on failure
            pass
    return _versions_cache["ob_version"], _versions_cache["client_version"]

# ---------- Helper to add dev credit in response headers ----------
def add_dev_headers(response):
    response.headers["X-Developer"] = DEV_CREDIT
    return response

# ---------- Routes ----------
@app.route('/token', methods=['GET'])
def token_converter():
    """
    Convert Free Fire UID and password to a JWT token.
    Required query parameters: uid, password
    """
    ob_ver, client_ver = get_versions()
    args = request.args

    # Check for required parameters
    if 'uid' not in args or 'password' not in args:
        return add_dev_headers(jsonify({
            "success": False,
            "error": "Missing parameters. Use ?uid=UID&password=PASSWORD",
            "credit": DEV_TELEGRAM
        })), 400

    uid = args.get('uid').strip()
    pwd = args.get('password').strip()

    if not uid or not pwd:
        return add_dev_headers(jsonify({
            "success": False,
            "error": "UID and password cannot be empty",
            "credit": DEV_TELEGRAM
        })), 400

    try:
        result = guest_to_jwt(uid, pwd, ob_version=ob_ver, client_version=client_ver)

        # Ensure result is a dict
        if isinstance(result, dict):
            # Add credit information to the response
            result["credit"] = DEV_TELEGRAM
        else:
            # If result is not a dict (e.g., string), wrap it
            result = {"success": True, "token": result, "credit": DEV_TELEGRAM}

        return add_dev_headers(jsonify(result))

    except Exception as e:
        return add_dev_headers(jsonify({
            "success": False,
            "error": str(e),
            "credit": DEV_TELEGRAM
        })), 500

# ---------- Local test ----------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
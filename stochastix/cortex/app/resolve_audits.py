"""
Runs the daily audit resolution against the API inside this container.

    docker exec dc_cortex python -m cortex.app.resolve_audits

The admin token is read from this container's own ADMIN_SECRET, so it never
appears on the host's command line, in `ps` output or in shell history. The
request goes to loopback, which is the only network the endpoint accepts.
Exit status: 0 on success, 1 on an HTTP or connection error, 2 when
ADMIN_SECRET is missing.
"""
import os
import sys
import urllib.error
import urllib.request

URL = "http://127.0.0.1:8000/api/v1/audit/resolve"


def main() -> int:
    token = os.environ.get("ADMIN_SECRET", "")
    if not token:
        print("ADMIN_SECRET is not set in this container.", file=sys.stderr)
        return 2
    # No proxy handler: the request must never leave the container.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(URL, method="POST", headers={"x-admin-token": token})
    try:
        with opener.open(request, timeout=900) as response:
            print(response.read().decode("utf-8", errors="replace"))
            return 0
    except urllib.error.HTTPError as error:
        print(f"Audit resolve failed: HTTP {error.code}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"Audit resolve failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

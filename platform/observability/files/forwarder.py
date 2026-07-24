"""Alertmanager -> AWS DevOps Agent event-channel forwarder.

Stdlib only, on purpose: no image build, no dependency chain to patch.
Alertmanager POSTs its webhook payload to /alert; we answer 200 after the
event channel accepted the signed incident, or 5xx so Alertmanager's own
retry loop takes over (it retries 429/5xx, never 4xx).
"""
import base64, hashlib, hmac, json, os, sys, urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CREDS_DIR = os.environ.get("CREDS_DIR", "/creds")
ENV_LABEL = os.environ.get("ENV_LABEL", "unknown")
PORT = int(os.environ.get("PORT", "8080"))
MAX_DESCRIPTION = 4000  # keep incident payloads comfortably small

def log(**fields):
    # One JSON object per line on stdout: Alloy ships it to Loki as-is.
    print(json.dumps({"ts": now_iso(), **fields}), flush=True)

def now_iso():
    # Millisecond UTC with a Z suffix, matching the AWS sample's
    # JavaScript toISOString() — the signed timestamp header must be a
    # format the service accepts.
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def read_creds():
    # Re-read per request: ESO refreshes the mounted Secret in place, so
    # a rotated webhook secret is picked up without a restart.
    with open(os.path.join(CREDS_DIR, "url")) as f:
        url = f.read().strip()
    with open(os.path.join(CREDS_DIR, "secret")) as f:
        secret = f.read().strip()
    return url, secret

def build_incident(am):
    """Reshape an Alertmanager webhook batch into a DevOps Agent incident."""
    firing = [a for a in am.get("alerts", []) if a.get("status") == "firing"]
    if not firing:
        return None
    group = am.get("groupLabels", {})
    alertname = group.get("alertname") or "alerts"
    namespace = group.get("namespace") or am.get("commonLabels", {}).get("namespace", "")

    # Deterministic id: same alert episode -> same id, however often
    # Alertmanager re-notifies (repeat_interval), so the event channel can
    # de-duplicate instead of opening a fresh investigation each repeat.
    # A NEW episode of the same alert gets a new id via its startsAt.
    first_start = min(a.get("startsAt", "") for a in firing)
    digest = hashlib.sha256(f"{am.get('groupKey','')}|{first_start}".encode()).hexdigest()
    incident_id = f"alertmanager-{digest[:32]}"

    severities = {a.get("labels", {}).get("severity", "") for a in firing}
    lines = [f"Environment: {ENV_LABEL} (Kubernetes, via Alertmanager)", ""]
    for a in firing:
        ann, lbl = a.get("annotations", {}), a.get("labels", {})
        lines.append("- " + (ann.get("summary") or lbl.get("alertname", "alert")))
        if ann.get("description"):
            lines.append("  " + ann["description"])
        detail = ", ".join(f"{k}={v}" for k, v in sorted(lbl.items()))
        lines.append(f"  labels: {detail}")
        lines.append(f"  firing since: {a.get('startsAt', '?')}")
    description = "\n".join(lines)[:MAX_DESCRIPTION]

    return {
        "eventType": "incident",
        "incidentId": incident_id,
        "action": "created",
        "priority": "HIGH" if "critical" in severities else "MEDIUM",
        "title": f"[{ENV_LABEL}] {alertname}: {len(firing)} alert(s) firing"
                 + (f" in {namespace}" if namespace else ""),
        "description": description,
        "service": namespace or "kubernetes",
        "timestamp": now_iso(),
        "data": {"metadata": {
            "source": "alertmanager",
            "environment": ENV_LABEL,
            "group_key": am.get("groupKey", ""),
            "external_url": am.get("externalURL", ""),
        }},
    }

def sign_and_send(incident):
    url, secret = read_creds()
    body = json.dumps(incident)
    ts = incident["timestamp"]
    sig = base64.b64encode(
        hmac.new(secret.encode(), f"{ts}:{body}".encode(), hashlib.sha256).digest()
    ).decode()
    req = urllib.request.Request(url, data=body.encode(), method="POST", headers={
        "Content-Type": "application/json",
        "x-amzn-event-signature": sig,
        "x-amzn-event-timestamp": ts,
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):  # our log() replaces the default access log
        pass

    def _respond(self, code, msg=""):
        self.send_response(code)
        self.end_headers()
        if msg:
            self.wfile.write(msg.encode())

    def do_GET(self):
        self._respond(200 if self.path == "/healthz" else 404)

    def do_POST(self):
        if self.path != "/alert":
            return self._respond(404)
        try:
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            incident = build_incident(json.loads(raw))
        except Exception as e:
            log(level="warn", event="bad_request", error=str(e))
            return self._respond(400, "unparseable Alertmanager payload")
        if incident is None:
            # resolved-only batch: nothing to investigate (send_resolved
            # is false anyway — this is belt and braces)
            log(level="info", event="skipped_resolved")
            return self._respond(200)
        try:
            status = sign_and_send(incident)
        except Exception as e:
            # 502 -> Alertmanager retries; the deterministic incidentId
            # makes those retries safe.
            log(level="error", event="forward_failed",
                incident_id=incident["incidentId"], error=str(e))
            return self._respond(502, "event channel unreachable")
        log(level="info", event="forwarded", incident_id=incident["incidentId"],
            title=incident["title"], upstream_status=status)
        self._respond(200)

if __name__ == "__main__":
    log(level="info", event="starting", port=PORT, env=ENV_LABEL)
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()

#!/usr/bin/env python3
"""Switch on shared group marks: Firebase setup steps, run one at a time, in this order:
  python3 tools/firebase_setup.py addfirebase  <project-id>      (needs the account's Firebase terms accepted)
  python3 tools/firebase_setup.py webapp       <project-id> data/sync.json
  python3 tools/firebase_setup.py anonymous    <project-id>
  python3 tools/firebase_setup.py rules        <project-id> firestore.rules
  python3 tools/firebase_setup.py restrictkey  <project-id>      (the web key works only from the site and localhost)
Uses the signed-in gcloud account's access token, fetched per run and never printed or stored."""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

step, PID = sys.argv[1], sys.argv[2]
TOKEN = subprocess.run(["/opt/homebrew/bin/gcloud", "auth", "print-access-token"], capture_output=True, text=True, check=True).stdout.strip()


def call(method, url, body=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
                                          "x-goog-user-project": PID})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def wait(op_url):
    for _ in range(60):
        code, op = call("GET", op_url)
        if op.get("done"):
            return op
        time.sleep(3)
    return {"error": "timeout"}


FB = "https://firebase.googleapis.com/v1beta1"
if step == "addfirebase":
    code, op = call("POST", f"{FB}/projects/{PID}:addFirebase", {})
    print("addFirebase:", code, json.dumps(op)[:300])
    if code == 200 and op.get("name"):
        res = wait(f"{FB}/{op['name']}")
        print("done:", json.dumps(res.get("response", res.get("error")))[:300])
elif step == "webapp":
    code, apps = call("GET", f"{FB}/projects/{PID}/webApps")
    app = (apps.get("apps") or [None])[0]
    if not app:
        code, op = call("POST", f"{FB}/projects/{PID}/webApps", {"displayName": "Vietnam Travel Map"})
        print("create web app:", code, json.dumps(op)[:200])
        res = wait(f"{FB}/{op['name']}")
        app = res.get("response")
    code, cfg = call("GET", f"{FB}/projects/{PID}/webApps/{app['appId']}/config")
    keep = {k: cfg[k] for k in ("apiKey", "authDomain", "projectId", "appId", "messagingSenderId", "storageBucket") if k in cfg}
    json.dump({"config": keep}, open(sys.argv[3], "w"), indent=1)
    print("web app", app["appId"], "config written to", sys.argv[3], "keys:", sorted(keep))
elif step == "anonymous":
    url = f"https://identitytoolkit.googleapis.com/admin/v2/projects/{PID}/config?updateMask=signIn.anonymous.enabled"
    code, res = call("PATCH", url, {"signIn": {"anonymous": {"enabled": True}}})
    print("enable anonymous sign-in:", code, json.dumps(res.get("signIn", res.get("error")))[:300])
elif step == "rules":
    src = open(sys.argv[3]).read()
    R = "https://firebaserules.googleapis.com/v1"
    code, rs = call("POST", f"{R}/projects/{PID}/rulesets", {"source": {"files": [{"name": "firestore.rules", "content": src}]}})
    print("ruleset:", code, rs.get("name", rs.get("error")))
    rel = {"name": f"projects/{PID}/releases/cloud.firestore", "rulesetName": rs["name"]}
    code, r = call("POST", f"{R}/projects/{PID}/releases", rel)
    if code == 409:
        code, r = call("PATCH", f"{R}/projects/{PID}/releases/cloud.firestore", {"release": rel})
    print("release cloud.firestore:", code, r.get("rulesetName", r.get("error")))
elif step == "restrictkey":
    code, keys = call("GET", f"https://apikeys.googleapis.com/v2/projects/{PID}/locations/global/keys")
    for k in keys.get("keys", []):
        body = {"restrictions": {**k.get("restrictions", {}), "browserKeyRestrictions": {
            "allowedReferrers": ["https://dthau120391.github.io/*", "http://127.0.0.1/*", "http://localhost/*"]}}}
        code, op = call("PATCH", f"https://apikeys.googleapis.com/v2/{k['name']}?updateMask=restrictions", body)
        print("restrict", k.get("displayName"), "->", code, json.dumps(op.get("error", "ok"))[:200])
elif step == "status":
    code, cfg = call("GET", f"https://identitytoolkit.googleapis.com/admin/v2/projects/{PID}/config")
    print("auth config:", code, json.dumps(cfg.get("signIn", cfg.get("error")))[:300])

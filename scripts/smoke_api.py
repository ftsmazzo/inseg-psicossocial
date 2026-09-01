import json
import subprocess
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8000"

data = urllib.parse.urlencode(
    {"username": "admin@inseg.local", "password": "inseg123"}
).encode()
req = urllib.request.Request(f"{BASE}/api/auth/login", data=data, method="POST")
req.add_header("Content-Type", "application/x-www-form-urlencoded")
token = json.loads(urllib.request.urlopen(req).read())["access_token"]
print("token ok")

req = urllib.request.Request(
    f"{BASE}/api/jobs",
    data=json.dumps({"title": "Amendo Demo 2"}).encode(),
    method="POST",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
)
job = json.loads(urllib.request.urlopen(req).read())
jid = job["id"]
print("job", jid)

r = subprocess.run(
    [
        "curl",
        "-s",
        "-X",
        "POST",
        f"{BASE}/api/jobs/{jid}/upload",
        "-H",
        f"Authorization: Bearer {token}",
        "-F",
        "campanha=@modelos/Campanha-Amendo.pdf",
        "-F",
        "pgr=@modelos/PGR-Amendo.docx",
    ],
    capture_output=True,
    text=True,
    cwd=r"c:\Users\anjo_\OneDrive\Projetos-FabriaIA\psicossocial",
)
print("upload", r.stdout)
if r.returncode != 0:
    print("curl err", r.stderr)
    raise SystemExit(1)

req = urllib.request.Request(
    f"{BASE}/api/jobs/{jid}/process",
    data=b"",
    method="POST",
    headers={"Authorization": f"Bearer {token}"},
)
proc = json.loads(urllib.request.urlopen(req).read())
print("status", proc["status"], "lines", len(proc["lines"]), "empresa", proc.get("empresa"))
for ln in proc["lines"][:4]:
    print("-", ln["ghe_numero"], ln["hazard_id"], ln["potencial"], ln["status"])
    print(" ", ln["agente"][:90])

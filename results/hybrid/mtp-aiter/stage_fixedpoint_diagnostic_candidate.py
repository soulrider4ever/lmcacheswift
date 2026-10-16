"""Stage an isolated CT115 candidate from the stopped Qwen MTP container.

Run inside CT115 only; do not copy inspect JSON to the repository. This
retains all launch settings and changes only the image and container name.
"""
import http.client
import json
import pathlib
import socket
import subprocess

SOURCE = "qwen38-swift-w8a8-lmcache-aiter-mtp3-coordinator-20261015"
NAME = "qwen38-swift-w8a8-lmcache-aiter-mtp3-fixedpoint-diag-20261015"
IMAGE = "local/vllm-mi210:lmcache-aiter-mtp-qwen-fixedpoint-diag-20261015"


class DockerHTTP(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect("/var/run/docker.sock")


def inspect(name):
    return json.loads(subprocess.check_output(["docker", "inspect", name]))[0]


source = inspect(SOURCE)
assert source["State"]["Status"] == "exited"
assert source["HostConfig"]["RestartPolicy"]["Name"] == "no"
assert source["Config"]["Cmd"][source["Config"]["Cmd"].index("--port") + 1] == "8092"
assert json.loads(source["Config"]["Cmd"][source["Config"]["Cmd"].index("--kv-transfer-config") + 1])["kv_connector_extra_config"]["lmcache.mp.port"] == 5556
image_id = subprocess.check_output(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"], text=True).strip()
assert image_id
try:
    existing = inspect(NAME)
except subprocess.CalledProcessError:
    existing = None
if existing is not None:
    assert existing["State"]["Status"] == "exited"
    assert existing["HostConfig"]["RestartPolicy"]["Name"] == "no"
    assert existing["Image"] == image_id
    print("already-staged", NAME)
    raise SystemExit(0)
config = source["Config"].copy()
config["Hostname"] = config["Domainname"] = ""
config["Image"] = IMAGE
host = source["HostConfig"].copy()
host["RestartPolicy"] = {"Name": "no", "MaximumRetryCount": 0}
c = DockerHTTP("localhost")
c.request("POST", "/v1.47/containers/create?name=" + NAME,
          body=json.dumps({**config, "HostConfig": host}),
          headers={"Content-Type": "application/json"})
r = c.getresponse()
body = r.read().decode()
if r.status != 201:
    raise RuntimeError(f"container create failed HTTP {r.status}: {body[:500]}")
candidate = inspect(NAME)
assert candidate["Config"]["Cmd"] == source["Config"]["Cmd"]
assert candidate["HostConfig"]["RestartPolicy"]["Name"] == "no"
assert candidate["Image"] == image_id
p = pathlib.Path("/home/ubuntu/lmcache-integration-20261015/mtp-fixedpoint-diagnostic-staged-inspect.json")
p.write_text(json.dumps(candidate, indent=2))
p.chmod(0o600)
print("staged", NAME, candidate["Image"])

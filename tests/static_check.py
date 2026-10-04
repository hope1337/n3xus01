"""Offline checks; no subprocess connects to target hosts or a real cluster."""
from __future__ import annotations

import ipaddress
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]


class UniqueLoader(yaml.SafeLoader):
    pass


def mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)


def load(relative):
    return yaml.load((ROOT / relative).read_text(encoding="utf-8"), Loader=UniqueLoader)


def main():
    files = sorted(set(ROOT.glob("**/*.yml")) | set(ROOT.glob("**/*.yaml")))
    files = [p for p in files if not any(x.startswith(".") and x != ".github" for x in p.relative_to(ROOT).parts)]
    # The real inventory and all runtime state are intentionally excluded.
    files = [p for p in files if p != ROOT / "inventory/hosts.yml"]
    for path in files:
        list(yaml.load_all(path.read_text(encoding="utf-8"), Loader=UniqueLoader))
    assert files, "No YAML files found"

    for path in [ROOT / "cluster", *ROOT.glob("tests/*.sh")]:
        content = path.read_bytes()
        assert b"\r" not in content, f"CRLF in {path}"
        assert content.startswith(b"#!/usr/bin/env bash\n"), f"Missing Bash shebang in {path}"

    role = load("roles/k3s_server/tasks/main.yml")
    imports = [task["ansible.builtin.import_tasks"] for task in role]
    assert imports == ["preflight.yml", "install.yml", "kubeconfig.yml"]
    for name in imports:
        assert (ROOT / "roles/k3s_server/tasks" / name).is_file()
    for playbook in ("setup", "reset"):
        plays = load(f"playbooks/{playbook}.yml")
        assert plays[0]["hosts"] == "k3s_servers"
        assert plays[0]["become"] is True
        assert plays[0]["any_errors_fatal"] is True

    defaults = load("roles/k3s_server/defaults/main.yml")
    assert re.fullmatch(r"v\d+\.\d+\.\d+\+k3s\d+", defaults["k3s_version"])
    env = Environment(undefined=StrictUndefined)
    env.filters["to_json"] = json.dumps
    variables = {"cluster_tailscale_ip": "100.101.102.103", "cluster_node_name": "first-node"}
    template_dir = ROOT / "roles/k3s_server/templates"
    for path in template_dir.glob("*.j2"):
        env.from_string(path.read_text(encoding="utf-8")).render(**variables)
    config = yaml.safe_load(env.from_string((template_dir / "config.yaml.j2").read_text(encoding="utf-8")).render(**variables))
    for field in ("bind-address", "advertise-address", "node-ip"):
        assert ipaddress.ip_address(config[field]) in ipaddress.ip_network("100.64.0.0/10")
    assert config["tls-san"] == [variables["cluster_tailscale_ip"]]
    assert config["flannel-iface"] == "tailscale0"
    assert {"traefik", "servicelb", "metrics-server"} <= set(config["disable"])
    assert config["write-kubeconfig-mode"] == "0600"
    assert "read-only-port=0" in config["kubelet-arg"]

    resources = list(yaml.safe_load_all((ROOT / "kubernetes/smoke-test.yml").read_text(encoding="utf-8")))
    assert {r["kind"] for r in resources} == {"Namespace", "Deployment", "Service"}
    ns, deployment, service = resources
    assert ns["metadata"]["labels"]["app.kubernetes.io/managed-by"] == "personal-compute-v1"
    assert service["spec"]["type"] == "ClusterIP"
    pod_spec = deployment["spec"]["template"]["spec"]
    assert not pod_spec.get("hostNetwork", False)
    assert not pod_spec.get("hostPID", False)
    assert "nodeSelector" not in pod_spec  # CPU test can run on the first server.
    for container in pod_spec["containers"]:
        assert not container["securityContext"].get("privileged", False)
        assert all("hostPort" not in p for p in container["ports"])
        assert "readinessProbe" in container

    kubeconfig_tasks = load("roles/k3s_server/tasks/kubeconfig.yml")
    for task in kubeconfig_tasks:
        if "ansible.builtin.slurp" in task or "ansible.builtin.copy" in task:
            assert task.get("no_log") is True, f"Credential task can log secrets: {task['name']}"
    copy = next(t["ansible.builtin.copy"] for t in kubeconfig_tasks if "ansible.builtin.copy" in t)
    assert copy["mode"] == "0600"

    # Exercise the actual read-only CIDR validator with fresh and rebooted-node routes.
    preflight = load("roles/k3s_server/tasks/preflight.yml")
    validator = next(t["ansible.builtin.command"]["argv"][2] for t in preflight if t["name"].startswith("Verify default Pod"))
    route_cases = [
        ([{"dst": "default", "dev": "eth0"}, {"dst": "192.168.1.0/24", "dev": "eth0"}], "fresh", True),
        ([{"dst": "10.42.1.0/24", "dev": "eth0"}], "fresh", False),
        ([{"dst": "10.0.0.0/8", "dev": "tailscale0"}], "fresh", False),
        ([{"dst": "10.43.0.9", "dev": "tun0"}], "owned", False),
        ([{"dst": "10.42.0.0/24", "dev": "cni0"}], "owned", True),
        ([{"dst": "10.42.0.0/24", "dev": "cni0"}], "fresh", False),
        ([{"dst": "0.0.0.0/0", "dev": "eth0"}], "fresh", True),
    ]
    for routes, owner, ok in route_cases:
        result = subprocess.run([sys.executable, "-c", validator, json.dumps(routes), owner], capture_output=True, text=True)
        assert (result.returncode == 0) == ok, (routes, owner, result.stderr)

    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for entry in ("/inventory/hosts.yml", "/.cluster/", "*.key", "*.pem"):
        assert entry in ignored
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    wrapper = (ROOT / "cluster").read_text(encoding="utf-8")
    for command in ("setup first-node", "status", "test", "check", "reset first-node --yes-delete-cluster"):
        assert f"./cluster {command}" in readme, f"Missing command in README: {command}"
    for path in re.findall(r'\$ROOT/(playbooks/[A-Za-z_-]+\.yml|kubernetes/[A-Za-z_-]+\.yml|tests/[A-Za-z_.]+)', wrapper):
        assert (ROOT / path).is_file(), f"Broken wrapper path: {path}"
    print(f"PASS: {len(files)} YAML files, strict Jinja rendering, private endpoints, credentials, CIDR safety, command/path consistency.")


if __name__ == "__main__":
    main()

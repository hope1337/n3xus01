#!/usr/bin/env bash
# Offline regression tests: fake external tools; no SSH or real Kubernetes.
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TEMP_BASE="$(cd -- "${TMPDIR:-/tmp}" && pwd -P)"
WORK="$(mktemp -d "$TEMP_BASE/cluster-wrapper-test.XXXXXXXX")"
WORK="$(cd -- "$WORK" && pwd -P)"
case "$WORK" in
  "$TEMP_BASE"/cluster-wrapper-test.*) ;;
  *) printf 'Refusing unexpected temporary directory: %s\n' "$WORK" >&2; exit 1 ;;
esac
trap 'rm -rf -- "$WORK"' EXIT
TEST_ROOT="$WORK/repo with spaces"
mkdir -p "$TEST_ROOT/inventory" "$TEST_ROOT/.cluster" "$TEST_ROOT/ansible" "$TEST_ROOT/playbooks" "$TEST_ROOT/kubernetes" "$WORK/bin"
cp "$ROOT/cluster" "$TEST_ROOT/cluster"
cp "$ROOT/kubernetes/smoke-test.yml" "$TEST_ROOT/kubernetes/smoke-test.yml"
chmod +x "$TEST_ROOT/cluster"
printf 'all: {}\n' > "$TEST_ROOT/inventory/hosts.yml"
printf 'offline fixture only\n' > "$TEST_ROOT/.cluster/kubeconfig.yaml"
export MOCK_LOG="$WORK/calls.log"
export MOCK_OWNER=personal-compute-v1
export MOCK_NAMESPACE_EXISTS=0
export MOCK_FAIL=""
export MOCK_OS=Linux
export PATH="$WORK/bin:$PATH"
# An unrelated shell KUBECONFIG must not redirect any cluster operation.
export KUBECONFIG=/unrelated/production-kubeconfig

cat > "$WORK/bin/uname" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$MOCK_OS"
MOCK
cat > "$WORK/bin/ssh" <<'MOCK'
#!/usr/bin/env bash
exit 0
MOCK
cat > "$WORK/bin/ansible-playbook" <<'MOCK'
#!/usr/bin/env bash
printf 'ansible %s\n' "$*" >> "$MOCK_LOG"
[[ "$MOCK_FAIL" != ansible ]]
MOCK
cat > "$WORK/bin/kubectl" <<'MOCK'
#!/usr/bin/env bash
printf 'kubectl %s\n' "$*" >> "$MOCK_LOG"
[[ "$1" == --kubeconfig && "$3" == --context && "$4" == personal-compute-v1 ]] || exit 99
[[ "$2" != "$KUBECONFIG" ]] || exit 99
shift 5
case "$*" in
  'get namespace '*jsonpath*) printf '%s' "$MOCK_OWNER" ;;
  'get namespace '*)
    [[ "$MOCK_FAIL" != namespace ]] || exit 42
    if [[ "$MOCK_NAMESPACE_EXISTS" == 1 ]]; then printf 'namespace/personal-compute-smoke\n'; fi
    ;;
  'rollout status '*) [[ "$MOCK_FAIL" != rollout ]] || exit 42 ;;
  'port-forward '*)
    printf 'Forwarding from 127.0.0.1:32123 -> 80\n'
    while :; do sleep 1; done
    ;;
  *) [[ "$MOCK_FAIL" != api ]] || exit 42 ;;
esac
MOCK
cat > "$WORK/bin/curl" <<'MOCK'
#!/usr/bin/env bash
printf 'curl %s\n' "$*" >> "$MOCK_LOG"
[[ "$MOCK_FAIL" != curl ]] || exit 42
printf '<html>Welcome to nginx!</html>\n'
MOCK
chmod +x "$WORK/bin/"*

run_ok() {
  : > "$MOCK_LOG"
  if ! (cd "$WORK" && bash "$TEST_ROOT/cluster" "$@") > "$WORK/output" 2>&1; then
    cat "$WORK/output"
    printf 'FAIL expected success: %s\n' "$*" >&2
    exit 1
  fi
}
run_fail() {
  : > "$MOCK_LOG"
  if (cd "$WORK" && bash "$TEST_ROOT/cluster" "$@") > "$WORK/output" 2>&1; then
    printf 'FAIL expected rejection: %s\n' "$*" >&2
    exit 1
  fi
  grep -q 'ERROR (' "$WORK/output"
}
no_calls() { [[ ! -s "$MOCK_LOG" ]] || { cat "$MOCK_LOG"; exit 1; }; }

run_ok help
no_calls
run_fail add-worker lab-01
no_calls
run_fail setup other-node
no_calls
run_fail reset first-node
no_calls
run_fail reset first-node --yes-delete-cluster --unexpected
no_calls
MOCK_OS=MINGW64_NT
run_fail setup first-node
no_calls
MOCK_OS=Linux

run_ok setup first-node
grep -Fq -- "ansible -i $TEST_ROOT/inventory/hosts.yml --ask-become-pass $TEST_ROOT/playbooks/setup.yml" "$MOCK_LOG"
grep -Fq -- "--kubeconfig $TEST_ROOT/.cluster/kubeconfig.yaml --context personal-compute-v1" "$MOCK_LOG"
run_ok setup first-node --no-sudo-prompt
! grep -q -- --ask-become-pass "$MOCK_LOG"
printf 'CHANGE_ME\n' > "$TEST_ROOT/inventory/hosts.yml"
run_fail setup first-node
no_calls
printf 'all: {}\n' > "$TEST_ROOT/inventory/hosts.yml"
MOCK_FAIL=ansible
run_fail setup first-node
! grep -q '^kubectl' "$MOCK_LOG"
MOCK_FAIL=""

run_ok status
grep -q 'get --raw=/readyz' "$MOCK_LOG"
run_ok kubectl get nodes
grep -q 'get nodes' "$MOCK_LOG"
run_ok test
grep -q 'PASS:' "$WORK/output"
grep -q 'port-forward --address 127.0.0.1' "$MOCK_LOG"
grep -q 'http://127.0.0.1:32123/' "$MOCK_LOG"
MOCK_NAMESPACE_EXISTS=1
MOCK_OWNER=someone-else
run_fail test
! grep -q ' apply ' "$MOCK_LOG"
run_fail test --cleanup
! grep -q ' delete ' "$MOCK_LOG"
MOCK_OWNER=personal-compute-v1
MOCK_FAIL=namespace
run_fail test
! grep -q ' apply ' "$MOCK_LOG"
MOCK_FAIL=rollout
run_fail test
! grep -q 'port-forward' "$MOCK_LOG"
MOCK_FAIL=curl
run_fail test
! grep -q 'PASS:' "$WORK/output"
MOCK_FAIL=""
run_ok test --cleanup
grep -q 'delete namespace personal-compute-smoke' "$MOCK_LOG"
run_ok reset first-node --yes-delete-cluster --no-sudo-prompt
grep -Fq '"cluster_confirm_reset": true' "$MOCK_LOG"

rm -f -- "$TEST_ROOT/.cluster/kubeconfig.yaml"
run_fail status
no_calls
printf 'PASS: wrapper safety, command routing, failure handling, isolated context, HTTP smoke flow.\n'

#!/usr/bin/env bash
set -euo pipefail

TEST_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "${TEST_DIR}/.." && pwd)"
INSTALL_SOURCE="${REPO_DIR}/install.sh"
ORIGINAL_PATH="${PATH}"
GENERATED_PATHS=(data darkmoon-settings workflows reports sessions workspace)
TEST_COUNT=0

fail() {
  echo "not ok - $*" >&2
  exit 1
}

pass() {
  TEST_COUNT=$((TEST_COUNT + 1))
  echo "ok ${TEST_COUNT} - $*"
}

assert_file_exists() {
  [ -e "$1" ] || fail "expected $1 to exist"
}

assert_path_absent() {
  [ ! -e "$1" ] && [ ! -L "$1" ] || fail "expected $1 to be absent"
}

assert_contains() {
  local file="$1"
  local expected="$2"
  grep -F -- "${expected}" "${file}" >/dev/null || {
    echo "--- ${file}" >&2
    cat "${file}" >&2 || true
    fail "expected ${file} to contain: ${expected}"
  }
}

assert_not_contains() {
  local file="$1"
  local unexpected="$2"
  if grep -F -- "${unexpected}" "${file}" >/dev/null; then
    echo "--- ${file}" >&2
    cat "${file}" >&2 || true
    fail "expected ${file} not to contain: ${unexpected}"
  fi
}

make_fixture() {
  local root="$1"
  local repo="${root}/repo"
  mkdir -p "${repo}/tests"
  cp "${INSTALL_SOURCE}" "${repo}/install.sh"
  chmod +x "${repo}/install.sh"
  : > "${repo}/docker-compose.yml"
  : > "${repo}/docker-compose-dev.yml"
  : > "${repo}/docker-compose.gpu.yml"
  cat > "${repo}/.opencode.env" <<'EOF_ENV'
OPENROUTER_PROVIDER=openrouter
OPENCODE_MODEL=test/model
OPENROUTER_API_KEY=test-key
EOF_ENV

  local path
  for path in "${GENERATED_PATHS[@]}"; do
    mkdir -p "${repo}/${path}"
    printf '%s\n' "${path}" > "${repo}/${path}/marker"
  done
}

make_mock_bin() {
  local root="$1"
  local mock_bin="${root}/mock-bin"
  mkdir -p "${mock_bin}"

  cat > "${mock_bin}/docker" <<'EOF_DOCKER'
#!/usr/bin/env bash
set -euo pipefail
printf '%q ' "$@" >> "${MOCK_DOCKER_LOG}"
printf '\n' >> "${MOCK_DOCKER_LOG}"

case "${1:-}" in
  info)
    if [ "${2:-}" = "--format" ]; then
      printf '%s\n' "${MOCK_DOCKER_RUNTIMES:-{}}"
    fi
    ;;
  compose)
    shift
    case " $* " in
      *" version "*) ;;
      *" config --images "*)
        printf '%s\n' "${MOCK_STACK_IMAGES:-mock/cleanup:latest}"
        ;;
      *) ;;
    esac
    ;;
  image)
    case "${2:-}" in
      inspect)
        [ "${MOCK_LOCAL_IMAGE:-1}" = "1" ]
        ;;
      rm) ;;
      *) ;;
    esac
    ;;
  builder)
    [ "${2:-}" = "prune" ] || exit 1
    ;;
  run)
    joined=" $* "
    if [[ "${joined}" == *"command -v rm"* ]]; then
      [ "${MOCK_ROOT_CAPABLE:-1}" = "1" ]
      exit $?
    fi

    mount=""
    previous=""
    for argument in "$@"; do
      if [ "${previous}" = "-v" ]; then
        mount="${argument}"
        break
      fi
      previous="${argument}"
    done
    [ -n "${mount}" ] || exit 1
    source_dir="${mount%:/darkmoon-root}"
    relative_path="${!#}"
    /bin/rm -rf -- "${source_dir}/${relative_path}"
    ;;
  *)
    echo "unexpected docker invocation: $*" >&2
    exit 1
    ;;
esac
EOF_DOCKER

  cat > "${mock_bin}/rm" <<'EOF_RM'
#!/usr/bin/env bash
set -euo pipefail
if [ -n "${MOCK_RM_FAIL_PATH:-}" ]; then
  for argument in "$@"; do
    if [ "${argument#./}" = "${MOCK_RM_FAIL_PATH}" ]; then
      exit 1
    fi
  done
fi
exec /bin/rm "$@"
EOF_RM

  cat > "${mock_bin}/uname" <<'EOF_UNAME'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "${MOCK_UNAME:-x86_64}"
EOF_UNAME

  chmod +x "${mock_bin}/docker" "${mock_bin}/rm" "${mock_bin}/uname"
}

run_installer() {
  local root="$1"
  shift
  env \
    PATH="${root}/mock-bin:${ORIGINAL_PATH}" \
    MOCK_DOCKER_LOG="${root}/docker.log" \
    "$@"
}

# Unknown options must fail before even checking Docker.
{
  root="$(mktemp -d)"
  trap 'rm -rf -- "${root}"' RETURN
  make_fixture "${root}"
  make_mock_bin "${root}"
  set +e
  output="$(cd / && run_installer "${root}" bash "${root}/repo/install.sh" --kepp 2>&1)"
  status=$?
  set -e
  [ "${status}" -eq 2 ] || fail "unknown option exited ${status}, expected 2"
  [[ "${output}" == *"Unknown option: --kepp"* ]] || fail "unknown option message missing"
  [ ! -s "${root}/docker.log" ] || fail "Docker was called for an unknown option"
  pass "unknown options fail before Docker operations"
  rm -rf -- "${root}"
  trap - RETURN
}

# --keep must preserve all runtime directories, named volumes, and caller data.
{
  root="$(mktemp -d)"
  trap 'rm -rf -- "${root}"' RETURN
  make_fixture "${root}"
  make_mock_bin "${root}"
  mkdir -p "${root}/outside/data"
  echo outside > "${root}/outside/data/marker"
  output_file="${root}/output"
  (cd "${root}/outside" && run_installer "${root}" bash "${root}/repo/install.sh" --keep) >"${output_file}" 2>&1

  for path in "${GENERATED_PATHS[@]}"; do
    assert_file_exists "${root}/repo/${path}/marker"
  done
  assert_file_exists "${root}/outside/data/marker"
  assert_not_contains "${root}/docker.log" "--volumes"
  assert_contains "${root}/docker.log" "compose -f docker-compose.yml down --remove-orphans"
  assert_contains "${output_file}" "Darkmoon stack rebuilt with persistent data retained"
  pass "--keep preserves all runtime data and named volumes from any working directory"
  rm -rf -- "${root}"
  trap - RETURN
}

# Clean mode must delete all generated bind mounts and remove named volumes.
{
  root="$(mktemp -d)"
  trap 'rm -rf -- "${root}"' RETURN
  make_fixture "${root}"
  make_mock_bin "${root}"
  output_file="${root}/output"
  run_installer "${root}" bash "${root}/repo/install.sh" >"${output_file}" 2>&1

  for path in "${GENERATED_PATHS[@]}"; do
    assert_path_absent "${root}/repo/${path}"
  done
  assert_contains "${root}/docker.log" "compose -f docker-compose.yml down --remove-orphans --volumes"
  assert_contains "${output_file}" "Darkmoon stack rebuilt CLEAN"
  pass "clean mode removes all generated bind mounts and named volumes"
  rm -rf -- "${root}"
  trap - RETURN
}

# Permission fallback must use a local image, explicitly run as root, and never pull.
{
  root="$(mktemp -d)"
  trap 'rm -rf -- "${root}"' RETURN
  make_fixture "${root}"
  make_mock_bin "${root}"
  output_file="${root}/output"
  env \
    PATH="${root}/mock-bin:${ORIGINAL_PATH}" \
    MOCK_DOCKER_LOG="${root}/docker.log" \
    MOCK_RM_FAIL_PATH="darkmoon-settings" \
    bash "${root}/repo/install.sh" >"${output_file}" 2>&1

  for path in "${GENERATED_PATHS[@]}"; do
    assert_path_absent "${root}/repo/${path}"
  done
  assert_contains "${root}/docker.log" "run --rm --pull=never --user 0:0"
  assert_contains "${root}/docker.log" "-v ${root}/repo:/darkmoon-root"
  assert_not_contains "${root}/docker.log" "pull alpine"
  if grep -E '^pull( |$)' "${root}/docker.log" >/dev/null; then
    fail "cleanup attempted an explicit docker pull"
  fi
  pass "root-owned cleanup is explicit, local-only, and pull-free"
  rm -rf -- "${root}"
  trap - RETURN
}

# ARM64 must use the development Compose file consistently.
{
  root="$(mktemp -d)"
  trap 'rm -rf -- "${root}"' RETURN
  make_fixture "${root}"
  make_mock_bin "${root}"
  env \
    PATH="${root}/mock-bin:${ORIGINAL_PATH}" \
    MOCK_DOCKER_LOG="${root}/docker.log" \
    MOCK_UNAME="aarch64" \
    bash "${root}/repo/install.sh" --keep >"${root}/output" 2>&1

  assert_contains "${root}/docker.log" "compose -f docker-compose-dev.yml config --images"
  assert_contains "${root}/docker.log" "compose -f docker-compose-dev.yml down --remove-orphans"
  assert_contains "${root}/docker.log" "compose -f docker-compose-dev.yml build --no-cache"
  assert_contains "${root}/docker.log" "compose -f docker-compose-dev.yml up -d --force-recreate"
  assert_not_contains "${root}/docker.log" "compose -f docker-compose.yml"
  pass "ARM64 uses docker-compose-dev.yml for every Compose operation"
  rm -rf -- "${root}"
  trap - RETURN
}

# If host removal fails and no local image can provide root cleanup, fail precisely.
{
  root="$(mktemp -d)"
  trap 'rm -rf -- "${root}"' RETURN
  make_fixture "${root}"
  make_mock_bin "${root}"
  set +e
  env \
    PATH="${root}/mock-bin:${ORIGINAL_PATH}" \
    MOCK_DOCKER_LOG="${root}/docker.log" \
    MOCK_RM_FAIL_PATH="darkmoon-settings" \
    MOCK_LOCAL_IMAGE="0" \
    bash "${root}/repo/install.sh" >"${root}/output" 2>&1
  status=$?
  set -e

  [ "${status}" -ne 0 ] || fail "cleanup unexpectedly succeeded without a local cleanup image"
  assert_contains "${root}/output" "No local stack image can run /bin/sh and rm as root"
  assert_contains "${root}/output" "sudo rm -rf -- ${root}/repo/darkmoon-settings"
  assert_not_contains "${root}/docker.log" "alpine"
  pass "cleanup fails safely with an exact manual command when no local image works"
  rm -rf -- "${root}"
  trap - RETURN
}

echo "1..${TEST_COUNT}"

# 🧹 Rebuild & Troubleshooting Darkmoon

This document explains:
- why a build can fail,
- when to rebuild,
- how to start fresh.

---

## 1. Frequent Docker Errors (Non-blocking)

Typical example:

```bash
failed to solve: error getting credentials
```

Or:

```bash
load metadata for docker.io/library/debian
```

👉 These errors:
- **do not come from the project**,
- are related to Docker network, WSL, or registries,
- are **temporary**.

### Simple Solution

Rerun the command:

```bash
docker compose build
```

or:

```bash
docker compose up -d
```

---

## 2. Why Docker Can Fail

Frequent causes:

* network timeout,
* DNS issue,
* corrupted Docker cache,
* unstable WSL (Windows).

👉 **No relation to the code quality or Dockerfiles.**

---

## 3. Clean Rebuild Script: `recreate_clean.sh`

Darkmoon provides a dedicated script:

```bash
./recreate_clean.sh
```

### What This Script Does

1. Stops the Docker stack
2. Removes the following bind mounts:

   * `./data`
   * `./darkmoon-settings`
   * `$HOME/darkmoon-docker-fs`
3. Rebuilds **without cache**
4. Recreates the stack cleanly

---

## 4. Why Use This Script

This script is **essential** if:

  * you have modified:

    * agents,
    * `darkmoon.json` (DarkMoon agent config),
    * `auth.json`,
* you have volume conflicts,
* you want a clean environment,
* you change the LLM model.

👉 It guarantees:

* a consistent state,
* a clean stack,
* no pollution from old builds.

---

## 5. Smart Configuration Inheritance

Even after a rebuild:

* configuration files can be **re-injected**,
* agents can be **copied automatically**,
* the seed logic runs **only once**.

---

## 6. When NOT to Rebuild

Do **not** rebuild if:

* you only modify a Markdown agent,
* you change a prompt,
* you modify a Python workflow in a mounted volume.

👉 These changes are taken into account **on the fly**.

---

## 7. Advanced Debugging

### Check Containers

```bash
docker ps
```

### DarkMoon Container Logs

```bash
docker logs darkmoon
```

### Darkmoon Toolbox Logs

```bash
docker logs darkmoon
```

---

## 8. Quick Summary

* Docker Error ≠ Darkmoon problem
* Rerunning is often enough
* `recreate_clean.sh` = clean rebuild
* Volumes = modification without rebuild

---

➡️ To understand the architecture:
see `docs/architecture.md`

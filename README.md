<div align="center">

# YANG Studio

**A modern workbench for exploring and operating on YANG models.**

[![CI](https://github.com/Karmatek-Consulting-LLC/yangstudio/actions/workflows/ci.yml/badge.svg)](https://github.com/Karmatek-Consulting-LLC/yangstudio/actions/workflows/ci.yml)
[![Container](https://github.com/Karmatek-Consulting-LLC/yangstudio/actions/workflows/release.yml/badge.svg)](https://github.com/Karmatek-Consulting-LLC/yangstudio/actions/workflows/release.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

[Documentation](https://yangstudio.karmatek.io) · [Container image](https://github.com/Karmatek-Consulting-LLC/yangstudio/pkgs/container/yangstudio)

</div>

---

Browse the YANG models a network device implements, then build and run NETCONF
or RESTCONF requests against it — from the same tree, in the same session.

```bash
docker run --rm --name yangstudio -p 8420:8420 -v yangstudio-data:/data \
  ghcr.io/karmatek-consulting-llc/yangstudio:latest
```

Then open <http://localhost:8420>.

## What it does

- **Reads schemas off the device, over either protocol.** Connect and it lists
  every module the box advertises — revisions, features, deviations — then
  downloads the ones you pick, in the background, with progress you can walk
  away from. Discovery works over NETCONF (`<hello>` and `<get-schema>`) or
  over RESTCONF (the YANG library), so a device that only runs RESTCONF is
  still fully usable.
- **Parses them into a browsable tree.** Virtualised, so a set with 100,000
  nodes scrolls at full speed. Filter by name, path, type or description and
  matches keep their ancestors for context.
- **Tells you what each node is.** Type and the typedef chain beneath it,
  constraints, allowed values (identityrefs resolve transitively — 273 concrete
  interface types, not one abstract identity), both paths, and whether it is
  config or state.
- **Builds requests from the tree.** Tick nodes and the NETCONF XML or the
  RESTCONF method, URI and JSON body are written as you go. Run either against
  a live device and read the reply pretty-printed and highlighted.

## Running it

### Docker

To try it out, in the foreground — `Ctrl-C` stops it, and `--rm` clears the
container away without touching the volume:

```bash
docker run --rm --name yangstudio \
  -p 8420:8420 \
  -v yangstudio-data:/data \
  ghcr.io/karmatek-consulting-llc/yangstudio:latest
```

To leave it running, detached and surviving reboots:

```bash
docker run -d --name yangstudio \
  --restart unless-stopped \
  -p 8420:8420 \
  -v yangstudio-data:/data \
  ghcr.io/karmatek-consulting-llc/yangstudio:latest
```

Docker rejects `--rm` together with `--restart`, so pick whichever fits. The
image runs as a non-root user and serves the API and UI from one process.

### Docker Compose

```yaml
# compose.yaml
services:
  yangstudio:
    image: ghcr.io/karmatek-consulting-llc/yangstudio:latest
    container_name: yangstudio
    ports:
      - "8420:8420"
    volumes:
      - yangstudio-data:/data
    environment:
      # Raise this if commits on your devices run long.
      YANGSTUDIO_RPC_TIMEOUT: "120"
    restart: unless-stopped

volumes:
  yangstudio-data:
```

That file ships in the repository as `compose.yaml`, so cloning and running
`docker compose up -d` works without editing anything.

```bash
docker compose up -d
```

**The volume matters.** `/data` holds your YANG repositories, sets and device
profiles. Without it, everything you download is lost when the container is
replaced. To keep it somewhere you can see, bind-mount a directory instead:

```yaml
    volumes:
      - ./yangstudio-data:/data
```

A repository is a plain directory of `.yang` files and a set is a JSON file, so
that directory is readable, diffable and version-controllable on its own.

> **Device passwords are stored in plain text** in `/data/devices/*.json`, as
> the app needs them to authenticate. Treat that volume as a secret: keep it off
> shared storage and out of git.

### From source

Needs [uv](https://docs.astral.sh/uv/) and Node 22+.

```bash
git clone https://github.com/Karmatek-Consulting-LLC/yangstudio
cd yangstudio
./run.sh
```

The script creates the virtualenv, installs dependencies, picks free ports —
8420 and 5173 are commonly taken — and prints both URLs.

## Configuration

Everything is optional.

| Variable | Default | Meaning |
|---|---|---|
| `YANGSTUDIO_DATA` | `~/.yangstudio` | Repositories, sets and device profiles |
| `YANGSTUDIO_HOST` | `127.0.0.1` | Bind address (`0.0.0.0` in the container) |
| `YANGSTUDIO_PORT` | `8420` | API and UI port |
| `YANGSTUDIO_RPC_TIMEOUT` | `60` | Seconds to wait for a NETCONF reply. A commit on a busy device can take most of this |
| `YANGSTUDIO_CORS` | `localhost:5173` | Allowed origins, comma-separated |
| `YANGSTUDIO_STATIC` | auto | Path to the built frontend |
| `YANGSTUDIO_UI_PORT` | `5173` | Vite dev server port (development only) |

## Getting started

First, make sure the device is running the services. On IOS-XE, the whole
thing is:

```
conf t
 aaa new-model
 aaa authentication login default local
 aaa authorization exec default local
 netconf-yang
 netconf-yang feature candidate-datastore
 ip http secure-server
 ip http authentication local
 no ip http server
 restconf
end
```

Apply the three AAA lines together — `aaa new-model` alone changes how logins
are authenticated and can lock you out. Exec authorisation is the one people
miss: without it a NETCONF session opens and is then dropped without a hello,
which looks like a credential problem and is not. Check with
`show netconf-yang status` and `show platform software yang-management process`.
[Full explanation in the docs](https://yangstudio.karmatek.io/getting-started#prepare).

Then:

1. **Devices** → add your device → **Connect**.
2. Choose NETCONF or RESTCONF next to **Connect**, then pick the modules you
   want — the family filters cut a 500-module list down fast — choose a
   repository, and **Download**. It runs in the background.
3. When it finishes, **Create set from these**. Imports are pulled in
   automatically, because a set that cannot resolve its imports will not parse.
4. **Explore** → pick the set. Click a node to inspect it, <kbd>Space</kbd> to
   add it to a request.
5. Choose NETCONF or RESTCONF, pick the device, **Run**.

Many devices refuse a direct write to `running` — IOS-XR and Junos always,
IOS-XE once `candidate-datastore` is enabled. There the flow is edit into
`candidate`, then **Commit**. YANG Studio says when a change is staged rather
than applied, so a successful-looking reply never implies the device changed.

If a set will not parse, the app names the missing imports and offers to fetch
them — the device advertises those too.

## Documentation

Full guides at **[yangstudio.karmatek.io](https://yangstudio.karmatek.io)**,
including a walkthrough of YANG itself written from inside the app: what a
capability string is, what you are downloading, and why a repository and a set
are different things.

## Architecture

```
backend/yangstudio
  core/quickparse.py   YANG header tokenizer — list a repo without parsing it
  core/storage.py      Repositories (directories) and sets (JSON)
  core/tree.py         pyang-backed schema tree, features and deviations applied
  core/rpc.py          NETCONF RPC composition
  core/resturl.py      RESTCONF path encoding (RFC 8040)
  core/devices.py      Device profiles, per-protocol inheritance
  services/            Parse cache and search, NETCONF, RESTCONF, background jobs
  api/routes.py        HTTP surface — OpenAPI at /docs

frontend/src
  components/TreeView      Virtualised, keyboard-navigable tree
  components/RequestBuilder, RestconfView, CodeView, TaskDrawer
  pages/Explore, Models, Devices
```

Two parsers, deliberately: listing a repository only needs each file's header,
and a full parse of a few hundred modules takes tens of seconds. 484 IETF
modules index in ~0.3 s; full parsing happens when you open a set.

## Development

```bash
cd backend  && ./.venv/bin/python -m pytest -q    # 105 tests
cd backend  && ./.venv/bin/python -m ruff check .
cd frontend && npm run build                      # typecheck + build
```

## Status

NETCONF and RESTCONF are built and tested against real hardware, sharing one
YANG engine. Not yet ported from the original: gNMI, gRPC telemetry, and saved
replays. The device profile model already carries per-protocol settings for
those.

## License

[Apache 2.0](LICENSE). See [NOTICE](NOTICE) for attribution and dependency
licences.

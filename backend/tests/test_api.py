"""API contract tests, including the paths that guard credentials."""
from pathlib import Path


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_repository_lifecycle(client):
    assert client.post("/api/repositories", json={"name": "R1"}).status_code == 201
    # Duplicate names are a client error, not a 500.
    assert client.post("/api/repositories", json={"name": "R1"}).status_code == 400
    assert [r["slug"] for r in client.get("/api/repositories").json()] == ["R1"]
    assert client.delete("/api/repositories/R1").status_code == 204
    assert client.get("/api/repositories/R1").status_code == 404


def test_upload_rejects_non_yang(client):
    client.post("/api/repositories", json={"name": "R2"})
    files = [("files", ("notes.txt", b"hello", "text/plain"))]
    body = client.post("/api/repositories/R2/upload", files=files).json()
    assert body["added"] == []
    assert body["skipped"][0]["reason"].startswith("'notes.txt' is not")


def test_explore_and_search(client, repo_with_modules):
    _, yangset = repo_with_modules
    tree = client.get(f"/api/explore/{yangset.slug}/tree").json()
    assert tree["stats"]["errors"] == 0
    assert tree["modules"][0]["name"] == "test-base"

    hits = client.get(f"/api/explore/{yangset.slug}/search", params={"q": "hostname"}).json()
    assert hits["results"][0]["name"] == "hostname"

    node = client.get(
        f"/api/explore/{yangset.slug}/node", params={"xpath": "/config/hostname"}
    ).json()
    assert node["mandatory"] is True

    missing = client.get(
        f"/api/explore/{yangset.slug}/node", params={"xpath": "/nope"}
    )
    assert missing.status_code == 404


def test_device_password_is_never_returned(client):
    created = client.post(
        "/api/devices",
        json={"name": "r1", "address": "10.0.0.1", "username": "admin", "password": "s3cret"},
    ).json()
    assert created["password"] == "********"
    assert created["has_password"] is True
    listed = client.get("/api/devices").json()[0]
    assert "s3cret" not in str(listed)


def test_patching_with_redacted_password_keeps_original(client):
    client.post(
        "/api/devices",
        json={"name": "r2", "address": "10.0.0.2", "username": "u", "password": "orig"},
    )
    client.patch("/api/devices/r2", json={"password": "********", "description": "edge"})
    from yangstudio.core.devices import Device

    assert Device.load("r2").password == "orig"
    assert Device.load("r2").description == "edge"


def test_protocol_settings_inherit_from_base(client):
    client.post(
        "/api/devices",
        json={
            "name": "r3",
            "address": "10.0.0.3",
            "username": "admin",
            "password": "p",
            "protocols": {"netconf": {"enabled": True, "port": 2022}},
        },
    )
    protocols = client.get("/api/devices/r3/protocols").json()
    assert protocols["netconf"]["address"] == "10.0.0.3"   # inherited
    assert protocols["netconf"]["username"] == "admin"     # inherited
    assert protocols["netconf"]["port"] == 2022            # overridden
    assert protocols["restconf"]["port"] == 443            # protocol default
    assert "password" not in protocols["netconf"]


def test_rpc_build_endpoint(client):
    body = client.post(
        "/api/rpc/build",
        json={
            "operation": "get-config",
            "datastore": "running",
            "namespaces": {"if": "urn:ietf:params:xml:ns:yang:ietf-interfaces"},
            "selections": [{"xpath": "/if:interfaces/if:interface/if:name"}],
        },
    ).json()
    assert "<nc:get-config>" in body["rpc_xml"]
    assert "urn:ietf:params:xml:ns:yang:ietf-interfaces" in body["rpc_xml"]


def test_rpc_build_rejects_empty_edit(client):
    resp = client.post("/api/rpc/build", json={"operation": "edit-config", "selections": []})
    assert resp.status_code == 400


def test_repository_modules_include_computed_key(client, repo_with_modules):
    """The client keys module selection off `key`, so it must be serialised."""
    repo, _ = repo_with_modules
    body = client.get(f"/api/repositories/{repo.slug}").json()
    module = body["modules"][0]
    assert module["key"] == "test-base@2024-01-01"


def test_download_rejects_empty_selection(client):
    """No modules selected is a client error, not a pointless empty job."""
    client.post("/api/devices", json={"name": "d1", "address": "10.0.0.9"})
    resp = client.post(
        "/api/netconf/d1/download-schemas", json={"modules": [], "repository": ""}
    )
    assert resp.status_code == 400
    assert "no modules selected" in resp.json()["detail"]


def test_download_unknown_device_is_404(client):
    resp = client.post(
        "/api/netconf/nope/download-schemas", json={"modules": ["ietf-interfaces"]}
    )
    assert resp.status_code == 404


def test_download_unknown_repository_is_404(client):
    client.post("/api/devices", json={"name": "d2", "address": "10.0.0.9"})
    resp = client.post(
        "/api/netconf/d2/download-schemas",
        json={"modules": ["ietf-interfaces"], "repository": "missing-repo"},
    )
    assert resp.status_code == 404


def test_jobs_endpoints_exist_and_start_empty(client):
    assert client.get("/api/jobs").json() == []
    assert client.get("/api/jobs/deadbeef").status_code == 404
    assert client.post("/api/jobs/deadbeef/cancel").status_code == 404


def test_create_set_from_modules(client, repo_with_modules):
    """The download → set handoff: an explicit module list becomes a set."""
    repo, _ = repo_with_modules
    body = client.post(
        "/api/yangsets/from-modules",
        json={"name": "from download", "repository": repo.slug, "modules": ["test-base"]},
    )
    assert body.status_code == 201
    data = body.json()
    assert data["module_count"] == 1
    assert data["validation"]["ok"] is True
    assert data["skipped"] == []


def test_create_set_from_modules_reports_unknown_names(client, repo_with_modules):
    repo, _ = repo_with_modules
    data = client.post(
        "/api/yangsets/from-modules",
        json={
            "name": "partial",
            "repository": repo.slug,
            "modules": ["test-base", "not-downloaded"],
        },
    ).json()
    assert data["skipped"] == ["not-downloaded"]
    assert data["module_count"] == 1


def test_create_set_from_modules_rejects_all_unknown(client, repo_with_modules):
    repo, _ = repo_with_modules
    resp = client.post(
        "/api/yangsets/from-modules",
        json={"name": "empty", "repository": repo.slug, "modules": ["nope"]},
    )
    assert resp.status_code == 400
    assert "none of those modules" in resp.json()["detail"]


def test_set_names_do_not_collide(client, repo_with_modules):
    """Creating the same-named set twice must not fail — it disambiguates."""
    repo, _ = repo_with_modules
    payload = {"name": "dupe", "repository": repo.slug, "modules": ["test-base"]}
    first = client.post("/api/yangsets/from-modules", json=payload).json()
    second = client.post("/api/yangsets/from-modules", json=payload).json()
    assert first["slug"] != second["slug"]
    assert second["name"] == "dupe 2"


def test_create_set_from_device_needs_a_known_device(client, repo_with_modules):
    repo, _ = repo_with_modules
    resp = client.post(
        "/api/yangsets/from-device",
        json={"name": "x", "repository": repo.slug, "device": "ghost"},
    )
    assert resp.status_code == 404


def test_git_import_keeps_one_file_per_name_and_revision(client, tmp_path, monkeypatch):
    """Repos carry the same module bare and revision-stamped, often twice over."""

    source = tmp_path / "clone"
    (source / "a").mkdir(parents=True)
    (source / "b").mkdir(parents=True)
    body = "module demo { namespace 'urn:demo'; prefix d; revision 2024-01-01; }"
    (source / "a" / "demo.yang").write_text(body)
    (source / "a" / "demo@2024-01-01.yang").write_text(body)
    (source / "b" / "demo.yang").write_text(body)
    (source / "b" / "other.yang").write_text(
        "module other { namespace 'urn:other'; prefix o; revision 2024-02-02; }"
    )

    class FakeRepo:
        git = type("G", (), {"checkout": lambda self, ref: None})()

    def fake_clone(url, dest, **kwargs):
        import shutil as sh

        sh.copytree(source, dest, dirs_exist_ok=True)
        return FakeRepo()

    monkeypatch.setattr("git.Repo.clone_from", staticmethod(fake_clone))

    client.post("/api/repositories", json={"name": "imported"})
    result = client.post(
        "/api/repositories/imported/import-git", json={"url": "https://example/x"}
    ).json()

    assert result["copied"] == 2
    assert result["skipped_duplicates"] == 2
    assert result["module_count"] == 2

    listed = client.get("/api/repositories/imported").json()["modules"]
    assert sorted(m["key"] for m in listed) == ["demo@2024-01-01", "other@2024-02-02"]
    # Files are named canonically, so a re-import lands on the same file.
    assert sorted(Path(m["path"]).name for m in listed) == [
        "demo@2024-01-01.yang",
        "other@2024-02-02.yang",
    ]

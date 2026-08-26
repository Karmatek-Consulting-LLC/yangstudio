"""Repository and yangset behaviour."""
import pytest

from yangstudio.core.storage import Repository, StorageError, YangSet, slugify


def test_slugify_rejects_empty_and_traversal():
    assert slugify("My Repo!") == "My-Repo"
    for bad in ("", "   ", "..", "/"):
        with pytest.raises(StorageError):
            slugify(bad)


def test_repository_indexes_and_caches(repo_with_modules):
    repo, _ = repo_with_modules
    modules = repo.modules()
    assert [m.name for m in modules] == ["test-base"]
    # A second call is served from the fingerprinted cache.
    assert repo.modules()[0].revision == "2024-01-01"


def test_find_module_prefers_newest_revision(repo_with_modules):
    repo, _ = repo_with_modules
    (repo.path / "test-base@2020-01-01.yang").write_text(
        "module test-base { namespace 'urn:x'; prefix tb; revision 2020-01-01; }"
    )
    repo.modules(refresh=True)
    assert repo.find_module("test-base").revision == "2024-01-01"
    assert repo.find_module("test-base", "2020-01-01").revision == "2020-01-01"
    assert repo.find_module("nope") is None


def test_duplicate_repository_rejected(repo_with_modules):
    with pytest.raises(StorageError):
        Repository.create("test-repo")


def test_yangset_validate_reports_unresolved_imports(repo_with_modules):
    repo, _ = repo_with_modules
    (repo.path / "needs-dep.yang").write_text(
        """
        module needs-dep {
          namespace "urn:example:needs"; prefix nd;
          import missing-module { prefix mm; }
          revision 2024-01-01;
        }
        """
    )
    repo.modules(refresh=True)
    yangset = YangSet.create("dep-set", repo.slug, [{"name": "needs-dep", "revision": ""}])
    report = yangset.validate()
    assert report["ok"] is False
    assert report["unresolved_dependencies"][0]["module"] == "missing-module"
    assert report["unresolved_dependencies"][0]["available_in_repo"] is False


def test_add_dependencies_pulls_transitively(repo_with_modules):
    repo, _ = repo_with_modules
    (repo.path / "a.yang").write_text(
        "module a { namespace 'urn:a'; prefix a; import b { prefix b; } revision 2024-01-01; }"
    )
    (repo.path / "b.yang").write_text(
        "module b { namespace 'urn:b'; prefix b; import c { prefix c; } revision 2024-01-01; }"
    )
    (repo.path / "c.yang").write_text(
        "module c { namespace 'urn:c'; prefix c; revision 2024-01-01; }"
    )
    repo.modules(refresh=True)
    yangset = YangSet.create("chain", repo.slug, [{"name": "a", "revision": ""}])
    assert yangset.add_dependencies() == 2
    assert {m["name"] for m in yangset.modules} == {"a", "b", "c"}
    assert yangset.validate()["ok"] is True


def test_missing_yangset_raises(repo_with_modules):
    with pytest.raises(StorageError, match="no such yangset"):
        YangSet.load("does-not-exist")


def test_validate_flags_two_revisions_of_one_module(repo_with_modules):
    """The same module at two revisions cannot resolve into one tree."""
    repo, _ = repo_with_modules
    (repo.path / "test-base@2023-01-01.yang").write_text(
        "module test-base { namespace 'urn:example:test-base'; prefix tb; "
        "revision 2023-01-01; }"
    )
    repo.modules(refresh=True)
    yangset = YangSet.create(
        "clash",
        repo.slug,
        [
            {"name": "test-base", "revision": "2024-01-01"},
            {"name": "test-base", "revision": "2023-01-01"},
        ],
    )
    report = yangset.validate()
    assert report["ok"] is False
    assert report["conflicting_revisions"] == [
        {"module": "test-base", "revisions": ["2023-01-01", "2024-01-01"]}
    ]


def test_add_dependencies_never_adds_a_second_revision(repo_with_modules):
    repo, _ = repo_with_modules
    (repo.path / "needs.yang").write_text(
        "module needs { namespace 'urn:n'; prefix n; "
        "import test-base { prefix tb; } revision 2024-01-01; }"
    )
    (repo.path / "test-base@2023-01-01.yang").write_text(
        "module test-base { namespace 'urn:example:test-base'; prefix tb; "
        "revision 2023-01-01; }"
    )
    repo.modules(refresh=True)
    # Pin the OLD revision explicitly; resolving imports must respect that.
    yangset = YangSet.create(
        "pinned",
        repo.slug,
        [{"name": "needs", "revision": ""}, {"name": "test-base", "revision": "2023-01-01"}],
    )
    yangset.add_dependencies()
    revisions = [m["revision"] for m in yangset.modules if m["name"] == "test-base"]
    assert revisions == ["2023-01-01"]
    assert yangset.validate()["conflicting_revisions"] == []


def test_feature_map_distinguishes_empty_from_absent(repo_with_modules):
    """An empty feature list means 'none supported', not 'unspecified'."""
    repo, _ = repo_with_modules
    yangset = YangSet.create(
        "features",
        repo.slug,
        [
            {"name": "test-base", "revision": "2024-01-01", "features": []},
            {"name": "other", "revision": ""},
        ],
    )
    mapping = yangset.feature_map()
    assert mapping == {"test-base": []}      # present-but-empty is kept
    assert "other" not in mapping            # absent means all features on


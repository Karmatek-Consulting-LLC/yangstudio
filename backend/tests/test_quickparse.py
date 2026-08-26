"""The header scanner must survive real-world YANG formatting."""
from yangstudio.core.quickparse import parse_text


def test_extracts_header_fields():
    info = parse_text(
        """
        module demo {
          namespace "urn:example:demo";
          prefix d;
          import ietf-yang-types { prefix yang; }
          include demo-sub;
          revision 2024-05-01;
          revision 2020-01-01;
        }
        """
    )
    assert info.name == "demo"
    assert info.namespace == "urn:example:demo"
    assert info.prefix == "d"
    assert info.imports == ["ietf-yang-types"]
    assert info.includes == ["demo-sub"]
    # Newest revision wins, even when the file lists them out of order.
    assert info.revision == "2024-05-01"
    assert info.key == "demo@2024-05-01"


def test_ignores_comments_and_braces_inside_strings():
    info = parse_text(
        """
        // module fake { prefix nope;
        /* namespace "urn:wrong"; */
        module real {
          namespace "urn:example:real{not-a-brace}";
          prefix r;   // trailing comment
        }
        """
    )
    assert info.name == "real"
    assert info.namespace == "urn:example:real{not-a-brace}"
    assert info.prefix == "r"


def test_handles_concatenated_strings():
    info = parse_text(
        'module c { namespace "urn:" + "example:" + "c"; prefix c; }'
    )
    assert info.namespace == "urn:example:c"


def test_nested_revision_date_is_not_module_revision():
    """An import's revision-date must not be mistaken for the module's."""
    info = parse_text(
        """
        module m {
          namespace "urn:m"; prefix m;
          import other { prefix o; revision-date 2019-09-09; }
          revision 2024-01-01;
        }
        """
    )
    assert info.revision == "2024-01-01"
    assert info.revisions == ["2024-01-01"]


def test_submodule_belongs_to():
    info = parse_text("submodule s { belongs-to parent { prefix p; } }")
    assert info.kind == "submodule"
    assert info.belongs_to == "parent"


def test_non_module_returns_none():
    assert parse_text("this is not yang at all") is None

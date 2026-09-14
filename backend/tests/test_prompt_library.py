"""Tests for `PromptLibrary` — the lightweight headed-fragment prompt loader
in `krutrim_agents_core.harness.prompts` (the in-repo stand-in for the
external `promptstore` package).

`load_prompt` (the original flat loader in the same module) is left untouched
by that addition; one regression test at the end guards it.
"""

from __future__ import annotations

import textwrap

import pytest
from krutrim_agents_core.harness import prompts as prompts_mod
from krutrim_agents_core.harness.prompts import (
    DEFAULT_SCOPE,
    PromptFormatError,
    PromptLibrary,
    PromptResolutionError,
    PromptVariableError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(root, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")


def _lib(root, files: dict[str, str]) -> PromptLibrary:
    for rel, text in files.items():
        _write(root, rel, text)
    return PromptLibrary(root)


# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------


def test_header_fields_are_parsed(tmp_path):
    lib = _lib(
        tmp_path,
        {
            "a.md": """
                <!--
                name: alpha
                scope: greeting
                description: a friendly hello
                variables:
                  - who
                -->
                hi {who}
            """,
        },
    )
    header = lib.header("alpha")
    assert header.name == "alpha"
    assert header.scope == "greeting"
    assert header.description == "a friendly hello"
    assert header.variables == frozenset({"who"})


def test_scope_defaults_to_default(tmp_path):
    lib = _lib(tmp_path, {"a.md": "<!--\nname: a\n-->\nbody\n"})
    assert lib.header("a").scope == DEFAULT_SCOPE
    assert lib.scopes("a") == [DEFAULT_SCOPE]


def test_unknown_header_keys_are_ignored(tmp_path):
    # eases migration from promptstore files that carry version / render_engine
    lib = _lib(
        tmp_path,
        {
            "a.md": """
                <!--
                name: a
                version: 1.2.3
                render_engine: f-string
                -->
                body
            """,
        },
    )
    assert lib.header("a").name == "a"


def test_quoted_header_values_are_dequoted(tmp_path):
    lib = _lib(
        tmp_path,
        {"a.md": '<!--\nname: "alpha"\ndescription: "with, comma"\n-->\nbody\n'},
    )
    assert lib.header("alpha").description == "with, comma"


def test_missing_name_is_rejected(tmp_path):
    with pytest.raises(PromptFormatError, match="missing a non-empty 'name'"):
        _lib(tmp_path, {"a.md": "<!--\nscope: x\n-->\nbody\n"})


def test_missing_header_comment_is_rejected(tmp_path):
    with pytest.raises(PromptFormatError, match="header comment"):
        _lib(tmp_path, {"a.md": "no header here, just text\n"})


def test_malformed_header_line_is_rejected(tmp_path):
    with pytest.raises(PromptFormatError, match="malformed header line"):
        _lib(tmp_path, {"a.md": "<!--\nname: a\nthis is not key value\n-->\nbody\n"})


def test_variables_inline_value_is_rejected(tmp_path):
    with pytest.raises(PromptFormatError, match="takes a '- item' list"):
        _lib(tmp_path, {"a.md": "<!--\nname: a\nvariables: who\n-->\n{who}\n"})


def test_duplicate_variable_entry_is_rejected(tmp_path):
    with pytest.raises(PromptFormatError, match="duplicate entry"):
        _lib(
            tmp_path,
            {"a.md": "<!--\nname: a\nvariables:\n  - who\n  - who\n-->\n{who}\n"},
        )


def test_invalid_variable_identifier_is_rejected(tmp_path):
    with pytest.raises(PromptFormatError, match="not a valid identifier"):
        _lib(
            tmp_path,
            {"a.md": "<!--\nname: a\nvariables:\n  - not-an-ident\n-->\nbody\n"},
        )


# ---------------------------------------------------------------------------
# Construction / indexing
# ---------------------------------------------------------------------------


def test_names_and_scopes_are_sorted(tmp_path):
    lib = _lib(
        tmp_path,
        {
            "x.md": "<!--\nname: beta\nscope: z\n-->\nb\n",
            "y.md": "<!--\nname: beta\nscope: a\n-->\nb\n",
            "z.md": "<!--\nname: alpha\n-->\na\n",
        },
    )
    assert lib.names() == ["alpha", "beta"]
    assert lib.scopes("beta") == ["a", "z"]
    assert lib.scopes("missing") == []


def test_duplicate_name_scope_across_files_is_rejected(tmp_path):
    with pytest.raises(PromptFormatError, match="two fragments share"):
        _lib(
            tmp_path,
            {
                "one.md": "<!--\nname: dup\nscope: s\n-->\nA\n",
                "two.md": "<!--\nname: dup\nscope: s\n-->\nB\n",
            },
        )


def test_same_name_different_scope_is_allowed(tmp_path):
    lib = _lib(
        tmp_path,
        {
            "f.md": "<!--\nname: greeting\nscope: formal\n-->\nGood evening.\n",
            "c.md": "<!--\nname: greeting\nscope: casual\n-->\nyo\n",
        },
    )
    assert lib.scopes("greeting") == ["casual", "formal"]


def test_non_directory_root_is_rejected(tmp_path):
    with pytest.raises(NotADirectoryError):
        PromptLibrary(tmp_path / "does-not-exist")


def test_nested_directories_are_scanned(tmp_path):
    lib = _lib(tmp_path, {"a/b/c/deep.md": "<!--\nname: deep\n-->\nfound\n"})
    assert lib.render("deep") == "found"


def test_construction_validates_every_fragment_even_unreferenced_ones(tmp_path):
    # `bad` is never included by anything, but a bad {token} in it must still
    # fail at construction — "all loading errors at load time".
    with pytest.raises(PromptFormatError, match="oops"):
        _lib(
            tmp_path,
            {
                "good.md": "<!--\nname: good\n-->\nfine\n",
                "bad.md": "<!--\nname: bad\n-->\n{oops}\n",
            },
        )


# ---------------------------------------------------------------------------
# Includes and cycles
# ---------------------------------------------------------------------------


def test_unknown_token_fails_at_construction(tmp_path):
    with pytest.raises(PromptFormatError, match="nonesuch"):
        _lib(tmp_path, {"a.md": "<!--\nname: a\n-->\n{nonesuch}\n"})


def test_self_include_is_a_cycle(tmp_path):
    with pytest.raises(PromptResolutionError, match="include cycle"):
        _lib(tmp_path, {"a.md": "<!--\nname: a\n-->\nloop {a}\n"})


def test_two_node_cycle_fails_at_construction(tmp_path):
    with pytest.raises(PromptResolutionError, match="include cycle"):
        _lib(
            tmp_path,
            {
                "a.md": "<!--\nname: a\n-->\n{b}\n",
                "b.md": "<!--\nname: b\n-->\n{a}\n",
            },
        )


def test_three_node_cycle_fails_at_construction(tmp_path):
    with pytest.raises(PromptResolutionError, match="include cycle"):
        _lib(
            tmp_path,
            {
                "a.md": "<!--\nname: a\n-->\n{b}\n",
                "b.md": "<!--\nname: b\n-->\n{c}\n",
                "c.md": "<!--\nname: c\n-->\n{a}\n",
            },
        )


def test_cycle_through_ambiguous_include_is_deferred_to_render(tmp_path):
    # `a` -> `b` is ambiguous (b has two scopes), so construction can't prove a
    # cycle and must not raise. Choosing scope `two` renders; `one` loops back.
    lib = _lib(
        tmp_path,
        {
            "a.md": "<!--\nname: a\n-->\nA\n{b}\n",
            "b_one.md": "<!--\nname: b\nscope: one\n-->\n{a}\n",
            "b_two.md": "<!--\nname: b\nscope: two\n-->\nplain\n",
        },
    )
    assert lib.render("a", scopes={"b": "two"}) == "A\nplain"
    with pytest.raises(PromptResolutionError, match="include cycle"):
        lib.render("a", scopes={"b": "one"})


# ---------------------------------------------------------------------------
# Variable validation
# ---------------------------------------------------------------------------


def test_required_variables_unions_the_whole_tree(tmp_path):
    lib = _lib(
        tmp_path,
        {
            "child.md": "<!--\nname: child\nvariables:\n  - a\n-->\nvalue {a}\n",
            "parent.md": "<!--\nname: parent\nvariables:\n  - b\n-->\n{child}\nand {b}\n",
        },
    )
    assert lib.required_variables("parent") == {"a", "b"}
    assert lib.render("parent", variables={"a": "1", "b": "2"}) == "value 1\nand 2"


def test_missing_variable_raises(tmp_path):
    lib = _lib(
        tmp_path,
        {"p.md": "<!--\nname: p\nvariables:\n  - x\n  - y\n-->\n{x} {y}\n"},
    )
    with pytest.raises(PromptVariableError, match=r"missing \['y'\]"):
        lib.render("p", variables={"x": "1"})


def test_unexpected_variable_raises(tmp_path):
    lib = _lib(tmp_path, {"p.md": "<!--\nname: p\nvariables:\n  - x\n-->\n{x}\n"})
    with pytest.raises(PromptVariableError, match=r"unexpected \['z'\]"):
        lib.render("p", variables={"x": "1", "z": "9"})


def test_no_variables_needed_renders_with_none(tmp_path):
    lib = _lib(tmp_path, {"p.md": "<!--\nname: p\n-->\njust text\n"})
    assert lib.render("p") == "just text"


def test_declared_variable_shadows_a_same_named_fragment(tmp_path):
    # {greeting} is declared as a variable here, so it stays a value slot even
    # though a fragment named `greeting` also exists — no include happens.
    lib = _lib(
        tmp_path,
        {
            "greeting.md": "<!--\nname: greeting\n-->\nSHOULD NOT APPEAR\n",
            "sys.md": "<!--\nname: sys\nvariables:\n  - greeting\n-->\n{greeting} world\n",
        },
    )
    assert lib.required_variables("sys") == {"greeting"}
    assert lib.render("sys", variables={"greeting": "hi"}) == "hi world"


def test_child_declares_its_own_variables(tmp_path):
    lib = _lib(
        tmp_path,
        {
            "inner.md": "<!--\nname: inner\nvariables:\n  - deep\n-->\ninner {deep}\n",
            "mid.md": "<!--\nname: mid\nvariables:\n  - mv\n-->\n{inner}\nmid {mv}\n",
            "outer.md": "<!--\nname: outer\nvariables:\n  - ov\n-->\n{mid}\nouter {ov}\n",
        },
    )
    assert lib.required_variables("outer") == {"deep", "mv", "ov"}
    assert (
        lib.render("outer", variables={"deep": "d", "mv": "m", "ov": "o"})
        == "inner d\nmid m\nouter o"
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_inheritance_renders_bottom_up_with_flat_vars(tmp_path):
    lib = _lib(
        tmp_path,
        {
            "p1/prompt_a.md": (
                "<!--\nname: ert\nscope: general\nvariables:\n  - who\n-->\nhello {who}\n"
            ),
            "p2/prompt_b.md": (
                "<!--\nname: dfg\nscope: abd\nvariables:\n  - topic\n-->\n"
                "{ert}\nabout {topic}\n"
            ),
        },
    )
    out = lib.render("dfg", variables={"who": "sam", "topic": "birds"})
    assert out == "hello sam\nabout birds"


def test_target_scope_selects_among_same_named_fragments(tmp_path):
    lib = _lib(
        tmp_path,
        {
            "f.md": "<!--\nname: t\nscope: formal\n-->\nFORMAL\n",
            "c.md": "<!--\nname: t\nscope: casual\n-->\ncasual\n",
        },
    )
    assert lib.render("t", scope="formal") == "FORMAL"
    assert lib.render("t", scope="casual") == "casual"
    with pytest.raises(PromptResolutionError, match="registered under scopes"):
        lib.render("t")
    with pytest.raises(
        PromptResolutionError, match="no fragment 't' with scope 'nope'"
    ):
        lib.render("t", scope="nope")


def test_unknown_target_name_raises(tmp_path):
    lib = _lib(tmp_path, {"a.md": "<!--\nname: a\n-->\nx\n"})
    with pytest.raises(PromptResolutionError, match="no fragment named 'missing'"):
        lib.render("missing")


def test_ambiguous_include_needs_a_scope(tmp_path):
    lib = _lib(
        tmp_path,
        {
            "gf.md": "<!--\nname: greeting\nscope: formal\n-->\nGood evening.\n",
            "gc.md": "<!--\nname: greeting\nscope: casual\n-->\nyo\n",
            "sys.md": (
                "<!--\nname: system\nvariables:\n  - task\n-->\n{greeting} Task: {task}\n"
            ),
        },
    )
    with pytest.raises(PromptResolutionError, match="ambiguous across scopes"):
        lib.render("system", variables={"task": "x"})
    assert (
        lib.render("system", variables={"task": "x"}, scopes={"greeting": "formal"})
        == "Good evening. Task: x"
    )
    assert (
        lib.render("system", variables={"task": "x"}, scopes={"greeting": "casual"})
        == "yo Task: x"
    )
    with pytest.raises(PromptResolutionError, match="only has scopes"):
        lib.render("system", variables={"task": "x"}, scopes={"greeting": "nope"})


def test_diamond_include_shares_a_leaf_variable(tmp_path):
    lib = _lib(
        tmp_path,
        {
            "leaf.md": "<!--\nname: leaf\nvariables:\n  - n\n-->\nleaf {n}\n",
            "l.md": "<!--\nname: l\n-->\nleft {leaf}\n",
            "r.md": "<!--\nname: r\n-->\nright {leaf}\n",
            "top.md": "<!--\nname: top\n-->\n{l}\n{r}\n",
        },
    )
    assert lib.required_variables("top") == {"n"}
    assert lib.render("top", variables={"n": "7"}) == "left leaf 7\nright leaf 7"


def test_repeated_include_in_one_body(tmp_path):
    lib = _lib(
        tmp_path,
        {
            "x.md": "<!--\nname: x\nvariables:\n  - v\n-->\n{v}\n",
            "y.md": "<!--\nname: y\n-->\n{x} {x}\n",
        },
    )
    assert lib.render("y", variables={"v": "z"}) == "z z"


def test_non_identifier_braces_are_left_untouched(tmp_path):
    lib = _lib(
        tmp_path,
        {
            "j.md": (
                "<!--\nname: j\nvariables:\n  - x\n-->\n"
                'ex: {"k": "v"} and { spaced } and {x}\n'
            ),
        },
    )
    assert (
        lib.render("j", variables={"x": "1"}) == 'ex: {"k": "v"} and { spaced } and 1'
    )


def test_brace_glued_to_another_character_is_literal(tmp_path):
    # the motivating case: a markdown-spec fragment writes `S{section_number}[.{slug}]`
    # as literal template syntax — a brace touching a non-space/newline character
    # is not a slot, so `section_number` / `slug` don't have to resolve to anything.
    lib = _lib(
        tmp_path,
        {
            "spec.md": (
                "<!--\nname: spec\nvariables:\n  - real\n-->\n"
                "Heading id: S{section_number}[.{slug}] — kept as-is.\n"
                "env={HOME} too. But {real} is a real slot.\n"
            ),
        },
    )
    assert lib.required_variables("spec") == {"real"}
    assert lib.render("spec", variables={"real": "X"}) == (
        "Heading id: S{section_number}[.{slug}] — kept as-is.\n"
        "env={HOME} too. But X is a real slot."
    )


def test_variable_value_with_braces_is_inserted_literally(tmp_path):
    # a value that itself contains {...} must not be re-scanned / re-substituted
    lib = _lib(tmp_path, {"p.md": "<!--\nname: p\nvariables:\n  - blob\n-->\n{blob}\n"})
    assert lib.render("p", variables={"blob": "{who} {x}"}) == "{who} {x}"


def test_non_string_variable_values_are_stringified(tmp_path):
    lib = _lib(tmp_path, {"p.md": "<!--\nname: p\nvariables:\n  - n\n-->\nn is {n}\n"})
    assert lib.render("p", variables={"n": 42}) == "n is 42"


# ---------------------------------------------------------------------------
# Module-level helpers: prompt_library() factory, load_prompt() regression
# ---------------------------------------------------------------------------


def test_prompt_library_factory_is_cached_and_rooted_at_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(prompts_mod.settings, "harness_dir", tmp_path)
    _write(tmp_path, "prompts/sub/a.md", "<!--\nname: a\n-->\nfrom sub\n")
    prompts_mod.prompt_library.cache_clear()
    try:
        lib1 = prompts_mod.prompt_library("sub")
        lib2 = prompts_mod.prompt_library("sub")
        assert lib1 is lib2  # cached per distinct root
        assert lib1.render("a") == "from sub"  # rooted at harness/prompts/sub
    finally:
        prompts_mod.prompt_library.cache_clear()


def test_load_prompt_is_unaffected_and_still_reads_a_flat_file(tmp_path, monkeypatch):
    monkeypatch.setattr(prompts_mod.settings, "harness_dir", tmp_path)
    _write(tmp_path, "prompts/demo/main.md", "  plain prompt body  \n")
    prompts_mod.load_prompt.cache_clear()
    try:
        assert prompts_mod.load_prompt("demo", "main") == "plain prompt body"
    finally:
        prompts_mod.load_prompt.cache_clear()

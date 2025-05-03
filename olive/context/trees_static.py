from typing import Dict, Set

# ext → grammar repo / pkg name  (add more at will)
GRAMMARS: Dict[str, str] = {
    ".js": "tree_sitter_javascript",
    ".jsx": "tree_sitter_javascript",
    ".ts": "tree_sitter_typescript",
    ".tsx": "tree_sitter_typescript",
    ".html": "tree_sitter_html",
    ".css": "tree_sitter_css",
    ".c": "tree_sitter_c",
    ".h": "tree_sitter_c",
    ".cc": "tree_sitter_cpp",
    ".cpp": "tree_sitter_cpp",
    ".rs": "tree_sitter_rust",
    ".go": "tree_sitter_go",
    ".lua": "tree_sitter_lua",
    ".lisp": "tree_sitter_commonlisp",
}

# ----------------------------------------------------------------------
#  Top-level “interesting” node sets per Tree-sitter language
#  – Only nodes that normally appear at depth-1 in a source file
#  – Names taken from the official grammars at their latest release
#    (0.20 / 0.21 ABI wheels as of May 2025)
# ----------------------------------------------------------------------

INTERESTING_BY_LANG: Dict[str, Set[str]] = {
    # ── JavaScript / JSX ───────────────────────────────────────────
    "javascript": {
        "function_declaration",
        "generator_function_declaration",
        "class_declaration",
        "lexical_declaration",          #  top-level “const/let/var …”
    },

    # ── TypeScript / TSX ──────────────────────────────────────────
    "typescript": {
        "function_declaration",
        "generator_function_declaration",
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "type_alias_declaration",
        "lexical_declaration",
    },

    # ── HTML (handled specially downstream) ───────────────────────
    "html": {
        "element",                      # we’ll further filter/_keep_html()
    },

    # ── CSS / SCSS / SASS ─────────────────────────────────────────
    "css": {
        "rule_set",                     # e.g. “.btn { … }”
        "at_rule",                      # “@media …”, “@keyframes …”
    },

    # ── C (and .h headers) ────────────────────────────────────────
    "c": {
        "function_definition",
        "struct_specifier",
        "union_specifier",
        "enum_specifier",
    },

    # ── C++ ───────────────────────────────────────────────────────
    "cpp": {
        "function_definition",
        "class_specifier",
        "struct_specifier",
        "enum_specifier",
        "namespace_definition",
        "template_declaration",
    },

    # ── Rust ──────────────────────────────────────────────────────
    "rust": {
        "function_item",
        "struct_item",
        "enum_item",
        "trait_item",
        "impl_item",
        "macro_definition",
        "mod_item",
        "const_item",
        "static_item",
        "type_item",
    },

    # ── Go ────────────────────────────────────────────────────────
    "go": {
        "function_declaration",
        "method_declaration",
        "type_declaration",             # covers struct + interface defs
        "const_declaration",
        "var_declaration",
        "import_declaration",
    },

    # ── Lua ───────────────────────────────────────────────────────
    "lua": {
        "function_declaration",
        "local_function",
    },

    # ── Common Lisp ───────────────────────────────────────────────
    #   Grammar exposes only generic “list” / “symbol” nodes; better
    #   to rely on heuristic fallback for signal.  Leave empty.
    "commonlisp": set(),
}

# ------------------------------------------------------------------
#  Derived tables – nothing else in the codebase needs to hard-code
# ------------------------------------------------------------------
# ext -> canonical language name  (".js" -> "javascript")
_LANG_FROM_EXT: dict[str, str] = {}

for ext, pkg in GRAMMARS.items():
    # tree_sitter_javascript  ->  javascript
    lang = pkg.replace("tree_sitter_", "")
    _LANG_FROM_EXT[ext] = lang

# auto-fill empty INTERESTING_BY_LANG entries with an empty set
for lang in _LANG_FROM_EXT.values():
    INTERESTING_BY_LANG.setdefault(lang, set())

def lang_from_ext(ext: str) -> str:
    """Return canonical language name for a file suffix, or ext.lstrip('.') fallback."""
    return _LANG_FROM_EXT.get(ext.lower(), ext.lstrip("."))

def interesting_nodes(lang: str) -> set[str]:
    """Return the node-type whitelist for a language (may be empty)."""
    return INTERESTING_BY_LANG.get(lang, set())


#****************************************************************************
#* conf.py
#*
#* Sphinx configuration for the dv-flow-libhdllint documentation.
#****************************************************************************
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_LIB = os.path.join(_HERE, "..", "src", "dv_flow", "libhdllint")

project = "dv-flow-libhdllint"
copyright = "2025, Matthew Ballance and Contributors"
author = "Matthew Ballance"

# autodoc imports the package, so src/ has to be importable whether or not the
# distribution is installed into the environment running Sphinx.
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "src")))

# `myst_parser` is listed because `dvflow_doc_format = "markdown"` below is
# inert without it -- having the module installed is not enough. With markdown
# selected and the parser unregistered, a fenced code block in a `doc:` string
# reaches docutils unparsed and the build reports `Unexpected indentation`
# rather than anything naming myst. It is also what parses the hand-written
# guide pages, which are Markdown.
extensions = [
    "myst_parser",
    "sphinxcontrib.mermaid",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx_dv_flow",
]

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Tables are the dominant shape in these guides (capability matrices, profile
# mappings, the cross-tool rule table), and GFM pipe tables are not core
# CommonMark.
myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 3

# ---------------------------------------------------------------------------
# sphinx-dv-flow
# ---------------------------------------------------------------------------
# This distribution registers seven flow packages by entry point -- the core
# `hdllint` package plus one per backend -- each a separate file in the same
# directory, so there is no single project root that covers them all. The
# default below is the core package; the backend pages carry `:root:` of their
# own.
dvflow_root = os.path.abspath(os.path.join(_LIB, "flow.dv"))

# The `desc:`/`doc:` strings in these flow files are Markdown because the same
# strings are read by `dfm show`, `dfm llms` and editor hovers, none of which
# render reStructuredText. The docs build follows what is written rather than
# asking the flow files to be written twice.
dvflow_doc_format = "markdown"

# `std.FileSet` and friends are types this library consumes and dv-flow-mgr
# owns. Naming them here says "documented elsewhere" instead of suppressing the
# nitpick; when dv-flow-mgr publishes an inventory, an `intersphinx_mapping`
# entry turns these into links with nothing else to change.
dvflow_intersphinx_packages = ["std"]

# Reported (dvflow-coverage.txt), not enforced: an undocumented parameter is a
# finding about the flow file, not a broken document, and folding it into `-W`
# is how the report ends up switched off.
dvflow_coverage = True

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
html_theme = "furo"
html_title = "dv-flow-libhdllint"

# No `html_static_path`/`templates_path` until there is an asset to put in
# them: an entry naming an empty directory works in the tree that created it
# and fails under -W on every clean checkout.

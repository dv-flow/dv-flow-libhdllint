# Minimal makefile for Sphinx documentation
#
# SPHINXBUILD defaults to the ivpm-assembled virtual environment
# (`ivpm update -a -d default-dev`), which is where sphinx-dv-flow comes from --
# it is not on PyPI. Override it for any other environment:
#
#   make html SPHINXBUILD=sphinx-build
#
DOC_DIR:=$(dir $(abspath $(lastword $(MAKEFILE_LIST))))
PROJ_DIR:=$(abspath $(DOC_DIR)/..)

SPHINXOPTS    ?=
SPHINXBUILD   ?= $(PROJ_DIR)/packages/python/bin/sphinx-build
SOURCEDIR     = .
BUILDDIR      = _build

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

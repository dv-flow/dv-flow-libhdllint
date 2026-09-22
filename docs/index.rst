dv-flow-libhdllint
==================

HDL lint for `dv-flow <https://github.com/dv-flow/dv-flow-mgr>`_: run one or
more lint tools over a set of sources and get **one** normalized report.

.. code-block:: yaml

   - name: rtl
     uses: std.FileSet
     with: {type: verilogSource, base: rtl, include: "*.v"}

   - name: lint
     uses: hdllint.Rtl
     needs: [rtl]
     with:
       top: [my_top]

.. code-block:: text

   $ dfm run lint
     W [verilator:WIDTHTRUNC] Operator ASSIGNW expects 1 bits ... (rtl/top.v:344)
     W [verilator:UNUSEDSIGNAL] Signal is not used: 'rst' (rtl/wb_mast.v:85)
     I lint: 2 new findings: 2 warnings [fail_on=error]
     I Lint reports: rundir/lint/lint.json, rundir/lint/lint.sarif, rundir/lint/lint-ctrf.json

How this differs from ``hdlsim``
--------------------------------

``hdlsim`` selects exactly **one** simulator: ``hdlsim.sim`` is a scalar and an
``elaborate:`` clause rebinds ``uses:`` to ``hdlsim.<sim>.<Family>``.

``hdllint`` does not. Lint is normally run with several tools at once, because
what each tool sees barely overlaps with what the others see. So the family
tasks take ``tools:`` -- a **list** -- and merge the results into one report.
An empty list (the default) means "every registered tool that implements this
family and is installed", which is what makes ``uses: hdllint.Rtl`` work with
no configuration. ``hdllint.vlt.Rtl`` is the same task with ``tools:`` pinned.

A **named** tool that is not installed is an error; an **auto-selected** tool
that is not installed is a skip, reported as an Info marker. A report is never
quietly thin -- see :doc:`guide/backends`.

The three families
------------------

.. list-table::
   :header-rows: 1
   :widths: 14 46 40

   * - Family
     - What it checks
     - Backends
   * - :dvf:task:`hdllint.Rtl`
     - Design lint: width, latch, unused/undriven, races
     - ``vlt``, ``spy``, ``z0i``, ``vcs``, ``qst``, ``jg``
   * - :dvf:task:`hdllint.Tb`
     - Testbench lint: class-based code, constraints, assertions
     - none yet -- asking for it fails, naming what would implement it
   * - :dvf:task:`hdllint.Style`
     - Formatting and naming
     - ``spy``, ``vcs``

Where to go next
----------------

* :doc:`quickstart` -- a lint task, a waiver, a baseline, in that order.
* :doc:`guide/index` -- backends and selection, profiles, waivers, the
  baseline, the gate, and the three report formats.
* :doc:`reference/index` -- every task and type, generated from the flow files.

.. toctree::
   :maxdepth: 2
   :caption: Contents

   install
   quickstart
   guide/index
   reference/index
   contributing

Trademarks
----------

All tool names are the property of their respective owners.

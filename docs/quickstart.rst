Quickstart
==========

Four steps, in the order a project actually meets them: run lint, stop the
noise, accept the backlog, then decide what fails the build.

1. Run lint
-----------

.. code-block:: yaml

   package:
     name: my-project
     imports:
     - name: hdllint

     tasks:
     - name: rtl
       uses: std.FileSet
       with: {type: verilogSource, base: rtl, include: "*.v"}

     - name: lint
       uses: hdllint.Rtl
       needs: [rtl]
       with:
         top: [my_top]

.. code-block:: shell

   dfm run lint

``top:`` matters more than it looks. Verilator and its peers produce their
high-value checks only when they can *elaborate*, which needs a top. A run with
no ``top:`` still works, and says so as an Info marker -- so a thin report is
never a mystery.

With ``tools:`` left empty, every registered backend that implements ``Rtl``
and is installed runs, and the ones that are not installed are reported as
skipped. To pin one tool, use its sub-package:

.. code-block:: yaml

     - name: lint
       uses: hdllint.vlt.Rtl     # same task, tools: [vlt]

2. Waive what is not a bug
--------------------------

.. code-block:: yaml

   # lint-waivers.yaml
   waivers:
   - rule: WIDTHEXPAND
     path: "packages/wb_dma/**"
     reason: "Third-party DUT, not modified by this project"

.. code-block:: yaml

     - name: lint-waivers
       uses: hdllint.LintWaivers
       with:
         file: lint-waivers.yaml

     - name: lint
       uses: hdllint.Rtl
       needs: [rtl, lint-waivers]
       with:
         top: [my_top]

``reason`` is required -- a waiver without one is a load error, because the
reason is the only part of it still useful once the author has moved on. A
waiver that matches nothing is reported as stale: the finding was either fixed
(delete the waiver) or moved (fix it). See :doc:`guide/waivers`.

3. Baseline the backlog
-----------------------

This is the step that decides whether lint gets adopted on existing code or
gets switched off in week two. A waiver says *this is not a bug*; a baseline
says *this is a bug we have not fixed yet*, and the two should not be confused.

.. code-block:: yaml

     - name: lint
       uses: hdllint.Rtl
       needs: [rtl]
       with:
         top: [my_top]
         baseline: lint-baseline.json

.. code-block:: shell

   dfm run lint -D lint.update_baseline=true   # accept today's findings
   dfm run lint
     I lint: 0 new findings (97 baselined) [fail_on=error]

New code is now held to a clean bar while the backlog stays visible and
countable. See :doc:`guide/baseline`.

4. Choose what fails the build
------------------------------

.. code-block:: yaml

     with:
       fail_on: warning     # none | error | warning | any

Only **new** findings count -- waived and baselined ones have already been
accepted. Failure is an explicit policy rather than a side effect of severity,
so someone adopting lint can run it, see error findings, and still get a zero
exit while they work through them. See :doc:`guide/gate`.

Where the reports go
--------------------

Every run writes three renderings of one finding list:

.. code-block:: text

   rundir/lint/lint.json         the authoritative record
   rundir/lint/lint.sarif        GitHub code scanning, IDE problem lists
   rundir/lint/lint-ctrf.json    the CI test-report UI

:doc:`guide/reports` covers what each one is for, and how to wire the last two
into CI.

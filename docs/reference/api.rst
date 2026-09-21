Python API
==========

The modules behind the tasks. A flow file never touches these; a **backend
author** does, and :doc:`../contributing` is the guide that walks through them
in the order they are written.

The three pure modules -- ``finding``, ``waiver`` and ``baseline`` -- are pure
on purpose: they are what make a backend testable with no tool installed.

The normalized finding
----------------------

.. automodule:: dv_flow.libhdllint.finding
   :members:
   :undoc-members:

The backend registry
--------------------

.. automodule:: dv_flow.libhdllint.backends
   :members:
   :undoc-members:

Waivers
-------

.. automodule:: dv_flow.libhdllint.waiver
   :members:
   :undoc-members:

Baseline
--------

.. automodule:: dv_flow.libhdllint.baseline
   :members:
   :undoc-members:

The gate
--------

.. automodule:: dv_flow.libhdllint.gate
   :members:
   :undoc-members:

Reports
-------

.. automodule:: dv_flow.libhdllint.report
   :members:
   :undoc-members:

The task implementation
-----------------------

.. automodule:: dv_flow.libhdllint.lint_runner
   :members:
   :undoc-members:

Tool execution helpers
----------------------

.. automodule:: dv_flow.libhdllint.util
   :members:
   :undoc-members:

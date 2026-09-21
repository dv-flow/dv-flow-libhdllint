``hdllint``
===========

The core package: the three family tasks and the data types that configure
them and report their result.

.. code-block:: yaml

   package:
     name: my-project
     imports:
     - name: hdllint

The family task **is** the implementation. It resolves ``tools:`` against the
capability registry, runs each selected backend, merges the findings and
writes the reports; ``hdllint.<tool>.<Family>`` is this same task with
``tools:`` pinned to one backend -- see :doc:`backends`.

Tasks and types
---------------

``LintArgs`` and ``LintWaivers`` are the dataflow interface -- delivered
through ``needs:``, so one task can configure lint everywhere it appears --
and ``Report`` is the verdict the rest of the flow can act on.

.. dvf:autopackage::
   :types:

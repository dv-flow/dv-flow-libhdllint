Reference
=========

Generated from the flow files. Every task, parameter, type and contract on the
package pages is extracted from ``src/dv_flow/libhdllint/*_flow.dv`` at build
time, so a page that disagrees with the library is a bug in the library's
``desc:``/``doc:`` rather than in the page.

.. toctree::
   :maxdepth: 2

   hdllint
   backends
   api

Which packages there are
------------------------

Seven flow packages are registered by entry point: the core ``hdllint``
package, which is where the family tasks and the data types live, and one
sub-package per backend, which is the same family task with ``tools:`` pinned.

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Package
     - What it is
   * - :doc:`hdllint <hdllint>`
     - ``Rtl``, ``Tb``, ``Style``, and the ``LintArgs`` / ``LintWaivers`` /
       ``Report`` types
   * - :doc:`hdllint.vlt … hdllint.jg <backends>`
     - One per backend: the family tasks with ``tools:`` pinned to that tool

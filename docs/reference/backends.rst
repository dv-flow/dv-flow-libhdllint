Backend packages
================

One sub-package per lint tool. Each exports the families that tool implements,
as the :doc:`hdllint <hdllint>` family task with ``tools:`` pinned -- identical
in every other respect: same waivers, same baseline, same reports.

Use ``hdllint.<tool>.<Family>`` when a flow wants a specific tool; use
``hdllint.<Family>`` when it wants whatever is installed. What the empty
``tools:`` list selects, and what happens when a named tool is missing, is in
:doc:`../guide/backends`.

Each page below is generated from that backend's own flow file, so the profile
mapping it documents is the one the backend actually applies.

``hdllint.vlt`` -- Verilator
----------------------------

.. dvf:autopackage::
   :root: ../src/dv_flow/libhdllint/vlt_flow.dv

``hdllint.spy`` -- SpyGlass
---------------------------

.. dvf:autopackage::
   :root: ../src/dv_flow/libhdllint/spy_flow.dv

``hdllint.vcs`` -- VC Static
----------------------------

.. dvf:autopackage::
   :root: ../src/dv_flow/libhdllint/vcs_flow.dv

``hdllint.qst`` -- Questa Lint
------------------------------

.. dvf:autopackage::
   :root: ../src/dv_flow/libhdllint/qst_flow.dv

``hdllint.jg`` -- JasperGold
----------------------------

.. dvf:autopackage::
   :root: ../src/dv_flow/libhdllint/jg_flow.dv

``hdllint.z0i`` -- 0-in
-----------------------

.. dvf:autopackage::
   :root: ../src/dv_flow/libhdllint/z0i_flow.dv

Trademarks
----------

All tool names are the property of their respective owners.

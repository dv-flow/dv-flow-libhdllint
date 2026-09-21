Installation
============

.. code-block:: shell

   pip install dv-flow-libhdllint

That is the whole install. ``dv-flow-mgr`` comes with it, and the seven flow
packages (``hdllint`` and one per backend) register themselves through the
``dv_flow.mgr`` entry point -- there is nothing to add to a flow file but the
``imports:``.

.. code-block:: yaml

   package:
     name: my-project
     imports:
     - name: hdllint

The lint tools themselves
-------------------------

**No tool is a dependency of this package.** Every backend resolves its
executable from ``PATH`` at run time, and loading the library never requires
one to be installed -- which is what makes ``uses: hdllint.Rtl`` a reasonable
thing to write in a flow file that will be run on machines with different tools
available.

Verilator is the reference backend: open source, and the only one the system
tests can exercise out of the box.

.. code-block:: shell

   # Debian/Ubuntu
   apt-get install verilator

   # or, in an ivpm project, from edapack
   ivpm update -a

The other five (SpyGlass, VC Static, Questa Lint, JasperGold, 0-in) are
commercial tools installed and licensed by their vendors; see
:doc:`guide/backends` for the executable each backend looks for.

From source
-----------

.. code-block:: shell

   git clone https://github.com/dv-flow/dv-flow-libhdllint.git
   cd dv-flow-libhdllint
   pip install --upgrade --pre ivpm
   ivpm update -a -d default-dev

``ivpm update`` assembles ``packages/python`` -- a virtual environment holding
this package's dependencies, pytest, the docs toolchain, and Verilator from
edapack. It is what the tests and the documentation build both run against.

.. code-block:: shell

   ./packages/python/bin/pytest tests
   make -C docs html

Building the documentation needs `sphinx-dv-flow
<https://github.com/dv-flow/sphinx-dv-flow>`_, which generates the task
reference from the flow files. It is **not** on PyPI, so ``pip install
.[docs]`` gets everything except that one; ``ivpm update -a -d default-dev``
gets the whole set. See :doc:`contributing`.

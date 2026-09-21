#****************************************************************************
#* __init__.py
#*
#* Copyright 2025 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may
#* not use this file except in compliance with the License.
#* You may obtain a copy of the License at:
#*
#*   http://www.apache.org/licenses/LICENSE-2.0
#*
#* Unless required by applicable law or agreed to in writing, software
#* distributed under the License is distributed on an "AS IS" BASIS,
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#* See the License for the specific language governing permissions and
#* limitations under the License.
#*
#****************************************************************************
"""dv-flow tasks for running HDL lint tools and reporting their findings."""

# VERSION and SUFFIX are rewritten in place by the shared release workflow
# (dv-flow/dv-flow-release .github/workflows/dv-flow-pybuild.yml), with
#   sed -e 's%SUFFIX=".*"%...%' -e 's%VERSION=".*"%...%'
# so the spacing here is load-bearing: `VERSION = "..."` with spaces around the
# `=` does not match that pattern, and sed does not fail on a pattern that
# matches nothing. A build would then be green and stamp nothing.
VERSION="0.0.1"
SUFFIX=""
__version__ = "%s%s" % (VERSION, SUFFIX)

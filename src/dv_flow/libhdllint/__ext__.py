#****************************************************************************
#* __ext__.py
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
import os

def dvfm_packages():
    hdllint_dir = os.path.dirname(os.path.abspath(__file__))

    return {
        'hdllint': os.path.join(hdllint_dir, "flow.dv"),
        'hdllint.vlt': os.path.join(hdllint_dir, "vlt_flow.dv"),
        'hdllint.spy': os.path.join(hdllint_dir, "spy_flow.dv"),
        'hdllint.z0i': os.path.join(hdllint_dir, "z0i_flow.dv"),
        'hdllint.vcs': os.path.join(hdllint_dir, "vcs_flow.dv"),
        'hdllint.qst': os.path.join(hdllint_dir, "qst_flow.dv"),
        'hdllint.jg': os.path.join(hdllint_dir, "jg_flow.dv"),
    }

# Tool selection is NOT done by rebinding `uses:` the way hdlsim's
# backend_select does. A lint run is normally several tools at once, so the
# family task (hdllint.Rtl) is itself the implementation: it resolves the
# `tools:` list against the capability registry in backends.py, runs each
# selected backend, and merges their findings into one report. See
# docs/tools.rst.

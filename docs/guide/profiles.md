# Profiles

Each backend maps the three standard profiles (`basic`, `default`, `strict`)
to its own flags or goal configuration. Profiles are convenience, not
policy -- they give a project a one-word way to say "how much do we want to
hear" without knowing each tool's flag set.

## Per-tool profile mapping

### Verilator (`vlt`)

| Profile   | Flags                  |
|-----------|------------------------|
| `basic`   | (Verilator's defaults) |
| `default` | `-Wall`                |
| `strict`  | `-Wall -Wpedantic`     |

### SpyGlass (`spy`)

| Profile   | Goal                        |
|-----------|-----------------------------|
| `basic`   | `lint/lint_turbo_rtl`        |
| `default` | `lint/lint_rtl`              |
| `strict`  | `lint/lint_rtl_enhanced`     |

### VC Static (`vcs`)

| Profile   | Goal                        |
|-----------|-----------------------------|
| `basic`   | `lint_turbo_rtl`             |
| `default` | `lint_rtl`                  |
| `strict`  | `lint_rtl_enhanced`          |

Mirrors SpyGlass when running in SpyGlass-compatible mode.

### Questa Lint / AutoCheck (`qst`)

| Profile   | Flags                     |
|-----------|---------------------------|
| `basic`   | `-autocheck_mode quick`   |
| `default` | (default mode)            |
| `strict`  | `-autocheck_mode deep`    |

### JasperGold (`jg`)

| Profile   | Behaviour                           |
|-----------|-------------------------------------|
| `basic`   | Default superlint checks            |
| `default` | Full superlint rule set             |
| `strict`  | All checks, including advisory      |

### 0-in (`z0i`)

| Profile   | Flags                |
|-----------|----------------------|
| `basic`   | (default checks)     |
| `default` | `-full`              |
| `strict`  | `-full -all`         |

# The gate

Whether a lint task fails is an **explicit policy**, not a side effect of a
finding's severity.

```yaml
with:
  fail_on: error     # none | error | warning | any
```

Someone adopting lint on existing code must be able to run it, see
error-severity findings, and still get a zero exit while they work through
them. Otherwise the first thing they do is turn the task off, and then nobody
sees anything.

## The four policies

| `fail_on` | Fails on |
|-----------|----------|
| `none`    | nothing -- report only |
| `error`   | new Error-severity findings **(default)** |
| `warning` | new Warnings and Errors |
| `any`     | any new finding, including Info |

## Only new findings count

Waived and baselined findings have already been accepted. Counting them would
make `fail_on:` a function of the project's history rather than of the change
in front of you -- and a gate that fails on things you did not do gets
disabled.

So the count that the gate uses is:

```
new = findings (after dedup) - waived - baselined
```

## The headline

```
I lint: 0 new findings (137 baselined, 4 waived) [fail_on=error]
```

The one line always states the accepted counts, **even on a pass**. That is
deliberate: `0 new (137 baselined, 4 waived)` is a passing run that still tells
the truth about what is being ignored, and a bare "lint passed" is not.

It also names the policy it was reached under, so a green run and a red run on
the same findings are distinguishable from the log alone.

## Setting it project-wide

`fail_on` and `profile` are package variables on `hdllint`, which is what makes
a whole tree steerable from one place without editing any task:

```shell
dfm run lint -D hdllint.fail_on=warning
dfm run lint -D hdllint.profile=strict
```

A task's own `fail_on:` overrides the project default; the default is written
as `${{ hdllint.fail_on:-error }}`, so a task that does not mention it follows
the project.

## Where the verdict goes

The `hdllint.Report` item carries `passed` and `status`, and deliberately has
no field named `total`. That is what makes `std.TestRunner`'s summary read a
lint task as a single case verdict rather than as a suite roll-up -- a lint
task shows up as one row in a project's test report with no extra wiring. The
count of findings is `findings`.

# Baseline

The feature that decides whether lint gets adopted on existing code or gets
switched off in week two.

Turning a lint tool on over code that predates it produces hundreds of findings
at once. The available responses are: waive them all by hand (nobody does), run
at a severity low enough to be quiet (which is the same as not running it), or
accept the current state and fail only on what is added. Only the third is
real, and that is what a baseline is.

```yaml
with:
  baseline: lint-baseline.json
```

```
$ dfm run lint -D lint.update_baseline=true   # accept today's findings
$ dfm run lint
  I lint: 0 new findings (97 baselined) [fail_on=error]
```

## Baseline or waiver?

They are not interchangeable, and the distinction is the whole reason both
exist.

| | Says | Carries a reason | Expected to |
|---|---|---|---|
| [Waiver](waivers.md) | This is not a bug | **Yes, required** | stay |
| Baseline | This is a bug we have not fixed yet | No | shrink |

A finding is never both: the baseline skips anything already waived, because
the waiver carries a human-written reason and is the more informative of the
two.

## The key ignores line numbers

Baseline entries are keyed on `(tool, rule, file, message-shape)` -- **not**
the line number.

This is the single design decision that makes the feature work. A baseline
keyed on `(file, line)` is invalidated by any edit *above* a finding, so within
a day every entry has drifted and the baseline reports the whole file as new.
The message shape is the message with its variable parts normalized, so a width
warning that changes from `expects 1 bits` to `expects 2 bits` still matches.

## Matching is count-aware

Three baselined `WIDTHTRUNC` in a file and five today is **two** new findings.
A set-membership test would report zero and hide both.

## The baseline is meant to shrink

Findings in the baseline that no longer occur are reported as stale entries --
either fixed, or moved out from under their key. Reporting the count is what
lets a team watch the baseline shrink, and it is the only thing that makes a
baseline a transition rather than a permanent amnesty.

## Updating it

```shell
dfm run lint -D lint.update_baseline=true
```

The run's verdict then describes the *new* baseline, which it says explicitly:
a run that rewrote the baseline has not told you anything about your change.
Treat the updated file as a reviewable artifact -- the diff is the list of
findings someone decided to accept.

## Failure modes, and what they do

| Situation | Behaviour |
|---|---|
| File does not exist | An empty baseline. This is the first run, before one has been established -- not an error. |
| File is unreadable or malformed | **Error.** An unreadable baseline silently becomes "every finding is new", which fails a CI job for the wrong reason and sends someone to look at the wrong thing. |
| File was written by a different baseline version | **Error**, naming the fix: regenerate it with `-D <task>.update_baseline=true`. |

# Testing Canvas imports on a local Canvas

Notes for verifying the QTI (`emit/qti.py`) and Common Cartridge (`emit/cc.py`) emitters against a
real Canvas. Written up because the setup is a pain and the failure mode is opaque.

## The load-bearing gotcha: the default Canvas Docker image can't import QTI

**The stock Canvas Docker container does NOT include the QTI-processing tool.** Without it, importing
a QTI `.zip` (a quiz export) — or a Common Cartridge that contains quizzes — **fails with a generic,
uninformative error**. The import (content migration) just dies; the message tells you nothing.

This is purely a *local environment* problem, not a problem with the emitted package. Confirmed
2026-07-24: the exact same week-6 quiz `.zip`

- **fails** to import into a local Docker Canvas (missing the QTI tool), but
- **imports and randomizes correctly** into **hosted Canvas**.

So if a quiz import fails locally with a generic error, **check the container before suspecting the
package** — and confirm against real/hosted Canvas, which is the actual deployment target.

### Symptom checklist (how to recognise this)
- Generic / non-specific error on import; content migration shows failed or stuck.
- Page (`webcontent`) imports may work while **quiz** imports fail — pages need no QTI tool.
- The same package imports fine in hosted Canvas.

### The fix — install the QTI migration tool manually
The tool has to be cloned into the container's `vendor/` by hand (it is not in the default image).
Verbatim, as used 2026-07-24:

```bash
# Enter the Canvas web container as root
docker compose exec --user root web bash

# Clone Instructure's QTI migration tool into vendor/ under the expected name
cd /usr/src/app/vendor
git clone https://github.com/instructure/QTIMigrationTool.git qti_migration_tool

# Install its Python dependency if the import still errors
apt-get update && apt-get install -y python3-lxml
```

Notes:
- The clone target directory **must** be `qti_migration_tool` (Canvas looks for it by that name).
- After this, retry the QTI/CC import — no Canvas restart was needed in the confirmed run.
- Paths assume the app lives at `/usr/src/app` in the container (the standard canvas-lms dev image).

## Broader local-Canvas setup

> **TODO:** capture the rest of the local Canvas bring-up (image/compose used, first-run steps,
> the delayed-jobs worker, admin/course creation) as it gets nailed down — same goal: never
> rediscover this.

## Related
- `docs/canvasQuizStructure.md` — the QTI/Canvas package format reference (the *what*, vs this *how*).
- `emit/qti.py` / `emit/cc.py` — the emitters this is for.
  Hosted Canvas, not a local container, is the real acceptance gate for both.

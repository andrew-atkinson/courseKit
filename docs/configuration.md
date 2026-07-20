# Configuration

Two layers: **environment** (`.env`, per machine) and **per-course** (`.vtconfig/`, versioned with
the course). Both are optional beyond a model name; everything falls back to a sensible default.

## Environment — `.env`

```bash
MODEL_NAME=unsloth-gemma-4-26b-a4b-it-qat-oq4   # must match an id the provider serves
LOCAL_HOST_URL=http://localhost:1234/v1/
TRANSCRIPTION=/path/to/a/week-3.md              # optional default input
PROVIDER=lm_studio                              # optional; lm_studio | ollama | openai
```

`MODEL_NAME` must match a model id the provider actually serves:

```bash
curl -s http://localhost:1234/v1/models | grep '"id"'
```

### Choosing a provider

Model access goes through `coursekit.providers`, so the endpoint is configuration rather than code.
`PROVIDER` selects it:

| `PROVIDER` | Endpoint | Notes |
|---|---|---|
| `lm_studio` *(default)* | `http://localhost:1234/v1/` | local; what this was built and tested against |
| `ollama` | `http://localhost:11434/v1/` | local |
| `openai` | OpenAI | needs `OPENAI_API_KEY` |

`LOCAL_HOST_URL` overrides the endpoint for whichever provider is selected. Only providers speaking
the OpenAI tool-calling format are implemented today; Anthropic uses a different `tool_use` shape and
would need its own implementation behind the same interface.

**Model choice is a RAM question.** On a 32 GB machine a ~15 GB model is the practical ceiling.
coursekit warns before a run if the configured model won't fit, and turns LM Studio's opaque load
failure into a readable message.

## Per-course — `.vtconfig/`

A course carries its own settings in a `.vtconfig/` folder at its root — the same folder the
videotranscriber uses. coursekit reads from it but never writes to it.

| File | Owner | What it holds |
| --- | --- | --- |
| `context.yaml` | shared | course structure — title, weeks, modules (authored by the transcriber) |
| `quiz.yaml` | quizzes | the quiz generator's settings |
| `page.yaml` | pages | the page generator's settings |
| `domain.md` | shared | the [domain profile](domain-profile.md) — applies to every generator |
| `prompts/<gen>/…md` | shared | per-course prompt overrides |
| `pages/<week>.yaml` | pages | a page's [supplements](pages.md) — references, examples, embeds |

### Generator settings — `quiz.yaml` / `page.yaml`

Each generator reads its own file. Every key is optional.

```yaml
# <course root>/.vtconfig/quiz.yaml   (page.yaml is identical in shape)
model: qwen2.5-32b-instruct   # used when MODEL_NAME is not set in the environment
system_prompt: system         # which prompts/<gen>/<name>.md to use for the rules…
task_prompt: exam             # …and for the brief (default: system / task)
```

`task_prompt: exam` tells the generator to load `exam.md` instead of `task.md` — resolved the same
way as any prompt (the course's own override first, then the shipped file). `MODEL_NAME` in the
environment still wins over `model` here; the file is the per-course default, not an override.

### Prompt overrides

The prompts are files, not strings in code — `prompts/quiz/system.md` (the rules) and
`prompts/quiz/task.md` (the brief), and likewise under `prompts/page/`. Edit them in place to change
behaviour everywhere.

To change them for **one course only**, drop a replacement next to that course's content and coursekit
prefers it, falling back to the shipped file for anything you don't override:

```
<course root>/.vtconfig/prompts/quiz/task.md
<course root>/.vtconfig/prompts/page/system.md
```

Naming a *variant* (`task_prompt: exam` above) and supplying its file (`prompts/quiz/exam.md`) is how
a course keeps several briefs and picks between them.

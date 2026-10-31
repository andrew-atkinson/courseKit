# How coursekit works

How a course's own material becomes Canvas- and Moodle-ready quizzes, pages, and assignments: who provides what, which files live in the course folder, what each `coursekit` command reads and writes, and where a model is involved.
For every command's flags see the [command reference](commands.md); for the internals (the course model, the generator seam, the shared spine) see [agent/architecture.md](../agent/architecture.md).
Verified 30 October 2026 against `main`; every diagram is render-checked with mermaid-cli.

## Reading the diagrams

The key below holds for every coursekit diagram, here and in [agent/architecture.md](../agent/architecture.md).

```mermaid
---
title: Key — for every coursekit diagram
---
flowchart LR
    io[/"a faculty input<br/>or an LMS package"/] --> step["a program step<br/>no model"]
    step -. "dotted: writes" .-> file[("a file in the<br/>course folder")]
    file -- "solid: reads or calls" --> llm["calls a model<br/>LLM or speech"]
    subgraph CMD [" coursekit &lt;command&gt; — what one command runs "]
        maybe["calls a model<br/>only when asked"]
    end
    llm --> maybe

    classDef model fill:#f59e0b33,stroke:#d97706,stroke-width:3px
    classDef maybe fill:#f59e0b14,stroke:#d97706,stroke-width:2px,stroke-dasharray:6 4
    class llm model
    class maybe maybe
```

Amber marks a model call: an LLM, or the transcriber's speech model; the dashed outline is `propose --model`, and `ingest --raw` skips ingest's model pass.

## The system in four layers

Every cylinder marked ② is a plain file in the course folder; every box marked ③ is a coursekit command.

```mermaid
---
title: The system in four layers
---
flowchart TB
    prof(("faculty"))
    layers["<b>the four layers</b><br/>①#nbsp;faculty's#nbsp;material<br/>②#nbsp;a#nbsp;course-folder#nbsp;file<br/>③#nbsp;a#nbsp;coursekit#nbsp;command<br/>④#nbsp;delivery"]:::legend

    subgraph L1 [" ① what faculty provides "]
        direction LR
        video[/"lecture video"/]
        docs[/"readings · PDF<br/>slides · docx"/]
        export[/"prior Canvas export<br/>optional"/]
    end

    vt["videotranscriber<br/>separate tool · media → text"]
    ingest["③ <b>coursekit ingest</b>"]

    ctx[("② <b>.vtconfig/context.yaml</b><br/>course · weeks · modules")]
    wk[("② week-N.md<br/>the unit's text")]
    ycfg[("② <b>.vtconfig/</b> quiz.yaml · page.yaml<br/>style.yaml · supplements<br/>structure.coursekit.yaml")]

    analyze["③ <b>coursekit analyze</b>"]
    cmap[("② <b>.vtconfig/concepts/</b><br/>week-N.yaml · the concept map")]
    generate["③ <b>coursekit generate</b>"]
    ir[("② bank.json · page.json<br/>assignment.json · <b>the IR</b>")]
    emit["③ <b>coursekit emit</b>"]
    census["③ <b>coursekit census</b>"]
    pkg[("② QTI .zip · .imscc · .html<br/>.gift — for Moodle")]
    cen[("② census.json · census.md")]

    llm[["an LLM — local (LM Studio)<br/>or a hosted API"]]
    canvas([" ④ Canvas · delivery "])

    prof --> video & docs & export
    prof -. "edits by hand" .-> ycfg

    video --> vt
    vt -.-> ctx & wk
    export -. "seed · once" .-> ctx
    docs --> ingest
    ingest -.-> wk

    wk --> analyze -.-> cmap
    wk & ctx & ycfg & cmap --> generate
    generate -.-> ir
    ir & ycfg --> emit
    ir & ctx --> census
    emit -.-> pkg
    generate -. ".gift · .html" .-> pkg
    census -.-> cen

    ingest <-- "shape pass" --> llm
    analyze <--> llm
    generate <--> llm

    pkg -- "import" --> canvas

    classDef model fill:#f59e0b33,stroke:#d97706,stroke-width:3px
    classDef legend fill:none,stroke:#888,stroke-width:1px,stroke-dasharray:3 3
    classDef maybe fill:#f59e0b14,stroke:#d97706,stroke-width:2px,stroke-dasharray:6 4
    class vt,ingest,analyze,generate,llm model
```

The pieces fall into four layers.
Two things are worth taking from it: **`.vtconfig/` is just local files in the course's own folder, created by the tools but freely hand-editable by faculty**, and that **coursekit is a set of programs that *drive* an LLM (local or hosted), not a model itself**.

**① What faculty provides.** The raw material for a week: a lecture video, or readings / PDFs / slides (`.docx`, `.odt`), or — for a course already living in Canvas — a prior course export.
Nothing here is coursekit-specific; it is what the instructor already has.

**② The course folder on disk.** A plain local directory — the course's own folder, marked by a `.vtconfig/` subfolder — holding two kinds of file:

- **the `.vtconfig/` reference:** `context.yaml` (course · weeks · modules) and the per-tool config (`quiz.yaml`, `page.yaml`, `style.yaml`, the per-week supplements, prompt overrides). The tools create these, but they are **faculty-editable** — a professor changes a theme, tunes a prompt, adds a supplement link, or fixes a week title by hand in an ordinary text editor. It is a *local reference coursekit both writes and reads*, not a hidden store.
- **the generated files:** `week-N.md` (the unit's text), the `bank.json` / `page.json` / `assignment.json` IR, the emitted artifacts (`.gift`, QTI `.zip`, `.html`, `.imscc`), and the census (`census.json` + `census.md`).

Everything is plain, versionable files in the course folder — never a database. coursekit **writes** here (week text, IR, artifacts) and **reads** here (config); the transcriber writes here too (`context.yaml`, `week-N.md`).
That file boundary is why the two tools stay separate repos with disjoint runtimes — the transcriber keeps `mlx-whisper` and its Apple-Silicon stack; coursekit stays pydantic + stdlib — and neither imports the other.

**③ coursekit — a set of programs.** Four phases run locally: **ingest** (documents → `week-N.md`), **analyze** (week text + the transcriber's `knowledge.json` → the per-week concept map), **generate** (week text → `bank.json`/`page.json`), **emit** (IR → Canvas files).
Two more verbs sit alongside them as the *output-worth* layer: **evaluate** (cold-read the committed IR for correctness, form, and concept-delivery) and **fix** (regenerate each flagged item in place).
Four more need no model: **propose** drafts the declared structure, grading groups, and expectations for the faculty to edit; **census** inventories what exists for every unit (presence, not quality); **check** validates every settings file; **config** reads and writes one setting.
Of the phases, all except `emit` — and ingest's optional shaping pass — **call an LLM, either one you host locally (LM Studio by default) or a hosted API.** coursekit holds no model of its own; it drives whichever provider is configured, which is what lets the whole thing run offline when the LLM is local. (The transcriber is the *media→text* front door; ingest is the *document→text* one — two ways onto the same folder.)

**④ Delivery — Canvas.** The emitted artifacts import into Canvas (a QTI `.zip`, or an `.imscc` course package).
Canvas is a **sink**.
The one loop back is optional and one-time: a *prior* Canvas export can seed `context.yaml` with real module and week titles — a file read, not a live coupling, and `context.yaml` builds fine from a filesystem scan alone.

## Inside coursekit — what each command runs

This opens up layer ③ of the diagram above: each `coursekit …` box there is a labelled boundary here, the IR and packages cylinders split into their actual files, the transcriber reappears as an input, and the LLM shows only as amber highlighting.
Each labelled boundary is one `coursekit` command and what runs inside it; the files sit outside the boundaries because they live in the course folder, where the next command picks them up.
`check` and `config` are left out — they validate and set `.vtconfig/` settings through `settings.py`, and touch nothing in this flow.

```mermaid
---
title: Inside coursekit — what each command runs
---
flowchart TB
    docs[/"PDF · slides · docx"/]
    vt["videotranscriber<br/>separate repo · media → text"]
    ctx[("context.yaml")]
    vt -.-> ctx

    subgraph INGEST [" coursekit ingest · documents → unit text "]
        ing["ingest.py<br/>extract · shape pass"]
    end
    subgraph PROPOSE [" coursekit propose · drafts the declared structure "]
        prop["propose.py<br/>structure · grading<br/>expectations"]
    end
    docs --> ing
    docs --> prop
    ing -.-> md[("week-N.md")]
    vt -.-> md
    prop -.-> ov[("structure.coursekit.yaml")]

    subgraph ANALYZE [" coursekit analyze · unit text → concept map "]
        ana["concept_map.py · consolidate.py"]
    end
    vt -. "knowledge.json" .-> kj[("knowledge.json")] --> ana
    md --> ana -.-> cmap[(".vtconfig/concepts/<br/>week-N.yaml")]

    md & ctx & ov --> model["<b>course.py · the course model</b><br/>units · artifact index · read by every verb below"]

    subgraph GENERATE [" coursekit generate · unit text → IR · --quizzes · --pages · --assignments · --source "]
        disc["discover.py · find_units"]
        pipe["pipeline.py<br/>run_course · run_unit · loop"]
        agen["assignment generator<br/>--assignments · driven by loop"]
        pbuild["page dispatcher · build.py<br/>--function"]
        subgraph SEAM [" Generator seam · generate/base.py "]
            direction LR
            qgen["quiz generator<br/>tools.py → bank.py"]
            pgen["page generator<br/>monolithic teaching page"]
        end
        pmodel["decompose · glossary<br/>their own section loop"]
        pnomodel["overview · recap<br/>from the concept map · no model"]
        gift["gift.py<br/>at finalize"]
    end
    model --> disc
    model -- "--source · targeted quiz" --> pipe
    disc --> pipe & agen
    pipe --> qgen & pbuild
    pbuild --> pgen & pmodel & pnomodel
    cmap --> pbuild & qgen

    qgen -.-> bank[("<b>bank.json</b>")]
    qgen --> gift -.-> gout[/".gift · for Moodle"/]
    pgen & pmodel & pnomodel -.-> page[("<b>page.json</b>")]
    agen -.-> asg[("<b>assignment.json</b>")]

    subgraph EVAL [" coursekit evaluate · fix · audit and repair the IR "]
        direction LR
        ev["evaluate<br/>cold reads · report-only"]
        fx["fix<br/>rewrites flagged items in place"]
    end
    bank & page --> ev --> fx

    subgraph EMIT [" coursekit emit · IR → packages · no model "]
        qti["emit qti · qti.py"]
        render["renderer · render_body"]
        html["emit html · html.py<br/>also run at generation"]
        cc["emit cc · cc.py"]
        crt["emit course · emit assignments<br/>cartridge.py"]
    end
    supp[(".vtconfig/pages/*.yaml · style.yaml<br/>merged in at render")] --> render
    bank --> qti
    page --> render --> html & cc
    qti -- "the same quiz XML" --> crt
    cc -- "the same page HTML" --> crt
    asg --> crt

    qti --> zip[/"QTI .zip"/]
    html --> hout[/".html"/]
    cc --> imscc[/"pages .imscc"/]
    crt --> crs[/"course .imscc"/]
    crt --> aimscc[/"assignments .imscc"/]

    subgraph CENSUS [" coursekit census · what exists for each unit · no model "]
        cen["census.py<br/>through the course model's index"]
    end
    bank & page & asg --> cen -.-> cenout[("census.json · census.md")]

    crs -- "import · the whole course" --> canvas(["<b>Canvas</b>"])
    zip & imscc & aimscc -- "import · one type" --> canvas

    classDef model fill:#f59e0b33,stroke:#d97706,stroke-width:3px
    classDef maybe fill:#f59e0b14,stroke:#d97706,stroke-width:2px,stroke-dasharray:6 4
    class vt,ing,ana,pipe,agen,qgen,pgen,pmodel,ev,fx model
    class prop maybe
```

**The waist.** Each artifact family has one canonical IR — quizzes converge on `bank.json`, pages on `page.json`, assignments on `assignment.json` — and every emitter reads only its IR (qti from `bank.json`; html/cc from `page.json`; the assignment source from `assignment.json`).
GIFT is the exception: `bank.finalize` writes `bank.gift` and `quiz_<seed>.gift` from the in-memory bank at the same moment it writes `bank.json`, so it is regenerated by a run or a `fix`, never re-emitted from the JSON (an `emit gift` that rebuilds it from `bank.json` is planned).
The standalone `.html` is likewise first written at generation, beside `page.json`, and `emit html` re-renders it.
Emitters find those files through the course model's index (`course.ir_files`), never by walking the folder.
Adding a platform costs one emitter, not one converter per input, and re-emitting needs no model: `emit qti`, `emit html`, `emit cc`, `emit assignments`, and `emit course` rebuild from the committed JSON.
`emit course` (`emit/cartridge.py`) sits one level up — it assembles all three IRs into one Common Cartridge of week modules, via a `CartridgeSource` per content type (pages, quizzes, assignments; discussions next), so a new content type is one source, not a new assembler.
It reuses the standalone emitters rather than formatting anything itself: a quiz's questions are `qti.emit_assessment`'s XML (only the packaging differs), a page is `cc.render_page`'s HTML (byte-identical to the pages-only `.imscc`), and an assignment's body goes through the same `render_body`.
`emit assignments` is the same assembler with only the assignment source.
So the course `.imscc` is the whole course in one import, and the QTI `.zip`, the pages `.imscc`, and the assignments `.imscc` are the alternative of importing one type at a time.
A Canvas **API** emitter is the gated third delivery path — it will read the same IRs, so it is one more emitter, not a new pipeline.

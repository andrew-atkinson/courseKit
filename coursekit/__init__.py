"""coursekit — the shared spine for AI-assisted course building.

Generators (quizzes, pages, assignments, rubrics) sit on top of this. It holds what they all
need and none of them should re-implement: model access, prompts, course configuration.

It imports nothing from any generator. That is deliberate — it currently lives inside the
quizbot repo for convenience, but nothing depends on that, so extracting it to its own package
when the transcriber migrates is a move, not a refactor.
"""

__version__ = "0.1.0"

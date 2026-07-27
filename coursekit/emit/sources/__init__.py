"""Cartridge sources — one module per Canvas content type.

Each source turns a course's committed artifacts into `CartridgeItem`s the assembler drops into week
modules. `pages` and `quizzes` exist today; a new content type (discussions, assignments + rubrics,
files) is a new module here plus one line in `cartridge._default_sources`.
"""

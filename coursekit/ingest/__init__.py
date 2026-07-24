"""Document ingest: turn readings/slides into the same `week-N.md` the generators consume.

A light, local, in-repo ingest adapter — the text counterpart to the (separate, heavy) video
transcriber. It reads PDFs, Word/OpenDocument files, slide decks, and plain text, optionally reshapes
them with the local model, and writes `output/week-N.md`, which `discover.find_units` then picks up
unchanged. No network, no video stack.
"""

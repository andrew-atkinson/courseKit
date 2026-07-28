# Synthetic course — planted flaws (the answer key)

A controlled test bed for `coursekit evaluate`. The transcript in `output/week-1.md` is the ONLY
material the critic may trust. Run:

    uv run coursekit evaluate examples/synthetic-course

A good critic should PASS c1 and FLAG c2–c5:

| Q  | planted flaw        | why it should flag |
|----|---------------------|--------------------|
| c1 | (none — good)       | in scope, self-contained, correct — should PASS |
| c2 | out of scope        | p5.FFT is never taught this week |
| c3 | missing context     | asks "why is manual repetition problematic?" with no scenario |
| c4 | garbled syntax      | `for.let i >== inc()` is not valid code |
| c5 | wrong answer        | marks "2"; after `i < 3` the loop leaves i = 3 |

The page in `pages/week-1/page.json` plants a "Fourier analysis" section for the later
pages-evaluator increment (out of scope for a loops week).

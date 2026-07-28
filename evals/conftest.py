"""Load the project's .env for the eval suite, so MODEL_NAME / LOCAL_HOST_URL / PROVIDER are picked
up exactly as the `coursekit` command picks them up. The offline `tests/` suite deliberately needs no
model and no env, so this lives only under `evals/`."""

from dotenv import load_dotenv

load_dotenv(override=True)

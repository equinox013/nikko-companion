"""
run_adp_a_v2_pipeline.py
------------------------
Executes Step 18 (ADP-A v2 data preparation) then Step 19 (ADP-A v2 QLoRA
training) in sequence. When Step 18 finishes, Step 19 is kicked off
automatically. If Step 18 fails or produces too few records, the pipeline
aborts before touching Step 19.

Usage (from repo root, nikko env active):
    conda activate nikko
    python notebooks/run_adp_a_v2_pipeline.py

Each notebook is executed in-place — cell outputs are written back into the
source .ipynb files, exactly as if the cells were run manually in Jupyter.
Cell outputs are streamed live to the terminal as each cell finishes, and the
notebook is saved to disk after every cell so progress is never lost.
Progress is also written to a timestamped log file in notebooks/.
"""

import sys
import time
import pathlib
import logging
import textwrap
from datetime import datetime

import nbformat
from nbconvert.preprocessors import ExecutePreprocessor, CellExecutionError

# ── Paths ──────────────────────────────────────────────────────────────────────
NOTEBOOKS = pathlib.Path(__file__).parent.resolve()
REPO      = NOTEBOOKS.parent

NB18 = NOTEBOOKS / "step18_adp_a_v2_data_preparation.ipynb"
NB19 = NOTEBOOKS / "step19_adp_a_v2_training.ipynb"

# Outputs written back into source notebooks (in-place), matching manual Jupyter execution.
# A timestamped log file in notebooks/ captures all stdout for post-run review.
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT18 = NB18   # nbconvert overwrites source notebook with cell outputs in-place
OUT19 = NB19   # same — after the run, opening either notebook shows all outputs

# Gate: Step 19 refuses to start unless this file exists with enough records
# (produced by Step 18 in-place execution above)
DATA_FILE  = REPO / "finetuning" / "adp_a_empathy" / "data" / "adp_a_v2_train.jsonl"
ADAPTER_V2 = REPO / "finetuning" / "adp_a_empathy" / "adp_a_v2_final"

MIN_RECORDS = 500   # abort threshold — corpus below this is unusable for training
LOG_FILE    = NOTEBOOKS / f"pipeline_{STAMP}.log"

# ── Logging — both file and stdout ────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ── Live-streaming notebook preprocessor ──────────────────────────────────────
class LiveExecutePreprocessor(ExecutePreprocessor):
    """
    Subclass of ExecutePreprocessor that:
      - Prints a header line before each code cell executes
      - Streams every output line to the terminal as cells finish
      - Saves the notebook to disk after each cell so outputs are never lost
        mid-run (you can open the .ipynb in Jupyter at any time and see
        progress exactly as if you had run cells manually)

    Non-code cells (markdown, raw) are skipped silently — same as Jupyter.
    """

    def __init__(self, nb_path: pathlib.Path, total_cells: int, **kwargs):
        super().__init__(**kwargs)
        self.nb_path     = nb_path      # path to write after every cell
        self.total_cells = total_cells  # for the [N / M] counter
        self._nb_ref     = None         # set by run_notebook before preprocess()

    # ── Per-cell hook ──────────────────────────────────────────────────────────
    def preprocess_cell(self, cell, resources, cell_index):
        if cell.cell_type != "code" or not cell.source.strip():
            return cell, resources

        # ── Header ────────────────────────────────────────────────────────────
        preview = cell.source.splitlines()[0][:72].strip()
        ellipsis = "…" if len(cell.source.splitlines()[0]) > 72 else ""
        print(
            f"\n{'─'*68}\n"
            f"[Cell {cell_index + 1} / {self.total_cells}]  {preview}{ellipsis}\n"
            f"  Executing...",
            flush=True,
        )
        t0 = time.time()

        # ── Execute ────────────────────────────────────────────────────────────
        cell, resources = super().preprocess_cell(cell, resources, cell_index)

        elapsed = time.time() - t0

        # ── Stream outputs ─────────────────────────────────────────────────────
        outputs = cell.get("outputs", [])
        if outputs:
            print("  Output:")
            for output in outputs:
                otype = output.get("output_type", "")

                if otype == "stream":
                    # stdout / stderr lines from the cell
                    text = "".join(output.get("text", []))
                    for line in text.rstrip().splitlines():
                        print(f"  │ {line}")

                elif otype in ("execute_result", "display_data"):
                    # repr() / rich display output — cap at 10 lines
                    data = output.get("data", {})
                    raw  = data.get("text/plain", "")
                    text = "".join(raw) if isinstance(raw, list) else raw
                    lines = text.rstrip().splitlines()
                    for line in lines[:10]:
                        print(f"  │ {line}")
                    if len(lines) > 10:
                        print(f"  │ … ({len(lines) - 10} more lines)")

                elif otype == "error":
                    # Surface the error name + message; full traceback is in the nb
                    print(f"  │ ✗ {output.get('ename', 'Error')}: {output.get('evalue', '')}")
        else:
            print("  (no output)")

        # ── Save notebook in-place after this cell ─────────────────────────────
        # Manually update nb.cells so the current cell's outputs are included
        # before writing — nbformat's parent loop only updates nb.cells AFTER
        # preprocess_cell returns, so we patch it here ourselves.
        if self._nb_ref is not None:
            self._nb_ref.cells[cell_index] = cell
            nbformat.write(self._nb_ref, str(self.nb_path))
            print(
                f"  ✓ Cell done ({elapsed:.1f}s) — outputs saved to {self.nb_path.name}",
                flush=True,
            )

        return cell, resources


# ── Notebook runner ────────────────────────────────────────────────────────────
def run_notebook(nb_in: pathlib.Path, nb_out: pathlib.Path, label: str) -> bool:
    """
    Execute nb_in in-place using LiveExecutePreprocessor.
    Streams cell outputs to terminal and saves the notebook after every cell.
    Returns True on success, False on failure (partial outputs still saved).
    """
    log.info("=" * 68)
    log.info(f"  {label}")
    log.info(f"  Notebook : {nb_in.name}")
    log.info("=" * 68)

    # Load the notebook
    nb = nbformat.read(str(nb_in), as_version=4)

    # Count code cells only — gives an accurate [N / M] counter
    total_code = sum(1 for c in nb.cells if c.cell_type == "code" and c.source.strip())
    log.info(f"  Code cells to execute: {total_code}")
    log.info("")

    ep = LiveExecutePreprocessor(
        nb_path=nb_out,
        total_cells=len(nb.cells),   # index is over all cells, not just code
        timeout=-1,
        kernel_name="python3",
    )
    ep._nb_ref = nb

    t_start = time.time()
    failed  = False

    try:
        ep.preprocess(nb, {"metadata": {"path": str(nb_in.parent)}})
    except CellExecutionError as exc:
        log.error(f"\n  ✗ Cell raised an exception — pipeline will abort after saving.")
        log.error(f"    {exc.ename}: {exc.evalue}")
        failed = True
    except Exception as exc:
        log.error(f"\n  ✗ Unexpected error: {exc}")
        failed = True
    finally:
        # Always do a final save so partial outputs are not lost
        nbformat.write(nb, str(nb_out))
        elapsed = (time.time() - t_start) / 60
        status  = "FAILED" if failed else "complete"
        log.info(f"\n  {label} {status} in {elapsed:.1f} min")
        log.info(f"  Notebook saved → {nb_out.name}")

    return not failed


# ── Step 18 output gate ────────────────────────────────────────────────────────
def check_step18_output() -> int:
    """
    Verify Step 18 produced a usable jsonl file.
    Returns the record count, or 0 on failure.
    """
    if not DATA_FILE.exists():
        log.error(f"Output file not found: {DATA_FILE}")
        return 0
    lines = [l for l in DATA_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    n = len(lines)
    log.info(f"  Step 18 output : {n} records at {DATA_FILE.name}")
    return n


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    log.info("")
    log.info("ADP-A v2 pipeline starting")
    log.info(f"  Log : {LOG_FILE.name}")
    log.info(f"  Repo: {REPO}")
    log.info("")

    # ── Preflight checks ───────────────────────────────────────────────────────
    for nb in (NB18, NB19):
        if not nb.exists():
            log.error(f"Notebook not found: {nb}")
            sys.exit(1)

    adp_c_v2 = REPO / "finetuning" / "adp_c_evaluator" / "adp_c_v2_final"
    if not adp_c_v2.exists():
        log.error(f"ADP-C v2 adapter missing: {adp_c_v2}")
        log.error("Run Step 17 first.")
        sys.exit(1)

    log.info("Preflight OK — both notebooks found, ADP-C v2 adapter present.")
    log.info("")

    # ── Step 18 — Data preparation ─────────────────────────────────────────────
    ok18 = run_notebook(NB18, OUT18, "STEP 18 — ADP-A v2 Data Preparation")
    if not ok18:
        log.error("Pipeline aborted at Step 18.")
        sys.exit(1)

    n_records = check_step18_output()
    if n_records < MIN_RECORDS:
        log.error(
            f"Record count {n_records} is below minimum threshold ({MIN_RECORDS}). "
            "Inspect Step 18 notebook and increase candidate caps before rerunning."
        )
        sys.exit(1)

    log.info("")

    # ── Step 19 — QLoRA training ───────────────────────────────────────────────
    ok19 = run_notebook(NB19, OUT19, "STEP 19 — ADP-A v2 QLoRA Training")
    if not ok19:
        log.error("Pipeline aborted at Step 19.")
        sys.exit(1)

    # ── Summary ────────────────────────────────────────────────────────────────
    log.info("")
    log.info("=" * 68)
    log.info("  Pipeline complete.")
    log.info(f"  Records assembled  : {n_records}")
    log.info(f"  Step 18 notebook   : {NB18.name}  (outputs written in-place)")
    log.info(f"  Step 19 notebook   : {NB19.name}  (outputs written in-place)")
    log.info(f"  Adapter location   : {ADAPTER_V2}")
    log.info("  Next: open step19_adp_a_v2_training.ipynb Section 8 to review smoke test results.")
    log.info("=" * 68)
    log.info("")


if __name__ == "__main__":
    main()

@echo off
REM ── ADP-A v2 Pipeline Launcher ───────────────────────────────────────────────
REM Run from the repo root. Activates the nikko conda env and executes
REM Step 18 (data prep) → Step 19 (QLoRA training) in sequence.
REM Progress is logged to notebooks/pipeline_<timestamp>.log

echo.
echo  ADP-A v2 Pipeline
echo  =================
echo  Step 18 (data prep) then Step 19 (training) will run unattended.
echo  Estimated total runtime: 8-12 hours on RTX 3070.
echo  Log file will appear in notebooks/ when the run starts.
echo.

call conda activate nikko
if errorlevel 1 (
    echo ERROR: Failed to activate conda environment "nikko"
    pause
    exit /b 1
)

python notebooks\run_adp_a_v2_pipeline.py
if errorlevel 1 (
    echo.
    echo  Pipeline exited with errors. Check the log file in notebooks/.
    pause
    exit /b 1
)

echo.
echo  Done. Press any key to close.
pause

@echo off
setlocal

cd /d "%~dp0backend"
if errorlevel 1 goto :directory_error

if not exist "evals\config\task-benchmark.yaml" goto :config_error

where uv >nul 2>nul
if errorlevel 1 goto :uv_error

set "RUNS_DIR=.runtime\evaluation\task-benchmark\runs"
set "PREVIOUS_RUN="
if exist "%RUNS_DIR%" (
    for /f "delims=" %%D in ('dir /b /ad /o-d "%RUNS_DIR%" 2^>nul') do (
        set "PREVIOUS_RUN=%%D"
        goto :previous_run_found
    )
)

:previous_run_found
echo.
echo This runs the real DeepSeek task benchmark (2 cases).
echo It sends live model requests and may incur provider charges.
echo It does not create or replace a baseline.
echo.

uv run python -m app.evaluation.real_model --config evals/config/task-benchmark.yaml
set "RUN_EXIT=%ERRORLEVEL%"

set "LATEST_RUN="
if exist "%RUNS_DIR%" (
    for /f "delims=" %%D in ('dir /b /ad /o-d "%RUNS_DIR%" 2^>nul') do (
        set "LATEST_RUN=%%D"
        goto :latest_run_found
    )
)

:latest_run_found
if not defined LATEST_RUN goto :finish
if "%LATEST_RUN%"=="%PREVIOUS_RUN%" goto :finish

set "REPORT_PATH=%CD%\%RUNS_DIR%\%LATEST_RUN%\report.json"
if not exist "%REPORT_PATH%" goto :finish

echo.
echo Opening this run's report:
echo %REPORT_PATH%
start "" "%REPORT_PATH%"

:finish
echo.
if "%RUN_EXIT%"=="0" (
    echo Evaluation command completed successfully.
) else (
    echo Evaluation command exited with code %RUN_EXIT%.
    echo A failed benchmark can still have a report; inspect it before changing the baseline.
)
echo.
pause
exit /b %RUN_EXIT%

:directory_error
echo Could not enter the backend directory.
set "RUN_EXIT=2"
goto :finish

:config_error
echo Could not find evals\config\task-benchmark.yaml.
set "RUN_EXIT=2"
goto :finish

:uv_error
echo Could not find uv on PATH. Install uv or open a terminal where uv is available.
set "RUN_EXIT=127"
goto :finish

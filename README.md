# Research priority study

Project folders:

- `code/`: Python scripts and a local pilot notebook (excluded from Git).
- `config/api_keys.json`: private API keys, excluded by `.gitignore`.
- `data/pilot/<timestamp>/`: local pilot results (excluded from Git).
- `data/official_v1/`: official script schedule and run results.

`.gitignore` excludes private API keys (`config/api_keys.json`), pilot outputs
(`data/pilot/`), the local notebook (`code/run_test_study.ipynb`), Python caches
(`__pycache__/` and `*.py[cod]`), and macOS `.DS_Store` files. Official collection
files under `data/official_v1/` are not ignored.

Install `openai`, `anthropic`, and `ipykernel` in your Python environment.
Enter `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` in `config/api_keys.json`.
On a fresh checkout, copy `config/api_keys.example.json` there first.

If you have the local notebook (it is not included in a fresh checkout),
for two pilot runs, open `code/run_test_study.ipynb` and select the `user_pr`
Python kernel. Run imports, setup, pilot folder, and both research cells.
The notebook runs one neutral research prompt per model using the exact request
functions and parameters in run_study.py. It includes no connection-test calls.
Pilot requests are paid API calls.
The notebook saves requests, raw responses, and reports under `data/pilot/`.

For the batch pilot, run:

```sh
python3 code/run_study.py
```

The script defaults to pilot mode and asks for `RUN PILOT` before submitting paid
batch requests. It runs the resilience prompt once per provider and saves each
collection under `data/pilot/batch_pilot_<UTC timestamp>/`, alongside the earlier
notebook pilots. Its purpose is to validate batch collection and Claude
continuations; the earlier notebook pilots used the neutral prompt for inspecting
individual model responses. The purpose and collection type are recorded in
`collection.json`.

Each batch collection contains `runs/` with requests, raw responses, metadata,
`final_report.txt`, and `usage.json`, plus provider batch records. OpenAI and Claude
use batch APIs; completion can take hours. Claude supports up to nine continuation
rounds. Existing pilots are preserved, and each invocation gets a new timestamp.
API-reported usage is saved; exact charges are available in provider billing consoles.

For the full collection, set `RUN_MODE = "official"` in `code/run_study.py`.
This schedules three conditions × six repetitions × two providers (36 runs),
asks for `RUN COLLECTION`, and saves to `data/official_v1/`. The script refuses
to overwrite an existing collection directory. Environment variables can also
supply API keys.

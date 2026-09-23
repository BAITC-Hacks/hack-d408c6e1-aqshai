# Rules for Codex in this project

- The team are **not programmers** (first hackathon, two people, one Windows laptop and one Mac). After every task, explain in 2–4 simple sentences what you did and exactly how to check it (which command, which tab, what to click).
- **Read SPEC.md and INTERFACE.md before every task.** Do only the step you are asked for. Don't add features that are not in SPEC.md.
- **File ownership (INTERFACE.md section 4): only create or edit the files that belong to the person you are working for.** Person 1: engine.py, app.py, README.md. Person 2: tab_checks.py, tab_analytics.py, tab_ai.py, export_manager_sheet.py, tests/, engine_stub.py, app_preview.py. If the other person's file needs a change, write it in NOTES_FOR_TEAMMATE.md instead.
- Python setup: on **Windows** use the global `python` / `pip` (no venv). On **Mac** use `./venv` (create it with `python3 -m venv venv` if missing, then `source venv/bin/activate`), because global pip is blocked there. Install packages with `pip install -r requirements.txt`. Always give me commands for the laptop I'm on.
- Quantities must be **deterministic** formulas. Never let an LLM decide numbers. The LLM (AI tab) only explains and chats.
- UI text, reasons and Excel exports are in **Russian**.
- The case data is in `data/` and IS part of the repo (the repo is private; judges need it to run the app). Never modify those files; write any outputs to downloads or `output/`.
- After each change: run `pytest -q` (when tests exist) and a quick smoke check (import the modules, run `build_plan` once). Make sure `streamlit run app.py` (or `app_preview.py`) starts without errors. Fix errors before you finish.
- Speed: cache parsed Excel to `data/cache/*.parquet`; the app must open in under 60 s the first time and in a few seconds after.
- **Git: do not run git commit / push / pull.** The team commits and pushes with GitHub Desktop. At the end of each task, write a one-line commit message I can paste.
- Never commit or print `.env` or the OpenAI API key. `.gitignore` must keep ignoring: venv/, .env, __pycache__/, data/cache/, output/.
- Never send anything to suppliers (no emails, no APIs). Orders are only downloaded after human approval.
- If the repo contains files from the organizers (README template, instructions), keep them and follow them; tell me what they say.
- Keep code simple and readable, with short comments explaining the business logic.

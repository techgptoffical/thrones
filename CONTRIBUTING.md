# Contributing to Thrones

Thank you for helping. A few rules keep the project honest and maintainable.

## Ground rules

1. **No fake functionality.** Every control in the UI must do what it says. If a feature isn't ready, label it "Not available" rather than shipping a dead button.
2. **No invented numbers.** Performance or quality figures in code, docs or the UI must come from a measurement on stated hardware (`evals/run_bench.py` or the app's own metrics).
3. **Model honesty.** Thrones is the application. Do not describe prompts, retrieval or tools as training, and do not describe a base model as a Thrones model.
4. **Local-first.** New network access must be user-initiated, visible in the UI, blocked by Offline mode, and listed in Settings → Privacy and `SECURITY.md`.
5. **Licences.** Any new dependency, model, dataset, font or asset must have a compatible licence recorded in `THIRD_PARTY_NOTICES.md`. Training data must follow `docs/TRAINING_PLAN.md` §3 — in particular, no outputs from models whose terms forbid training competing models.

## Development setup

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
cd backend; ..\.venv\Scripts\python -m thrones --no-browser   # API + built UI on :8765
cd frontend; npm run dev                                       # live-reload UI on :5173 (proxies /api)
```

## Before opening a pull request

```powershell
.venv\Scripts\python -m pytest backend\tests -q
cd frontend; npm run build
.venv\Scripts\python scripts\e2e_check.py --skip-web   # with the app running and a model installed
```

Describe what you tested and on what hardware. Screenshots for UI changes, in both light and dark themes.

## Code layout

See `docs/ARCHITECTURE.md`. Keep modules small and focused; prompts live in `backend/thrones/reasoning/prompts.py`; design tokens in `frontend/src/styles/tokens.css`.

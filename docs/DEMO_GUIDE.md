# Thrones 1.0 — demo guide for the TECH GPT video

Everything below is real and was verified on the reference PC (RTX 5060 Ti 16 GB, i3-10105F, 16 GB RAM). Timings are what we measured; yours will vary a little.

## Before recording (5 minutes)

1. Close games, browsers with many tabs and other GPU apps. Thrones uses about **6 GB VRAM** and the engine about **8 GB of RAM working set** with the 9B model.
2. Double-click `Thrones.bat`. The browser opens at `http://127.0.0.1:8765`.
3. Settings → Models & hardware: confirm **Qwen3.5 9B** is selected and press **Load Qwen3.5 9B now** so the first answer on camera doesn't include the ~8–12 s load.
4. Settings → General: pick the theme you want on camera.
5. Optional: delete test conversations (Settings → Privacy & data → Delete all…).

## Shot list

### 1. The app opens (≈ 20 s)
Show the welcome screen: the Thrones mark, the greeting, "Running Qwen3.5 9B on this PC". Point to the sidebar footer: green dot, model name, context size, "local".

**Say:** Thrones is our app; the brain is Qwen3.5 9B, an open model by Alibaba's Qwen team, running on this GPU. We haven't trained our own model yet — that's the next phase.

### 2. Local answer, internet unplugged (≈ 60 s)
1. Unplug the network cable / turn off Wi-Fi. Within ~20 s the top bar shows **No internet**.
2. Mode: **Fast**. Ask: *"Mujhe Hinglish mein samjhao ki GPU aur CPU mein kya fark hota hai."*
3. It streams at roughly **50 tokens/second**. Click the grey line under the answer to open the **measured metrics** (speed, first-token time, peak VRAM).

### 3. Real reasoning with tools (≈ 90 s)
Mode: **Think**. Ask:
*"A loan of ₹8,50,000 at 9.5% annual interest is repaid monthly over 7 years. What is the EMI and the total interest paid? Show the working."*

While it runs, show the **Activity** panel: the plan, each **Calculating** step with the exact expression and result, then **Checking the answer**. Correct result: **EMI ₹13,892.38, total interest ₹3,16,960.29** (≈ 55 s on the reference PC).

Optional contrast: ask Fast mode *"Compute 48213 × 9917 − 1234567."* In our benchmark the 9B, answering directly without tools, ran out of tokens doing long multiplication by hand. Think mode answers it exactly (476,893,754) with the calculator.

### 4. Deep Research after reconnecting (≈ 2 min)
1. Reconnect. The "No internet" chip disappears.
2. Mode: **Deep Research**. Ask something current, e.g. *"What are the most capable open-weight language models that run on a 16 GB GPU right now, and how do they compare?"*
3. Show the steps: planning queries → searching → reading N pages (failed pages are listed honestly) → extracting evidence → writing.
4. Hover a citation number to show its source card; click one to open the real page. Scroll to the **Sources** grid with dates.

Typical run: 8 pages read, ~100–110 s.

### 5. Comparison against a baseline chatbot
Use the same prompt in both, recorded side by side:
- a hard multi-step maths prompt from `evals/items.py` (`hm-*` items), or the EMI problem;
- a current-events question (baseline without browsing vs. Thrones Deep Research with citations).

Say clearly which baseline you used and that results are from single runs. For our measured comparisons of the raw model vs. Thrones Think mode on the same 65 questions, see `docs/MODEL_RESEARCH.md`.

### 6. Hardware and performance (≈ 30 s)
Settings → **Models & hardware**: live GPU/VRAM, CPU, RAM; engine status with load time and VRAM taken; the model list with licences and compatibility labels. Mention the profiles (Lite / Balanced / High).

## Things not to claim on camera

- That Thrones is a new model or was trained by us (it isn't, yet).
- That it matches ChatGPT or Claude in general intelligence. A 9B local model makes more mistakes; Think and Deep Research help on specific kinds of tasks.
- Speeds you didn't measure on your own PC.

## If something goes wrong

| Symptom | Fix |
|---|---|
| "Cannot reach the Thrones engine" | The `Thrones.bat` window was closed. Start it again. |
| First answer is slow | The model was loading. Load it in Settings beforehand. |
| Deep Research: "search returned no results" | DuckDuckGo rate limit. Wait a minute, or switch provider in Settings → Research. |
| Model won't load | Close other GPU apps; or pick a smaller context in Settings → Models & hardware. |

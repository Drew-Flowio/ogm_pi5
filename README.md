# ogm_pi5 — Offgrid Minds Pi 5 Field Device

Offline AI field instrument for Raspberry Pi 5: camera → vision → voice → brain →
spoken answer. No cloud at runtime.

This repo is the **software home** for the Pi 5 Offgrid Minds touch UI, the
Insight desktop dev app, supporting PoCs, iOS companion work, and internal OGM
platform tooling.

## Repository layout

| Path | Purpose |
|---|---|
| [`insight_desktop/`](insight_desktop/) | **Primary Pi 5 UI** — PySide6 touch app (`config.pi.yaml`) + macOS desktop dev app |
| [`poc/`](poc/) | Original terminal PoCs (vision, voice, brain pipeline) — shared model paths |
| [`docs/`](docs/) | Hardware, PoC, product specs — see [docs/README.md](docs/README.md) |
| [`insight_ios/`](insight_ios/) | Swift/iOS companion app (separate target) |
| [`internal_tools/`](internal_tools/) | OGM Foundry, ACP, milestone tooling, canonical control center |
| [`control_center/`](control_center/) | Legacy control-center snapshot — prefer `internal_tools/ogm_control_center/` |
| [`models/`](models/) | Downloaded weights (gitignored) |
| [`vendor/`](vendor/) | llama.cpp / whisper.cpp builds (gitignored) |

## Pi 5 touch UI (Offgrid Minds)

```bash
cd ~/Desktop/ogm_pi5
source .venv/bin/activate
python insight_desktop/app/main.py --config insight_desktop/config/config.pi.yaml
```

Modes: **Scan** (camera-first) · **Talk** (live voice) · **Chat** (full-screen keyboard).

## Desktop dev app

```bash
python insight_desktop/app/main.py
```

See [`insight_desktop/README.md`](insight_desktop/README.md) for models, packaging, and mock mode.

## Stack (offline)

- **Brain:** Phi-3.5-mini-instruct Q4_K_M (MIT) via llama.cpp
- **Vision:** SmolVLM-500M via llama-mtmd-cli
- **STT:** whisper.cpp base.en
- **TTS:** Piper (Ryan voice on desktop/Pi configs)

## Quickstart (terminal PoC)

```bash
bash poc/setup_mac.sh
source .venv/bin/activate
python poc/run_llm.py --model models/Phi-3.5-mini-instruct-Q4_K_M.gguf --threads 8
```

Full voice loop: see [`docs/07-voice-poc.md`](docs/07-voice-poc.md).

## Internal tools

| Tool | Path |
|---|---|
| OGM Foundry | `internal_tools/ogm_foundry/` |
| Agent Control Center | `internal_tools/ogm_control_center/` |
| Agent Communication Protocol | `internal_tools/ogm_acp/` |

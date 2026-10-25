# Sentinel Phoenix — Python reference version

This archive prepares the existing Python source for review and migration to Java.
It is NOT a completed Java version or a verified fresh installation.

## Environment
Original environment reported by the owner: Ubuntu, Python 3.14.4.
requirements.txt records that environment; installation availability and compatibility
on a new machine have not been verified.

## Structure
- core/: application modules, preserved without behavioral changes.
- scripts/start_sentinel.sh: portable launcher using the project-local .venv.
- ui/incident_replay/: replay interface and bundled Three.js file.

## Setup prerequisites
Create .venv in this directory and install requirements.txt using that environment.
The original installation also uses system audio/TTS dependencies (including espeak-ng),
GUI/camera/microphone access and, for the LLM conversation module, a separate Ollama
service at localhost:11434 with qwen3:4b. pip requirements do not install these services.

Models are intentionally absent. Restore independently in the expected locations:
- models/face/face_recognition_sface_2021dec.onnx
- models/face/face_detection_yunet_2026may.onnx
- models/wake/vosk-model-small-en-us-0.15/ (complete model tree)
The owner reports approximately 38 MiB face models and 68 MiB wake models.
Verify model origins, licenses and exact paths before distribution. Other resources,
including Whisper model caches, may also be needed depending on the enabled features.

Personal data, facial galleries, PIN records, conversations, logs, recovery snapshots
and learned state are absent. Enrollment and initial-data creation still need checking
on a clean installation. Do not copy the owner's identity data into a shared repository.

## Launch (after prerequisites are ready)
bash scripts/start_sentinel.sh
Logs: data/logs/sentinel_autostart.log
The launcher starts core.honeypot_service and core.sentinel_runtime.
The honeypot binds to 0.0.0.0:2222: use an authorized isolated lab network.
core.main.main() is not called by this launch path, so its dashboard startup,
integrity preflight and lifecycle startup are not run through that function.

## Validation performed
All 69 Python source files parse successfully. Explicit absolute core module imports
resolve to files in the archive. These are static checks, not end-to-end validation.
Audio, camera, GUI, models, external services and clean-data startup remain untested.
No comprehensive secrets audit or third-party licensing review has been completed.

## Java migration
Keep the Python original unchanged. Inventory behavior and port the network/analysis/
event pipeline first, then the interfaces, identity, voice and replay components.
Validate equivalent scenarios for each component; do not mark a capability migrated
until its Java behavior has been demonstrated. No Java implementation is included.

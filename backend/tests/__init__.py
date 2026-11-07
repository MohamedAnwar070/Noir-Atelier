"""Tests are hermetic: never call a paid model, whatever the developer's .env says.

Runs before any test module imports backend.app.config (which reads .env with
setdefault, so these explicit values win). The LLM path is exercised with a
scripted fake model instead (agents/tests/test_assistant_runtime.py).
"""

import os

os.environ["USE_LIVE_LLM"] = "0"
os.environ["AGENT_RUNTIME"] = "llm"

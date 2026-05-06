"""
Root-level entry point required by Hugging Face Spaces.

HF Spaces looks for app.py at the repo root. This file just
imports and launches the Gradio app defined in ui/app.py.
"""

from ui.app import build_app

app = build_app()

if __name__ == "__main__":
    app.launch(server_name="0.0.0.0", server_port=7860)

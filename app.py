"""
Root-level entry point required by Hugging Face Spaces.

HF Spaces looks for app.py at the repo root. This file just
imports and launches the Gradio app defined in ui/app.py.
"""

# Patch huggingface_hub before Gradio loads — newer versions removed HfFolder
# but some Gradio builds still import it. This shim restores the class.
try:
    from huggingface_hub import HfFolder  # noqa: F401
except ImportError:
    import huggingface_hub as _hfh

    class _HfFolder:
        _token = None

        @classmethod
        def get_token(cls):
            return cls._token

        @classmethod
        def save_token(cls, token):
            cls._token = token

        @classmethod
        def delete_token(cls):
            cls._token = None

    _hfh.HfFolder = _HfFolder

from ui.app import build_app

app = build_app()

if __name__ == "__main__":
    app.launch(server_name="0.0.0.0", server_port=7860)

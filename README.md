# MyAgent

An extensible local coding agent. The initial provider is MiniMax through its Anthropic-compatible API.

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

Copy `.env.example` to `.env` and set `MINIMAX_API_KEY` before using a real model.

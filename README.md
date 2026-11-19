# Alethic Agent

A small terminal agent harness for the Alethic-300M language model. It runs the model on your own computer and lets it
read, write and edit files in one folder, run safe shell commands, and search Wikipedia. It asks before anything risky.

- Model weights: https://huggingface.co/bekhruzsuleyman/alethic-300m (SFT-3c is in `sft/sft3c/`)
- Training code, data tools and results: https://github.com/bekhruzsuleyman/alethic-300m

## What is in here

| Path | What it is |
| --- | --- |
| `src/alethic/agent` | the harness: terminal UI, tool loop, safe-command policy, shell emulation, search |
| `src/alethic/model` | the model code the harness loads |
| `tests/` | the harness tests |
| `deploy/31_agent_sft3c.bat` | Windows double-click launcher (downloads the weights on the first run) |
| `deploy/21_build_agent_exe.bat`, `deploy/setup_installer.cs` | builds a Windows installer |

## How it works

The model writes `<plan>`, `<call> tool(args) </call>` and a final answer. The harness runs the call in the work folder,
returns `<result>..</result>`, and shows everything as UI blocks, never as raw tags. Tools: `read`, `write`, `edit`,
`shell`, `search(content, source)`. Reading and listing run freely; deleting, moving and unknown commands ask first.

## Limits

Alethic-300M is small. On my 50-prompt check, SFT-3c passed 19 of 35 graded prompts, and edits at a given line failed
every time. Check anything that matters.

## Tests

    pip install -e .
    pytest

## License

MIT, see `LICENSE`.

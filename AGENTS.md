# AGENTS.md

<!-- cs-template:begin (this block is owned by cs-project-template: do not edit; the rest of the file is the project's) -->
Entry point for coding agents (and people) working in csopencvcuda. The rules of every cscosine repository are
in [.claude/cscosine-rules.md](.claude/cscosine-rules.md): read them first. What is specific to this repository
follows this block.

Commands:

- Setup: `./setup.sh` (Windows: `.\setup.ps1`), then `source .venv/bin/activate` (the pre-commit hooks run in it).
- Checks: `pre-commit run --all-files`; tests: `pytest` (`--run-all`: every test, as CI).
- Recipe: `python csopencvcuda_project.py` (local run), `python csopencvcuda_project.py generate-github-workflow`
  after changing it.

Who owns which file (template: [cs-project-template](https://github.com/cscosine/cs-project-template); change it
there, then `copier update --defaults`; never edit its parts here):

- Template: `setup.sh`, `setup.ps1`, `open-code.sh`, `open-code.ps1`, `conftest.py`, `.clang-format`,
  `.vscode/`, `.github/` (the workflows: `checks.yml` only), `CLAUDE.md`, `.claude/cscosine-rules.md`, `.claude/settings.json`,
  `LICENSE`.
- Template and project: `pyproject.toml` (template tables between the `template` markers), `.pre-commit-config.yaml` (project hooks
  between the `project: begin` / `project: end` markers), `.gitignore`, `.gitattributes` (project lines after
  `--- project ---`), `README.md` and this file (the
  `cs-template` block).
- csorchestrator (generated, never edited): `.github/workflows/csopencvcuda.yml`, `csorchestratorsdk/`,
  `dependencies/`.
- The project: everything else.
<!-- cs-template:end -->

## csopencvcuda

OpenCV 5 with CUDA built for Linux x64 and Windows

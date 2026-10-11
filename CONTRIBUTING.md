# Contributing to speakloop

Thanks for taking the time to help! This project is small and young, so every issue, idea and pull request
matters. By taking part you agree to follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to help

- **Report a bug** with the [bug report form](https://github.com/ducvuathuduc/speakloop/issues/new?template=bug_report.yml).
- **Suggest a feature** with the [feature request form](https://github.com/ducvuathuduc/speakloop/issues/new?template=feature_request.yml).
- **Improve the docs**: typos, clearer examples and translations are all welcome.
- **Send code**: look for issues labelled `good first issue` or `help wanted`, or pick something below.

Good first contributions:

- New drills in `speakloop/content.py` (original text only, with a reference answer)
- A new first-language sound pack: copy `skills/l1-template/` to `skills/l1-<code>/`, fill `pack.json`
  (and optionally `rules.yaml`), then `python -m speakloop.skillpacks validate skills/l1-<code>`
- Accessibility and mobile layout fixes for the simulator (`web/`)
- New planner providers behind the same `/agent/step` contract

## Development setup

```bash
git clone https://github.com/ducvuathuduc/speakloop && cd speakloop
python3 -m venv .venv && source .venv/bin/activate   # Python 3.11+
pip install -r requirements-dev.txt
sudo apt-get install espeak-ng                       # optional: the G2P tests skip without it
python -m pytest -q                                  # must stay green (slow real-model tests: -m slow)
(cd ui && npm ci && npm test)                        # if you touch the MCP App card
python -m speakloop.server                           # http://127.0.0.1:8765
```

## Pull request workflow

1. Fork the repo and create a branch from `main` (`feat/short-name` or `fix/short-name`).
2. Make your change with tests. Keep pull requests focused: one topic per PR.
3. Run the test suite locally; CI runs the same command on every push and pull request.
4. Write a clear commit message in the imperative mood ("Add …", "Fix …"). [Conventional Commits](https://www.conventionalcommits.org/) prefixes are welcome but not required.
5. Open the PR and fill in the template. A maintainer will review it as soon as possible.

## Style

- Python 3.11+, standard library first; keep new runtime dependencies to a minimum.
- Keep tool results voice-first: one short `speech` line, details in `structuredContent`.
- Every scoring rule must stay explainable: a learner should be able to see *which word* caused a deduction.
- Tests must never call AWS or any paid API. Stub providers like `tests/test_agent.py` does.
- Never commit keys. `.env` is git-ignored; put new settings in `.env.example` with an empty value.

## Security

Please do **not** open public issues for security problems. See [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).

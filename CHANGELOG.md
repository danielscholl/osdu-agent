# Changelog

## [0.1.5](https://github.com/danielscholl/osdu-agent/compare/osdu-agent-v0.1.4...osdu-agent-v0.1.5) (2025-10-27)


### Bug Fixes

* resolve 17 CodeQL security and code quality issues ([#14](https://github.com/danielscholl/osdu-agent/issues/14)) ([77c677e](https://github.com/danielscholl/osdu-agent/commit/77c677e4d7023ec5a17238966ce098afc0b64440))
* resolve 5 remaining CodeQL issues and suppress 9 false positives ([#16](https://github.com/danielscholl/osdu-agent/issues/16)) ([71818c4](https://github.com/danielscholl/osdu-agent/commit/71818c4fb9b07ce03993fe749681e425fceca3b1))

## [0.1.4](https://github.com/danielscholl/osdu-agent/compare/osdu-agent-v0.1.3...osdu-agent-v0.1.4) (2025-10-27)


### Features

* **observability:** complete Application Insights integration with CLI auth ([#12](https://github.com/danielscholl/osdu-agent/issues/12)) ([123cf66](https://github.com/danielscholl/osdu-agent/commit/123cf66e06698aed97d92c7f4ae9471ec238ccf7))

## [0.1.3](https://github.com/danielscholl/osdu-agent/compare/osdu-agent-v0.1.2...osdu-agent-v0.1.3) (2025-10-27)


### Features

* **mcp:** redirect stderr to /dev/null when logging disabled ([#9](https://github.com/danielscholl/osdu-agent/issues/9)) ([90f9a71](https://github.com/danielscholl/osdu-agent/commit/90f9a7189f268ae2f398b63793bb5fed015c8de3))


### Bug Fixes

* **release:** remove uv.lock from release-please configuration ([#10](https://github.com/danielscholl/osdu-agent/issues/10)) ([1ca1c08](https://github.com/danielscholl/osdu-agent/commit/1ca1c08b83f825036db3373f28cf32cd82ede64f))

## [0.1.2](https://github.com/danielscholl/osdu-agent/compare/osdu-agent-v0.1.1...osdu-agent-v0.1.2) (2025-10-27)


### Features

* **cli:** add version flag with package metadata support ([#7](https://github.com/danielscholl/osdu-agent/issues/7)) ([2aee77d](https://github.com/danielscholl/osdu-agent/commit/2aee77d5bf8c3f906097ae54a40fd817b03a2a2e))

## [0.1.1](https://github.com/danielscholl/osdu-agent/compare/osdu-agent-v0.1.0...osdu-agent-v0.1.1) (2025-10-26)


### Features

* **config:** add configurable repos root and optional logging ([0f6a6d6](https://github.com/danielscholl/osdu-agent/commit/0f6a6d6c138d69ac2f342518d1a8e260bc23429f))
* initialize OSDU Agent with AI-powered GitHub & GitLab management ([c927e17](https://github.com/danielscholl/osdu-agent/commit/c927e173a3b9d4e12d714d1da93045a67e9994f0))


### Documentation

* add upgrade instructions to README ([#6](https://github.com/danielscholl/osdu-agent/issues/6)) ([99c044b](https://github.com/danielscholl/osdu-agent/commit/99c044b40a5ceef3504b0d1e3c2400ead8d77878))
* **config:** clarify optional environment variables with defaults ([0c55f2a](https://github.com/danielscholl/osdu-agent/commit/0c55f2aa82cd3ea7e166ac91348bde6d0bfccde0))
* **readme:** remove GitLab status, dependency analysis, and session management sections ([500354f](https://github.com/danielscholl/osdu-agent/commit/500354fdcb6a6b8b5c702fb4530e6c4fb194a834))
* refine project description and positioning ([ccb9daa](https://github.com/danielscholl/osdu-agent/commit/ccb9daa359e02c9b46510c0da87e14c5036883c1))
* refine project overview and update prerequisites ([38755b0](https://github.com/danielscholl/osdu-agent/commit/38755b097d8e3d78b66bda33de2a6e055b52a22b))
* simplify README with streamlined overview and quickstart ([1edadb4](https://github.com/danielscholl/osdu-agent/commit/1edadb4f8e52504168bb1b6096db71b0d49068db))
* update Python version requirement and license information ([ffb2874](https://github.com/danielscholl/osdu-agent/commit/ffb28746c889ac21a1987b320dd8ceb77ee5b1aa))
* update Python version requirement to 3.12 and adjust coverage threshold ([4603813](https://github.com/danielscholl/osdu-agent/commit/46038136660ed7d8758f99c195afee801b2600fd))


### Tests

* handle optional log file and repos_root in test fixtures ([d5a8de7](https://github.com/danielscholl/osdu-agent/commit/d5a8de7b6c7baa2850c4c5591b56f3ab5f869167))


### Build System

* **deps:** bump actions/upload-artifact from 4 to 5 ([#1](https://github.com/danielscholl/osdu-agent/issues/1)) ([ad67489](https://github.com/danielscholl/osdu-agent/commit/ad67489c224fc6420c8c797c4adbe996b59c1ca2))


### Continuous Integration

* reduce coverage threshold to 60% and relax mypy type checking ([ac786a4](https://github.com/danielscholl/osdu-agent/commit/ac786a43a707afbce4fd09570ebc03d552e1b92f))


### Miscellaneous

* **ci:** migrate dependabot from pip to uv package manager ([77692a4](https://github.com/danielscholl/osdu-agent/commit/77692a4fb480093f3f162b359d9f7906cb9d4257))
* **deps:** bump ruff from 0.13.3 to 0.14.2 in the python-dev group ([#3](https://github.com/danielscholl/osdu-agent/issues/3)) ([27288e8](https://github.com/danielscholl/osdu-agent/commit/27288e8f76e98a3bfcf479bc64e28218d986f3dd))
* **deps:** bump the python-prod group with 5 updates ([#4](https://github.com/danielscholl/osdu-agent/issues/4)) ([337b488](https://github.com/danielscholl/osdu-agent/commit/337b4887cf704d046ca2c5dc5055b47a906c2ae4))
* **env:** update .env.example defaults for Azure OpenAI and GitHub token ([29d9624](https://github.com/danielscholl/osdu-agent/commit/29d96249f747b0f92f3c24e45fd9b5d5f4324f62))
* expand default repository list and improve code formatting ([c87d0c8](https://github.com/danielscholl/osdu-agent/commit/c87d0c8381a84ac203d265456e4b84d70029d179))

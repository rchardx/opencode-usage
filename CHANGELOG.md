# Changelog

## [0.2.3](https://github.com/rchardx/opencode-usage/compare/v0.2.2...v0.2.3) (2026-03-03)


### Features

* **cli:** add --version / -V flag ([a1273dd](https://github.com/rchardx/opencode-usage/commit/a1273dd5f480b16490c0c737ef495528bfd7d54f))


### Code Refactoring

* **cli:** remove global flags and shortcuts, default to run subcommand ([11d0368](https://github.com/rchardx/opencode-usage/commit/11d0368d7d10bdebedaa286ac342a3c59c6a4ae1))

## [0.2.2](https://github.com/rchardx/opencode-usage/compare/v0.2.1...v0.2.2) (2026-03-02)


### Features

* add --compare mode for period-over-period comparison ([0a89549](https://github.com/rchardx/opencode-usage/commit/0a895491a9f7185c3b001f196511e15fc387ee46))
* add --no-color flag for disabling colored output ([ccb2e14](https://github.com/rchardx/opencode-usage/commit/ccb2e14cd22d8a3f49f42d688c2535a798fdbed2))
* add model discovery, ranking, and interactive selection ([da2b90e](https://github.com/rchardx/opencode-usage/commit/da2b90ec5547750876e0fad1babd59e509275ad0))
* add sparkline trend column to daily view ([bd870cd](https://github.com/rchardx/opencode-usage/commit/bd870cd1e9ae85cc8609e590221c9016acb59bbe))
* **cli:** add insights command with --no-llm, --provider, --model flags ([a65d0f3](https://github.com/rchardx/opencode-usage/commit/a65d0f36d70aeab1f4b8e97ca46547f5d94e6c66))
* **cli:** add opencode CLI wrapper for dynamic path resolution ([b76858c](https://github.com/rchardx/opencode-usage/commit/b76858ce94a77973aa05d11d01a3d86a584fd1b1))
* **cli:** add run_models wrapper to opencode CLI module ([6fd89fe](https://github.com/rchardx/opencode-usage/commit/6fd89fe7034be0c8575804e04c3c729ad62cc352))
* **db:** add derived metric queries and transcript builder for insights ([10abb8a](https://github.com/rchardx/opencode-usage/commit/10abb8a70b4f794455112b40e637c8c7fbfd980c))
* initial release of opencode-usage CLI ([ab8eb4d](https://github.com/rchardx/opencode-usage/commit/ab8eb4d0ff213c0e88080b42cf6abc6efb033398))
* **insights:** add concurrent LLM analysis with ThreadPoolExecutor ([61c0156](https://github.com/rchardx/opencode-usage/commit/61c01567d66ba9ace89a84455021b3d2d7a2ad2d))
* **insights:** add dataclasses, auth resolver, and LLM client for insights pipeline ([cdabf66](https://github.com/rchardx/opencode-usage/commit/cdabf66cf685705be8cb2b7464e8384f54ab6b9d))
* **insights:** add e2e integration, progress display, and error handling ([f87d817](https://github.com/rchardx/opencode-usage/commit/f87d81782fa2f401dbdace085709fe5e79cfd1d0))
* **insights:** add facet cache, quant engine, facet extraction, and suggestion generation ([3f53d89](https://github.com/rchardx/opencode-usage/commit/3f53d89f3298115ba1001dd4dea87ccdef286798))
* **insights:** add facet extraction and aggregate analysis pipeline ([8fc4990](https://github.com/rchardx/opencode-usage/commit/8fc49908235cfdaa846b7733cf466debc72c32e0))
* **insights:** add insights_to_dict serializer and JSON output for insights command ([771f74f](https://github.com/rchardx/opencode-usage/commit/771f74f00f7dd7471dc09f2d22035acf5d011a86))
* **insights:** add session extraction, transcript reconstruction, stats, and prompt templates ([3e41513](https://github.com/rchardx/opencode-usage/commit/3e415135c11b1f876af9039a62ae3780949d614d))
* **insights:** add terminal-style HTML report generation ([3412e8d](https://github.com/rchardx/opencode-usage/commit/3412e8d4cde2a0a60af7ab3f2635a333d66ec4e8))
* **insights:** add types, cache, LLM runner, and CLI scaffolding ([f8ae7ca](https://github.com/rchardx/opencode-usage/commit/f8ae7ca73979b8713a38134a7c802bc3cb558248))
* **render:** add render_insights and render_insights_progress panels ([0e31561](https://github.com/rchardx/opencode-usage/commit/0e3156197f213e9436fe68a4be412bfbadd72e00))
* replace sparkline with horizontal trend bar ([35738a7](https://github.com/rchardx/opencode-usage/commit/35738a72327273eebcf5b6e0ba7adb56bc70ad21))


### Bug Fixes

* **ci:** remove component prefix from release-please tags ([cbe0598](https://github.com/rchardx/opencode-usage/commit/cbe059857300939faf26313a9f2af6ed10775b3e))
* **db:** use ~/.local/share path on all platforms to match OpenCode ([381a212](https://github.com/rchardx/opencode-usage/commit/381a21218de1b4373e77869ab3bad783f1a35db4))
* derive __version__ from package metadata dynamically ([1572cea](https://github.com/rchardx/opencode-usage/commit/1572cea7b9ec59763776698365bc8d760a5e6a56))
* sync __init__.py version to 0.1.2 ([dc06366](https://github.com/rchardx/opencode-usage/commit/dc063667a7e23fa545e0455295f6368f6e9b414d))
* **test:** make aggregate analysis test thread-order independent ([ccc3d92](https://github.com/rchardx/opencode-usage/commit/ccc3d92e47fa4696becd3d0452f685f1c20d78e1))


### Code Refactoring

* **auth:** use opencode CLI for paths and define Credentials locally ([8d4278b](https://github.com/rchardx/opencode-usage/commit/8d4278b80057350a236c7df4c1cd73e0d7bdccdc))
* **cli:** restructure argument parsing with run/insights subcommands ([4b9ba45](https://github.com/rchardx/opencode-usage/commit/4b9ba4599341781d47c7d954e7ea245d272a8047))
* **db:** use opencode CLI for path resolution and define SessionMeta locally ([eca5da5](https://github.com/rchardx/opencode-usage/commit/eca5da5b581d2443783da491d4450212dc11d614))
* **insights:** make InsightsConfig.model required, wire interactive picker ([56707b0](https://github.com/rchardx/opencode-usage/commit/56707b0f921e28869440245f67ec57ae162086e6))
* **insights:** use opencode CLI for DB path in orchestrator ([9fe5a93](https://github.com/rchardx/opencode-usage/commit/9fe5a93e165e7f7dedf2f69cae918fd71f75653d))
* remove dead legacy types and render functions ([b5f8103](https://github.com/rchardx/opencode-usage/commit/b5f810329dd4614b311b5cda15fe739b45ad735a))


### Documentation

* add AGENTS.md for AI agent guidelines ([96d9b89](https://github.com/rchardx/opencode-usage/commit/96d9b8942cb10b0837d8f0997f7184afb88415e1))
* add PyPI installation instructions to README ([f32c957](https://github.com/rchardx/opencode-usage/commit/f32c9578691e4d7e3b46348149ff14314c5e6c70))

## [0.2.1](https://github.com/rchardx/opencode-usage/compare/opencode-usage-v0.2.0...opencode-usage-v0.2.1) (2026-03-02)


### Features

* add --compare mode for period-over-period comparison ([0a89549](https://github.com/rchardx/opencode-usage/commit/0a895491a9f7185c3b001f196511e15fc387ee46))
* add --no-color flag for disabling colored output ([ccb2e14](https://github.com/rchardx/opencode-usage/commit/ccb2e14cd22d8a3f49f42d688c2535a798fdbed2))
* add model discovery, ranking, and interactive selection ([da2b90e](https://github.com/rchardx/opencode-usage/commit/da2b90ec5547750876e0fad1babd59e509275ad0))
* add sparkline trend column to daily view ([bd870cd](https://github.com/rchardx/opencode-usage/commit/bd870cd1e9ae85cc8609e590221c9016acb59bbe))
* **cli:** add insights command with --no-llm, --provider, --model flags ([a65d0f3](https://github.com/rchardx/opencode-usage/commit/a65d0f36d70aeab1f4b8e97ca46547f5d94e6c66))
* **cli:** add opencode CLI wrapper for dynamic path resolution ([b76858c](https://github.com/rchardx/opencode-usage/commit/b76858ce94a77973aa05d11d01a3d86a584fd1b1))
* **cli:** add run_models wrapper to opencode CLI module ([6fd89fe](https://github.com/rchardx/opencode-usage/commit/6fd89fe7034be0c8575804e04c3c729ad62cc352))
* **db:** add derived metric queries and transcript builder for insights ([10abb8a](https://github.com/rchardx/opencode-usage/commit/10abb8a70b4f794455112b40e637c8c7fbfd980c))
* initial release of opencode-usage CLI ([ab8eb4d](https://github.com/rchardx/opencode-usage/commit/ab8eb4d0ff213c0e88080b42cf6abc6efb033398))
* **insights:** add concurrent LLM analysis with ThreadPoolExecutor ([61c0156](https://github.com/rchardx/opencode-usage/commit/61c01567d66ba9ace89a84455021b3d2d7a2ad2d))
* **insights:** add dataclasses, auth resolver, and LLM client for insights pipeline ([cdabf66](https://github.com/rchardx/opencode-usage/commit/cdabf66cf685705be8cb2b7464e8384f54ab6b9d))
* **insights:** add e2e integration, progress display, and error handling ([f87d817](https://github.com/rchardx/opencode-usage/commit/f87d81782fa2f401dbdace085709fe5e79cfd1d0))
* **insights:** add facet cache, quant engine, facet extraction, and suggestion generation ([3f53d89](https://github.com/rchardx/opencode-usage/commit/3f53d89f3298115ba1001dd4dea87ccdef286798))
* **insights:** add facet extraction and aggregate analysis pipeline ([8fc4990](https://github.com/rchardx/opencode-usage/commit/8fc49908235cfdaa846b7733cf466debc72c32e0))
* **insights:** add insights_to_dict serializer and JSON output for insights command ([771f74f](https://github.com/rchardx/opencode-usage/commit/771f74f00f7dd7471dc09f2d22035acf5d011a86))
* **insights:** add session extraction, transcript reconstruction, stats, and prompt templates ([3e41513](https://github.com/rchardx/opencode-usage/commit/3e415135c11b1f876af9039a62ae3780949d614d))
* **insights:** add terminal-style HTML report generation ([3412e8d](https://github.com/rchardx/opencode-usage/commit/3412e8d4cde2a0a60af7ab3f2635a333d66ec4e8))
* **insights:** add types, cache, LLM runner, and CLI scaffolding ([f8ae7ca](https://github.com/rchardx/opencode-usage/commit/f8ae7ca73979b8713a38134a7c802bc3cb558248))
* **render:** add render_insights and render_insights_progress panels ([0e31561](https://github.com/rchardx/opencode-usage/commit/0e3156197f213e9436fe68a4be412bfbadd72e00))
* replace sparkline with horizontal trend bar ([35738a7](https://github.com/rchardx/opencode-usage/commit/35738a72327273eebcf5b6e0ba7adb56bc70ad21))


### Bug Fixes

* **db:** use ~/.local/share path on all platforms to match OpenCode ([381a212](https://github.com/rchardx/opencode-usage/commit/381a21218de1b4373e77869ab3bad783f1a35db4))
* derive __version__ from package metadata dynamically ([1572cea](https://github.com/rchardx/opencode-usage/commit/1572cea7b9ec59763776698365bc8d760a5e6a56))
* sync __init__.py version to 0.1.2 ([dc06366](https://github.com/rchardx/opencode-usage/commit/dc063667a7e23fa545e0455295f6368f6e9b414d))
* **test:** make aggregate analysis test thread-order independent ([ccc3d92](https://github.com/rchardx/opencode-usage/commit/ccc3d92e47fa4696becd3d0452f685f1c20d78e1))


### Code Refactoring

* **auth:** use opencode CLI for paths and define Credentials locally ([8d4278b](https://github.com/rchardx/opencode-usage/commit/8d4278b80057350a236c7df4c1cd73e0d7bdccdc))
* **cli:** restructure argument parsing with run/insights subcommands ([4b9ba45](https://github.com/rchardx/opencode-usage/commit/4b9ba4599341781d47c7d954e7ea245d272a8047))
* **db:** use opencode CLI for path resolution and define SessionMeta locally ([eca5da5](https://github.com/rchardx/opencode-usage/commit/eca5da5b581d2443783da491d4450212dc11d614))
* **insights:** make InsightsConfig.model required, wire interactive picker ([56707b0](https://github.com/rchardx/opencode-usage/commit/56707b0f921e28869440245f67ec57ae162086e6))
* **insights:** use opencode CLI for DB path in orchestrator ([9fe5a93](https://github.com/rchardx/opencode-usage/commit/9fe5a93e165e7f7dedf2f69cae918fd71f75653d))
* remove dead legacy types and render functions ([b5f8103](https://github.com/rchardx/opencode-usage/commit/b5f810329dd4614b311b5cda15fe739b45ad735a))


### Documentation

* add AGENTS.md for AI agent guidelines ([96d9b89](https://github.com/rchardx/opencode-usage/commit/96d9b8942cb10b0837d8f0997f7184afb88415e1))
* add PyPI installation instructions to README ([f32c957](https://github.com/rchardx/opencode-usage/commit/f32c9578691e4d7e3b46348149ff14314c5e6c70))

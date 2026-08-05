"""Tests for opencode_usage.config persistent configuration."""

from __future__ import annotations

from opencode_usage.config import config_dir, config_path, load


class TestConfigLoad:
    def test_missing_file_yields_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "nonexistent"))
        cfg = load()
        assert cfg.days is None
        assert cfg.by is None
        assert cfg.sort == "tokens"
        assert cfg.preferred_models == []

    def test_valid_file(self, tmp_path, monkeypatch):
        conf_dir = tmp_path / "config"
        (conf_dir / "opencode-usage").mkdir(parents=True)
        (conf_dir / "opencode-usage" / "config.toml").write_text(
            "[defaults]\n"
            "days = 14\n"
            'by = "model"\n'
            'sort = "cost"\n'
            "\n"
            "[insights]\n"
            'preferred_models = ["opencode-go/kimi-k3"]\n'
        )
        monkeypatch.setenv("XDG_CONFIG_HOME", str(conf_dir))
        cfg = load()
        assert cfg.days == 14
        assert cfg.by == "model"
        assert cfg.sort == "cost"
        assert cfg.preferred_models == ["opencode-go/kimi-k3"]

    def test_malformed_file_yields_defaults(self, tmp_path, monkeypatch):
        conf_dir = tmp_path / "config"
        (conf_dir / "opencode-usage").mkdir(parents=True)
        (conf_dir / "opencode-usage" / "config.toml").write_text("not [valid toml")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(conf_dir))
        cfg = load()
        assert cfg.sort == "tokens"

    def test_invalid_sort_ignored(self, tmp_path, monkeypatch):
        conf_dir = tmp_path / "config"
        (conf_dir / "opencode-usage").mkdir(parents=True)
        (conf_dir / "opencode-usage" / "config.toml").write_text('[defaults]\nsort = "bogus"\n')
        monkeypatch.setenv("XDG_CONFIG_HOME", str(conf_dir))
        cfg = load()
        assert cfg.sort == "tokens"


class TestConfigPaths:
    def test_default_dir_is_dot_config(self, monkeypatch):
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        assert str(config_dir()).endswith(".config/opencode-usage")

    def test_path_under_dir(self):
        assert config_path().parent == config_dir()
        assert config_path().name == "config.toml"

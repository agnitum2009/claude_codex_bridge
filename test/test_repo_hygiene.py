from __future__ import annotations

from pathlib import Path
import re
import subprocess

import pytest


def _is_ephemeral_repo_artifact(path_text: str) -> bool:
    path = Path(path_text.strip())
    if not path.parts:
        return False
    first = path.parts[0]
    return first == ".tmp_pytest" or first.startswith(".tmp_test_env_")


def test_git_index_does_not_track_ephemeral_test_artifacts() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    if not (repo_root / ".git").exists():
        pytest.skip("git checkout required")

    completed = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = [
        line
        for line in completed.stdout.splitlines()
        if line.strip() and _is_ephemeral_repo_artifact(line)
    ]

    assert tracked == []


def test_useful_tools_skills_are_provider_paired() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    useful_tools = repo_root / "useful_tools"
    if not useful_tools.exists():
        pytest.skip("useful_tools not present")

    codex_root = useful_tools / "codex_skills"
    claude_root = useful_tools / "claude_skills"
    codex_skills = {
        path.name
        for path in codex_root.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    }
    claude_skills = {
        path.name
        for path in claude_root.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    }

    assert codex_skills == claude_skills


def test_inherited_skills_live_under_inherit_skills_only() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    for legacy_root in ("claude_skills", "codex_skills", "droid_skills"):
        assert not (repo_root / legacy_root).exists()

    inherited = repo_root / "inherit_skills"
    assert (inherited / "claude_skills" / "ask" / "SKILL.md").is_file()
    assert (inherited / "codex_skills" / "ask" / "SKILL.md").is_file()
    assert (inherited / "droid_skills" / "ask" / "SKILL.md").is_file()
    assert (inherited / "claude_skills" / "ccb-config" / "SKILL.md").is_file()
    assert (inherited / "codex_skills" / "ccb-config" / "SKILL.md").is_file()
    assert (inherited / "claude_skills" / "ccb-clear" / "SKILL.md").is_file()
    assert (inherited / "codex_skills" / "ccb-clear" / "SKILL.md").is_file()

    assert not (repo_root / "useful_tools" / "claude_skills" / "ccb-config").exists()
    assert not (repo_root / "useful_tools" / "codex_skills" / "ccb-config").exists()
    assert not (repo_root / "useful_tools" / "claude_skills" / "ccb-clear").exists()
    assert not (repo_root / "useful_tools" / "codex_skills" / "ccb-clear").exists()


def test_inherited_skill_set_is_minimal() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    expected = {
        "claude_skills": {"ask", "ccb-config", "ccb-clear"},
        "codex_skills": {"ask", "ccb-config", "ccb-clear"},
        "droid_skills": {"ask"},
    }
    for provider_root, expected_names in expected.items():
        skill_root = repo_root / "inherit_skills" / provider_root
        actual = {
            path.name
            for path in skill_root.iterdir()
            if path.is_dir() and (path / "SKILL.md").is_file()
        }

        assert actual == expected_names


def test_install_scripts_current_skill_lists_are_minimal() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    install_sh = (repo_root / "install.sh").read_text(encoding="utf-8")
    install_ps1 = (repo_root / "install.ps1").read_text(encoding="utf-8")

    assert 'local ccb_skills="ask ccb-config ccb-clear"' in install_sh
    assert 'local ccb_skills="ask ping' not in install_sh
    assert '$ccbSkills = @("ask", "ccb-config", "ccb-clear")' in install_ps1
    assert '$ccbSkills = @("ask", "ccb-config", "ping"' not in install_ps1
    assert '$droidSkills = @("ask")' in install_ps1


def test_inherited_codex_skill_names_are_valid_and_match_directories() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    skill_root = repo_root / "inherit_skills" / "codex_skills"
    name_re = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

    for skill_dir in skill_root.iterdir():
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        text = skill_md.read_text(encoding="utf-8")
        first_name = next(
            line.split(":", 1)[1].strip()
            for line in text.splitlines()
            if line.startswith("name:")
        )

        assert first_name == skill_dir.name
        assert name_re.fullmatch(first_name)


def test_ccb_config_skill_uses_current_config_authority() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    for provider_root in ("claude_skills", "codex_skills"):
        skill_text = (
            repo_root
            / "inherit_skills"
            / provider_root
            / "ccb-config"
            / "SKILL.md"
        ).read_text(encoding="utf-8")
        reference_text = (
            repo_root
            / "inherit_skills"
            / provider_root
            / "ccb-config"
            / "references"
            / "ccb-config.md"
        ).read_text(encoding="utf-8")

        assert "CCB config precedence is built-in default < user config" in skill_text
        assert "The normal output is a valid `.ccb/ccb.config`" in skill_text
        assert "only when explicitly requested, a user-level `~/.ccb/ccb.config`" in skill_text
        assert "Never write `.ccb_config/ccb.config`" in skill_text
        assert "Never run `ccb`, `ccb -s`, `ccb kill`" in skill_text
        assert "result.source_kind" in skill_text
        assert "Explicit windows topology uses `version = 2`, `[windows]`" in skill_text
        assert "treat it as a migration task" in skill_text
        assert "Migration to `[windows]` is the default recommendation" in skill_text
        assert "workspace_group" in skill_text
        assert "provider_command_template" in skill_text
        assert "Do not write `.ccb_config/ccb.config`" in reference_text
        assert "## Explicit Windows Topology" in reference_text
        assert "## Migrating Old Configs To Windows" in reference_text
        assert "Old compact and hybrid configs are still valid single-window configs" in reference_text
        assert "cmd` is not supported inside `[windows]` topology" in reference_text
        assert "workspace_path" in reference_text
        assert "workspace_group" in reference_text
        assert "provider_command_template" in reference_text


def test_ccb_config_role_pack_docs_use_agentroles_archi_with_legacy_alias_only() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    allowed_legacy_context = ("legacy", "migration", "not `ccb.archi`", "do not write `ccb.archi`", "rewrite")
    forbidden_new_usage = (
        "ccb roles install ccb.archi",
        "ccb roles doctor ccb.archi",
        "ccb roles add ccb.archi",
        'role = "ccb.archi"',
        "ccb.archi:codex",
    )
    for provider_root in ("claude_skills", "codex_skills"):
        paths = (
            repo_root / "inherit_skills" / provider_root / "ccb-config" / "SKILL.md",
            repo_root / "inherit_skills" / provider_root / "ccb-config" / "references" / "ccb-config.md",
        )
        for path in paths:
            text = path.read_text(encoding="utf-8")

            assert "agentroles.archi:codex" in text
            assert 'role = "agentroles.archi"' in text
            assert "ccb roles install agentroles.archi" in text
            assert "ccb roles doctor agentroles.archi" in text
            assert "ccb roles add agentroles.archi:codex" in text
            assert "ccb ask archi" in text
            for forbidden in forbidden_new_usage:
                assert forbidden not in text
            for line in text.splitlines():
                if "ccb.archi" in line:
                    lowered = line.lower()
                    assert any(context in lowered for context in allowed_legacy_context), line


def test_ccb_config_skill_is_config_only_without_workflow_memory_patterns() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    for provider_root in ("claude_skills", "codex_skills"):
        skill_text = (
            repo_root
            / "inherit_skills"
            / provider_root
            / "ccb-config"
            / "SKILL.md"
        ).read_text(encoding="utf-8")
        reference_text = (
            repo_root
            / "inherit_skills"
            / provider_root
            / "ccb-config"
            / "references"
            / "ccb-config.md"
        ).read_text(encoding="utf-8")
        removed_memory_patterns = (
            repo_root
            / "inherit_skills"
            / provider_root
            / "ccb-config"
            / "references"
            / "memory-patterns.md"
        )

        assert not removed_memory_patterns.exists()
        assert "This skill is not a workflow-memory designer" in skill_text
        assert "Do not edit `.ccb/ccb_memory.md`" in skill_text
        assert "workflow memory can be set separately" in skill_text
        assert "workflow memory files" in reference_text
        assert "Do not edit memory files for ordinary config design" in reference_text
        assert "callback dependencies" not in skill_text
        assert "main -> worker" not in skill_text


def test_source_checkout_runtime_discipline_is_enforced_by_entrypoints() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source_entrypoint = (repo_root / "ccb").read_text(encoding="utf-8")
    test_entrypoint = (repo_root / "ccb_test").read_text(encoding="utf-8")

    for text in (source_entrypoint, test_entrypoint):
        assert "source checkout" in text or "source-change validation" in text
        assert "ccb_test" in text
        assert "test_ccb2" in text
    assert "/home/bfly/yunwei/test_ccb2" in test_entrypoint


def test_inherited_runtime_skills_distinguish_source_validation_from_work_environment() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    for provider_root in ("claude_skills", "codex_skills"):
        for skill_name in ("ccb-config", "ccb-clear"):
            skill_text = (
                repo_root
                / "inherit_skills"
                / provider_root
                / skill_name
                / "SKILL.md"
            ).read_text(encoding="utf-8")

            assert "source checkout" in skill_text
            assert "source validation" in skill_text
            assert "ccb_test" in skill_text
            assert "/home/bfly/yunwei/test_ccb2" in skill_text

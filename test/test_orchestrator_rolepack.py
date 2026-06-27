from __future__ import annotations

import json
from pathlib import Path
import shutil

from provider_profiles.codex_home_config import materialize_codex_home_config
from rolepacks.manifest import load_role_manifest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DRAFTS = (
    REPO_ROOT
    / 'docs'
    / 'plantree'
    / 'plans'
    / 'agentic-loop-workflow'
    / 'drafts'
)
ORCHESTRATOR_ROLE = (
    WORKFLOW_DRAFTS
    / 'agentroles.ccb_orchestrator'
)
ROLE_EXPECTATIONS = {
    'agentroles.ccb_frontdesk': {
        'default': 'frontdesk',
        'skill': 'skills/frontdesk-intake',
        'templates': ('templates/macro-task-request.md',),
    },
    'agentroles.ccb_planner': {
        'default': 'planner',
        'skill': 'skills/planner-task-packet',
        'templates': (
            'templates/task-packet.md',
            'templates/readiness.json',
            'templates/candidate-questions.jsonl',
        ),
    },
    'agentroles.ccb_plan_reviewer': {
        'default': 'plan_reviewer',
        'skill': 'skills/plan-readiness-review',
        'templates': ('templates/planner-review.md',),
    },
    'agentroles.ccb_clarification_broker': {
        'default': 'clarification_broker',
        'skill': 'skills/clarification-broker',
        'templates': ('templates/user-questions.md', 'templates/normalized-answers.jsonl'),
    },
    'agentroles.ccb_orchestrator': {
        'default': 'orchestrator',
        'skills': (
            'adapters/ccb/skills/orchestrator-capacity',
            'adapters/ccb/skills/dynamic-agent-lifecycle',
        ),
        'templates': (
            'templates/capacity-request.json',
            'templates/worker-ask.md',
            'templates/checker-ask.md',
            'templates/round-aggregation.md',
        ),
    },
    'agentroles.ccb_worker': {
        'default': 'worker',
        'skill': 'skills/bounded-work-item',
        'templates': ('templates/node-work-result.md',),
    },
    'agentroles.ccb_checker': {
        'default': 'code_reviewer',
        'skill': 'skills/node-check',
        'templates': ('templates/node-check-result.md',),
    },
    'agentroles.ccb_round_checker': {
        'default': 'round_checker',
        'skill': 'skills/round-verification',
        'templates': ('templates/round-result.md',),
    },
}


def role_root(role_id: str) -> Path:
    return WORKFLOW_DRAFTS / role_id


def test_orchestrator_rolepack_translates_ccb_skills() -> None:
    manifest = load_role_manifest(ORCHESTRATOR_ROLE)
    expected_skills = [
        'adapters/ccb/skills/orchestrator-capacity',
        'adapters/ccb/skills/dynamic-agent-lifecycle',
    ]

    assert manifest.id == 'agentroles.ccb_orchestrator'
    assert manifest.default_agent_name == 'orchestrator'
    assert {'codex', 'claude', 'qwen', 'zai'} <= set(manifest.providers)
    assert manifest.manifest['memory']['files'] == ['memory.md', 'adapters/ccb/memory.md']
    assert manifest.manifest['skills']['codex'] == expected_skills
    assert manifest.manifest['skills']['qwen'] == expected_skills


def test_orchestrator_capacity_skill_declares_command_boundary() -> None:
    skill = (
        ORCHESTRATOR_ROLE
        / 'adapters'
        / 'ccb'
        / 'skills'
        / 'orchestrator-capacity'
        / 'SKILL.md'
    ).read_text(encoding='utf-8')

    assert 'ccb loop capacity ensure --loop-id <id>' in skill
    assert 'ccb loop capacity status --loop-id <id> --json' in skill
    assert 'ccb loop capacity release --loop-id <id> --policy auto --json' in skill
    assert 'ccb layout status --json' in skill
    assert 'loop_capacity_status = "ensured"' in skill
    assert 'apply.apply_status = "applied"' in skill
    assert 'source=loop' in skill
    assert 'expected `loop_id`/`node_id`' in skill
    assert 'CCB-owned evidence only' in skill
    assert 'runtime layout manager owns window naming' in skill
    assert 'Do not use `ccb loop run-once`' in skill
    assert 'command ask --callback "$WORKER_AGENT"' in skill
    assert 'Never:' in skill
    assert 'edit `.ccb/ccb.config`' in skill
    assert 'ccb agent add --window' in skill
    assert 'ccb agent add --window-class' in skill
    assert 'call raw `ccb reload`' in skill
    assert 'call raw `ccb kill`' in skill
    assert 'run `tmux` commands' in skill
    assert 'exceed `max_nodes`, profile `max_instances`, or four total nodes' in skill
    assert 'capacity requests are advisory' in skill
    assert 'Use this skill only from an execution-ready loop round' in skill
    assert 'replan_required' in skill
    assert 'replan_needed' not in skill
    assert 'dynamic-agent-lifecycle' in skill


def test_dynamic_agent_lifecycle_skill_declares_non_loop_command_boundary() -> None:
    skill = (
        ORCHESTRATOR_ROLE
        / 'adapters'
        / 'ccb'
        / 'skills'
        / 'dynamic-agent-lifecycle'
        / 'SKILL.md'
    ).read_text(encoding='utf-8')

    assert 'ccb agent status --json' in skill
    assert 'ccb agent show <agent> --json' in skill
    assert 'ccb layout resolve <agent>' in skill
    assert 'ccb layout resolve planner_helper1 --window-class plan-orchestrate --json' in skill
    assert 'resolved_window_name' in skill
    assert 'will_create_window' in skill
    assert 'ccb agent add <name>:<provider>' in skill
    assert '--window-class <class>' in skill
    assert 'ccb agent park <agent> --json' in skill
    assert 'ccb agent resume <agent> --hidden --json' in skill
    assert 'ccb agent release <agent> --idle-only --json' in skill
    assert 'ccb layout status --json' in skill
    assert 'agent_kind' in skill
    assert 'ownership_class' in skill
    assert 'dispatch_state' in skill
    assert 'pane_identity_source' in skill
    assert 'failed_apply' in skill
    assert 'retained_busy' in skill
    assert 'namespace_reflowed_windows' in skill
    assert 'source=loop' in skill
    assert 'orchestrator-capacity' in skill
    assert 'Never edit `.ccb/ccb.config`' in skill
    assert 'call raw `ccb reload`' in skill
    assert 'call raw `ccb kill`' in skill
    assert 'run `tmux`' in skill
    assert 'remove --policy kill' in skill


def test_orchestrator_capacity_template_keeps_placement_ccb_owned() -> None:
    template = json.loads(
        (ORCHESTRATOR_ROLE / 'templates' / 'capacity-request.json').read_text(
            encoding='utf-8'
        )
    )

    assert template['placement_policy'] == 'ccb_runtime_layout_manager'
    assert template['forbidden_placement_overrides'] == [
        'window_name',
        'window_class',
        'pane_id',
    ]
    assert 'window_name' not in template
    assert 'window_class' not in template
    assert 'pane_id' not in template


def test_workflow_rolepacks_translate_and_project_role_skills() -> None:
    for role_id, expectation in ROLE_EXPECTATIONS.items():
        manifest = load_role_manifest(role_root(role_id))

        assert manifest.id == role_id
        assert manifest.default_agent_name == expectation['default']
        assert {'codex', 'claude', 'qwen', 'zai'} <= set(manifest.providers)
        assert manifest.manifest['memory']['files'] == ['memory.md', 'adapters/ccb/memory.md']
        expected_skills = tuple(expectation.get('skills') or (expectation['skill'],))
        assert manifest.manifest['skills']['codex'] == list(expected_skills)
        assert manifest.manifest['skills']['qwen'] == list(expected_skills)
        for skill in expected_skills:
            assert (manifest.root / skill / 'SKILL.md').is_file()


def test_workflow_rolepacks_include_common_authority_rule_and_templates() -> None:
    shared = (WORKFLOW_DRAFTS / '_shared' / 'authority-rule.md').read_text(encoding='utf-8')
    assert 'You may author semantic artifacts and recommend transitions.' in shared
    assert 'You must not directly edit authoritative state' in shared
    assert 'program kernel should stay simple and stable' in shared

    for role_id, expectation in ROLE_EXPECTATIONS.items():
        root = role_root(role_id)
        memory = (root / 'memory.md').read_text(encoding='utf-8')
        assert 'You may author semantic artifacts and recommend transitions.' in memory
        assert 'You must not directly edit authoritative state' in memory
        assert 'hand-edit state files' in memory
        for template in expectation['templates']:
            assert (root / template).is_file(), f'{role_id} missing {template}'


def test_round_checker_and_orchestrator_templates_share_result_contract() -> None:
    round_template = (
        WORKFLOW_DRAFTS
        / 'agentroles.ccb_round_checker'
        / 'templates'
        / 'round-result.md'
    ).read_text(encoding='utf-8')
    aggregation_template = (
        ORCHESTRATOR_ROLE
        / 'templates'
        / 'round-aggregation.md'
    ).read_text(encoding='utf-8')
    checker_ask = (ORCHESTRATOR_ROLE / 'templates' / 'checker-ask.md').read_text(
        encoding='utf-8'
    )

    assert 'round result: pass|rework_node|partial|replan_required|global_blocker' in round_template
    assert 'aggregation result: complete|partial|blocked|replan_required' in aggregation_template
    assert 'pass`, `rework_required`, `blocked`, `non_converged' in checker_ask


def test_orchestrator_rolepack_projects_capacity_skill_to_codex_home(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('AGENT_ROLES_STORE', str(tmp_path / '.roles'))
    installed = tmp_path / '.roles' / 'installed' / 'agentroles.ccb_orchestrator' / 'current'
    installed.parent.mkdir(parents=True)
    shutil.copytree(ORCHESTRATOR_ROLE, installed)

    project = tmp_path / 'project'
    (project / '.ccb').mkdir(parents=True)
    (project / '.ccb' / 'ccb.config').write_text(
        '\n'.join(
            [
                'version = 2',
                'entry_window = "main"',
                '',
                '[windows]',
                'main = "orchestrator:codex"',
                '',
                '[agents.orchestrator]',
                'role = "agentroles.ccb_orchestrator"',
            ]
        )
        + '\n',
        encoding='utf-8',
    )
    target_home = tmp_path / 'managed-codex'
    source_home = tmp_path / 'source-codex'

    materialize_codex_home_config(
        target_home,
        source_home=source_home,
        project_root=project,
        agent_name='orchestrator',
        workspace_path=project,
    )

    projected = target_home / 'skills' / 'orchestrator-capacity' / 'SKILL.md'
    assert projected.is_file()
    assert 'ccb loop capacity ensure' in projected.read_text(encoding='utf-8')
    dynamic_projected = target_home / 'skills' / 'dynamic-agent-lifecycle' / 'SKILL.md'
    assert dynamic_projected.is_file()
    dynamic_text = dynamic_projected.read_text(encoding='utf-8')
    assert 'ccb layout resolve <agent>' in dynamic_text
    assert 'ccb agent add <name>:<provider>' in dynamic_text


def test_planner_rolepack_projects_planner_skill_to_codex_home(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('AGENT_ROLES_STORE', str(tmp_path / '.roles'))
    installed = tmp_path / '.roles' / 'installed' / 'agentroles.ccb_planner' / 'current'
    installed.parent.mkdir(parents=True)
    shutil.copytree(role_root('agentroles.ccb_planner'), installed)

    project = tmp_path / 'project'
    (project / '.ccb').mkdir(parents=True)
    (project / '.ccb' / 'ccb.config').write_text(
        '\n'.join(
            [
                'version = 2',
                'entry_window = "main"',
                '',
                '[windows]',
                'main = "planner:codex"',
                '',
                '[agents.planner]',
                'role = "agentroles.ccb_planner"',
            ]
        )
        + '\n',
        encoding='utf-8',
    )
    target_home = tmp_path / 'managed-codex'
    source_home = tmp_path / 'source-codex'

    materialize_codex_home_config(
        target_home,
        source_home=source_home,
        project_root=project,
        agent_name='planner',
        workspace_path=project,
    )

    projected = target_home / 'skills' / 'planner-task-packet' / 'SKILL.md'
    assert projected.is_file()
    assert 'readiness recommendations' in projected.read_text(encoding='utf-8')

from __future__ import annotations

from typer.testing import CliRunner

from clawteam.cli.commands import app
from clawteam.config import ClawTeamConfig, load_config, save_config
from clawteam.team.mailbox import MailboxManager
from clawteam.team.manager import TeamManager
from clawteam.team.models import MessageType


def test_config_cli_supports_all_keys_and_bool_values(tmp_path):
    runner = CliRunner()
    env = {
        "HOME": str(tmp_path),
        "CLAWTEAM_DATA_DIR": str(tmp_path / ".clawteam"),
    }

    result = runner.invoke(app, ["config", "set", "skip_permissions", "false"], env=env)
    assert result.exit_code == 0
    assert load_config().skip_permissions is False

    result = runner.invoke(app, ["config", "set", "workspace", "never"], env=env)
    assert result.exit_code == 0
    assert load_config().workspace == "never"

    result = runner.invoke(app, ["config", "set", "default_profile", "gemini-main"], env=env)
    assert result.exit_code == 0
    assert load_config().default_profile == "gemini-main"

    result = runner.invoke(app, ["config", "get", "workspace"], env=env)
    assert result.exit_code == 0
    assert "workspace = never" in result.output


def test_team_approve_join_errors_when_request_missing(tmp_path):
    runner = CliRunner()
    env = {
        "HOME": str(tmp_path),
        "CLAWTEAM_DATA_DIR": str(tmp_path / ".clawteam"),
        "CLAWTEAM_AGENT_ID": "leader001",
        "CLAWTEAM_AGENT_NAME": "leader",
    }

    TeamManager.create_team(
        name="demo",
        leader_name="leader",
        leader_id="leader001",
    )

    result = runner.invoke(app, ["team", "approve-join", "demo", "missing-req"], env=env)

    assert result.exit_code == 1
    assert "No join request found with id 'missing-req'" in result.output
    assert [member.name for member in TeamManager.list_members("demo")] == ["leader"]


def test_team_request_join_supports_no_wait_mode(tmp_path):
    runner = CliRunner()
    env = {
        "HOME": str(tmp_path),
        "CLAWTEAM_DATA_DIR": str(tmp_path / ".clawteam"),
        "CLAWTEAM_AGENT_ID": "worker001",
        "CLAWTEAM_AGENT_NAME": "worker",
    }

    TeamManager.create_team(
        name="demo",
        leader_name="leader",
        leader_id="leader001",
    )

    result = runner.invoke(
        app,
        ["team", "request-join", "demo", "worker", "--no-wait"],
        env=env,
    )

    assert result.exit_code == 0
    assert "Join request sent" in result.output
    assert "join-status demo" in result.output


def test_team_request_join_timeout_returns_pending_instead_of_error(tmp_path):
    runner = CliRunner()
    env = {
        "HOME": str(tmp_path),
        "CLAWTEAM_DATA_DIR": str(tmp_path / ".clawteam"),
        "CLAWTEAM_AGENT_ID": "worker001",
        "CLAWTEAM_AGENT_NAME": "worker",
    }

    TeamManager.create_team(
        name="demo",
        leader_name="leader",
        leader_id="leader001",
    )

    result = runner.invoke(
        app,
        ["team", "request-join", "demo", "worker", "--timeout", "0"],
        env=env,
    )

    assert result.exit_code == 0
    assert "Still pending." in result.output
    assert "join-status demo" in result.output


def test_team_join_status_reports_approval(tmp_path):
    runner = CliRunner()
    env = {
        "HOME": str(tmp_path),
        "CLAWTEAM_DATA_DIR": str(tmp_path / ".clawteam"),
        "CLAWTEAM_AGENT_ID": "worker001",
        "CLAWTEAM_AGENT_NAME": "worker",
    }

    TeamManager.create_team(
        name="demo",
        leader_name="leader",
        leader_id="leader001",
    )

    mailbox = MailboxManager("demo")
    mailbox.send(
        from_agent="leader",
        to="_pending_worker",
        msg_type=MessageType.join_approved,
        request_id="join-abc123",
        assigned_name="worker",
        agent_id="worker001",
        team_name="demo",
    )

    result = runner.invoke(
        app,
        ["team", "join-status", "demo", "join-abc123", "--proposed-name", "worker"],
        env=env,
    )

    assert result.exit_code == 0
    assert "Approved!" in result.output


def test_task_cli_supports_priority_create_update_and_list(tmp_path):
    runner = CliRunner()
    env = {
        "HOME": str(tmp_path),
        "CLAWTEAM_DATA_DIR": str(tmp_path / ".clawteam"),
    }

    create_result = runner.invoke(
        app,
        ["task", "create", "demo", "important work", "--priority", "urgent", "--owner", "alice"],
        env=env,
    )
    assert create_result.exit_code == 0
    assert "Priority: urgent" in create_result.output

    list_result = runner.invoke(
        app,
        ["task", "list", "demo", "--priority", "urgent", "--sort-priority"],
        env=env,
    )
    assert list_result.exit_code == 0
    assert "urgent" in list_result.output
    assert "important work" in list_result.output

    task_id = create_result.output.split("Task created: ")[1].splitlines()[0].strip()
    update_result = runner.invoke(
        app,
        ["task", "update", "demo", task_id, "--priority", "low"],
        env=env,
    )
    assert update_result.exit_code == 0

    get_result = runner.invoke(
        app,
        ["task", "get", "demo", task_id],
        env=env,
    )
    assert get_result.exit_code == 0
    assert "Priority: low" in get_result.output


def test_task_cli_accepts_agent_alias_for_owner(tmp_path):
    runner = CliRunner()
    env = {
        "HOME": str(tmp_path),
        "CLAWTEAM_DATA_DIR": str(tmp_path / ".clawteam"),
    }

    create_result = runner.invoke(
        app,
        ["task", "create", "demo", "important work", "--agent", "alice"],
        env=env,
    )
    assert create_result.exit_code == 0
    task_id = create_result.output.split("Task created: ")[1].splitlines()[0].strip()

    update_result = runner.invoke(
        app,
        ["task", "update", "demo", task_id, "--agent", "bob"],
        env=env,
    )
    assert update_result.exit_code == 0

    list_result = runner.invoke(
        app,
        ["task", "list", "demo", "--agent", "bob"],
        env=env,
    )
    assert list_result.exit_code == 0
    assert "important work" in list_result.output


def test_task_cli_rejects_circular_dependencies(tmp_path):
    runner = CliRunner()
    env = {
        "HOME": str(tmp_path),
        "CLAWTEAM_DATA_DIR": str(tmp_path / ".clawteam"),
    }

    first = runner.invoke(app, ["task", "create", "demo", "first"], env=env)
    second = runner.invoke(
        app,
        ["task", "create", "demo", "second", "--blocked-by", first.output.split("Task created: ")[1].splitlines()[0].strip()],
        env=env,
    )

    assert first.exit_code == 0
    assert second.exit_code == 0

    first_id = first.output.split("Task created: ")[1].splitlines()[0].strip()
    second_id = second.output.split("Task created: ")[1].splitlines()[0].strip()
    result = runner.invoke(
        app,
        ["task", "update", "demo", first_id, "--add-blocked-by", second_id],
        env=env,
    )

    assert result.exit_code == 1
    assert "cannot contain cycles" in result.output


def test_team_status_uses_configured_timezone(tmp_path):
    runner = CliRunner()
    env = {
        "HOME": str(tmp_path),
        "CLAWTEAM_DATA_DIR": str(tmp_path / ".clawteam"),
    }

    save_config(ClawTeamConfig(timezone="Asia/Shanghai"))
    TeamManager.create_team(
        name="demo",
        leader_name="leader",
        leader_id="leader001",
    )

    result = runner.invoke(app, ["team", "status", "demo"], env=env)

    assert result.exit_code == 0
    assert "CST" in result.output


def test_team_add_member_cli_adds_member_directly(tmp_path):
    runner = CliRunner()
    env = {
        "HOME": str(tmp_path),
        "CLAWTEAM_DATA_DIR": str(tmp_path / ".clawteam"),
        "CLAWTEAM_AGENT_ID": "leader001",
        "CLAWTEAM_AGENT_NAME": "leader",
    }

    TeamManager.create_team(
        name="demo",
        leader_name="leader",
        leader_id="leader001",
    )

    result = runner.invoke(
        app,
        ["team", "add-member", "demo", "worker", "--agent-type", "coder"],
        env=env,
    )

    assert result.exit_code == 0
    members = TeamManager.list_members("demo")
    assert [member.name for member in members] == ["leader", "worker"]
    assert members[1].agent_type == "coder"


def test_board_update_cli_is_a_compatibility_alias(tmp_path):
    runner = CliRunner()
    env = {
        "HOME": str(tmp_path),
        "CLAWTEAM_DATA_DIR": str(tmp_path / ".clawteam"),
    }

    TeamManager.create_team(
        name="demo",
        leader_name="leader",
        leader_id="leader001",
    )

    result = runner.invoke(app, ["board", "update", "demo", "--agent", "worker"], env=env)

    assert result.exit_code == 0
    assert "derived automatically" in result.output


def test_lifecycle_check_zombies_reports_clean_state(monkeypatch, tmp_path):
    runner = CliRunner()
    env = {
        "HOME": str(tmp_path),
        "CLAWTEAM_DATA_DIR": str(tmp_path / ".clawteam"),
    }

    monkeypatch.setattr("clawteam.spawn.registry.list_zombie_agents", lambda team, max_hours=2.0: [])

    result = runner.invoke(app, ["lifecycle", "check-zombies", "--team", "demo"], env=env)

    assert result.exit_code == 0
    assert "No zombie agents detected" in result.output


def test_lifecycle_check_zombies_exits_nonzero_when_found(monkeypatch, tmp_path):
    runner = CliRunner()
    env = {
        "HOME": str(tmp_path),
        "CLAWTEAM_DATA_DIR": str(tmp_path / ".clawteam"),
    }

    monkeypatch.setattr(
        "clawteam.spawn.registry.list_zombie_agents",
        lambda team, max_hours=2.0: [
            {
                "agent_name": "worker",
                "pid": 4321,
                "backend": "subprocess",
                "spawned_at": 0.0,
                "running_hours": 3.5,
            }
        ],
    )

    result = runner.invoke(app, ["lifecycle", "check-zombies", "--team", "demo"], env=env)

    assert result.exit_code == 1
    assert "zombie agent(s) detected" in result.output
    assert "worker" in result.output
    assert "process manager" in result.output

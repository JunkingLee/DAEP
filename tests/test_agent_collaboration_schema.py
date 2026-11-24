import sqlite3

import app.main as main_module
from app.agent_identity import ensure_agent_schema


def test_agent_team_collaboration_initial_schema_contract():
    main_module.init()
    ensure_agent_schema(main_module.conn)

    expected_tables = {
        "agent_task_execution_policies",
        "agent_task_grants",
        "agent_task_contributions",
        "agent_collaboration_sessions",
        "agent_collaboration_grants",
        "agent_collaboration_messages",
        "agent_collaboration_proposals",
    }
    with main_module.conn() as c:
        tables = {
            row["name"]
            for row in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert expected_tables <= tables

        grant_columns = {
            row["name"] for row in c.execute(
                "PRAGMA table_info(agent_task_grants)"
            ).fetchall()
        }
        assert "legacy_assignment_id" not in grant_columns

        indexes = c.execute("PRAGMA index_list(agent_task_grants)").fetchall()
        active_index = next(
            row for row in indexes
            if row["name"] == "uq_agent_task_grants_active_task_agent"
        )
        assert active_index["unique"] == 1
        active_columns = [
            row["name"] for row in c.execute(
                "PRAGMA index_info(uq_agent_task_grants_active_task_agent)"
            ).fetchall()
        ]
        assert active_columns == ["task_id", "agent_id"]

        policy_columns = {
            row["name"] for row in c.execute(
                "PRAGMA table_info(agent_task_execution_policies)"
            ).fetchall()
        }
        assert {"allow_multiple_agents", "max_agents", "collaboration_mode",
                "responsible_member_id", "policy_version"} <= policy_columns

        session_indexes = c.execute(
            "PRAGMA index_list(agent_collaboration_sessions)"
        ).fetchall()
        assert any(row["unique"] == 1 for row in session_indexes)

        collab_indexes = c.execute(
            "PRAGMA index_list(agent_collaboration_grants)"
        ).fetchall()
        assert any(
            row["name"] == "uq_agent_collaboration_grants_active_session_agent"
            and row["unique"] == 1
            for row in collab_indexes
        )

        message_columns = {
            row["name"] for row in c.execute(
                "PRAGMA table_info(agent_collaboration_messages)"
            ).fetchall()
        }
        assert {"session_id", "author_type", "author_member_id",
                "author_agent_id", "agent_owner_member_id",
                "collaboration_grant_id"} <= message_columns

        proposal_columns = {
            row["name"] for row in c.execute(
                "PRAGMA table_info(agent_collaboration_proposals)"
            ).fetchall()
        }
        assert {"proposal_type", "proposed_by_agent_id",
                "collaboration_grant_id", "status", "decided_by_member_id"} <= proposal_columns


def test_team_policy_accepts_unbounded_agent_count_in_initial_schema():
    main_module.init()
    ensure_agent_schema(main_module.conn)
    with main_module.conn() as c:
        c.execute(
            """INSERT INTO projects(id,name,description,created_by,created_at,tenant_id)
               VALUES('schema-team-project','Schema Team Project','', 'member-admin',
                      '2026-11-24T00:00:00+00:00','tenant-default')"""
        )
        c.execute(
            """INSERT INTO requirements(id,project_id,title,description,acceptance_criteria,status,created_at)
               VALUES('schema-team-requirement','schema-team-project','Requirement','','[]','OPEN',
                      '2026-11-24T00:00:00+00:00')"""
        )
        c.execute(
            """INSERT INTO tasks(id,requirement_id,title,description,status,progress,created_at,updated_at)
               VALUES('schema-team-task','schema-team-requirement','Task','','READY',0,
                      '2026-11-24T00:00:00+00:00','2026-11-24T00:00:00+00:00')"""
        )
        c.execute(
            """INSERT INTO agent_task_execution_policies(
                   id,tenant_id,project_id,task_id,responsible_member_id,
                   allow_multiple_agents,max_agents,collaboration_mode,
                   policy_version,created_at,updated_at
               ) VALUES(?,?,?,?,?,1,NULL,'TEAM',1,?,?)""",
            ("schema-team-policy","tenant-default","schema-team-project",
             "schema-team-task","member-admin",
             "2026-11-24T00:00:00+00:00","2026-11-24T00:00:00+00:00"),
        )
        policy = c.execute(
            "SELECT allow_multiple_agents,max_agents,collaboration_mode "
            "FROM agent_task_execution_policies WHERE task_id='schema-team-task'"
        ).fetchone()
        assert policy["allow_multiple_agents"] == 1
        assert policy["max_agents"] is None
        assert policy["collaboration_mode"] == "TEAM"

        try:
            c.execute(
                """INSERT INTO agent_task_execution_policies(
                       id,tenant_id,project_id,task_id,responsible_member_id,
                       allow_multiple_agents,max_agents,collaboration_mode,
                       policy_version,created_at,updated_at
                   ) VALUES('duplicate-policy','tenant-default','schema-team-project',
                            'schema-team-task','member-admin',1,NULL,'TEAM',1,?,?)""",
                ("2026-11-24T00:00:00+00:00","2026-11-24T00:00:00+00:00"),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("A Task must have at most one execution policy")


def test_multiple_agent_grants_share_one_task_but_duplicate_agent_is_rejected():
    main_module.init()
    ensure_agent_schema(main_module.conn)
    with main_module.conn() as c:
        c.execute(
            """INSERT INTO projects(id,name,description,created_by,created_at,tenant_id)
               VALUES('schema-multi-project','Schema Multi Project','', 'member-admin',
                      '2026-11-24T00:00:00+00:00','tenant-default')"""
        )
        c.execute(
            """INSERT INTO requirements(id,project_id,title,description,acceptance_criteria,status,created_at)
               VALUES('schema-multi-requirement','schema-multi-project','Requirement','','[]','OPEN',
                      '2026-11-24T00:00:00+00:00')"""
        )
        c.execute(
            """INSERT INTO tasks(id,requirement_id,title,description,status,progress,created_at,updated_at)
               VALUES('schema-multi-task','schema-multi-requirement','Task','','READY',0,?,?)""",
            ("2026-11-24T00:00:00+00:00","2026-11-24T00:00:00+00:00"),
        )
        for agent_id in ("schema-agent-one", "schema-agent-two"):
            c.execute(
                """INSERT INTO agents(id,owner_member_id,tenant_id,name,description,status,created_at,updated_at)
                   VALUES(?, 'member-admin','tenant-default',?,'','ACTIVE',?,?)""",
                (agent_id, agent_id, "2026-11-24T00:00:00+00:00",
                 "2026-11-24T00:00:00+00:00"),
            )
            c.execute(
                """INSERT INTO agent_task_grants(
                       id,tenant_id,project_id,task_id,agent_id,owner_member_id,
                       human_assignee_member_id,authorized_by_member_id,scope_json,
                       status,created_at,updated_at,expires_at
                   ) VALUES(?,?,?,?,?,?,?,?,'["task.read"]','AUTHORIZED',?,?,?)""",
                ("schema-grant-" + agent_id,"tenant-default","schema-multi-project",
                 "schema-multi-task",agent_id,"member-admin","member-admin","member-admin",
                 "2026-11-24T00:00:00+00:00","2026-11-24T00:00:00+00:00",
                 "2026-12-24T00:00:00+00:00"),
            )

        active_count = c.execute(
            """SELECT count(*) AS n FROM agent_task_grants
               WHERE task_id='schema-multi-task' AND status IN ('AUTHORIZED','ACCEPTED')"""
        ).fetchone()["n"]
        assert active_count == 2

        try:
            c.execute(
                """INSERT INTO agent_task_grants(
                       id,tenant_id,project_id,task_id,agent_id,owner_member_id,
                       human_assignee_member_id,authorized_by_member_id,scope_json,
                       status,created_at,updated_at,expires_at
                   ) VALUES('schema-duplicate-agent-grant','tenant-default',
                            'schema-multi-project','schema-multi-task','schema-agent-one',
                            'member-admin','member-admin','member-admin','["task.read"]',
                            'AUTHORIZED',?,?,?)""",
                ("2026-11-24T00:00:00+00:00","2026-11-24T00:00:00+00:00",
                 "2026-12-24T00:00:00+00:00"),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("The same Agent cannot hold duplicate active grants for one Task")

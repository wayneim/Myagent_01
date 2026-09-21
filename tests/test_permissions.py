from myagent.security.permissions import PermissionEffect, PermissionEngine, PermissionRule


def test_last_matching_rule_wins() -> None:
    engine = PermissionEngine([
        PermissionRule("shell", "*", PermissionEffect.DENY),
        PermissionRule("shell", "git status*", PermissionEffect.ALLOW),
    ])
    assert engine.check("shell", "git status --short")
    assert not engine.check("shell", "python build.py")

from myagent.security.permissions import PermissionEffect, PermissionEngine, PermissionRule


def test_deny_cannot_be_overridden_by_later_allow() -> None:
    engine = PermissionEngine([
        PermissionRule("shell", "*", PermissionEffect.DENY),
        PermissionRule("shell", "git status*", PermissionEffect.ALLOW),
    ])
    assert not engine.check("shell", "git status --short")
    assert not engine.check("shell", "python build.py")


def test_specific_allow_can_override_ask_but_not_deny() -> None:
    engine = PermissionEngine([
        PermissionRule("shell", "*", PermissionEffect.ASK),
        PermissionRule("shell", "git status*", PermissionEffect.ALLOW),
    ])
    assert engine.check("shell", "git status --short")
    assert not engine.check("shell", "python build.py")

from myagent.security.permissions import CliApprovalHandler


def test_cli_approval_accepts_yes() -> None:
    output: list[str] = []
    handler = CliApprovalHandler(lambda _: "yes", output.append)
    assert handler.approve("edit", "file.txt")
    assert output == ["Permission required: edit file.txt"]


def test_cli_approval_rejects_other_answers() -> None:
    handler = CliApprovalHandler(lambda _: "no", lambda _: None)
    assert not handler.approve("shell", "python build.py")

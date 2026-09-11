from __future__ import annotations

from io import StringIO

from pitblu_core.terminal import CheckResult, ResultLevel, Terminal, safe_text


class TtyBuffer(StringIO):
    def isatty(self) -> bool:
        return True


def test_safe_text_removes_terminal_controls_and_newlines() -> None:
    assert safe_text("device\x1b[31m\nname") == "device?[31m name"


def test_results_are_meaningful_without_colour() -> None:
    output = StringIO()
    terminal = Terminal(output_stream=output, environ={})

    level = terminal.results([CheckResult(ResultLevel.WARN, "Bluetooth", "not ready")])

    assert level is ResultLevel.WARN
    assert output.getvalue() == "WARN  Bluetooth: not ready\n"


def test_colour_requires_tty_and_respects_no_color() -> None:
    coloured = TtyBuffer()
    Terminal(output_stream=coloured, environ={}).result(
        CheckResult(ResultLevel.PASS, "API", "ready")
    )
    plain = TtyBuffer()
    Terminal(output_stream=plain, environ={"NO_COLOR": "1"}).result(
        CheckResult(ResultLevel.PASS, "API", "ready")
    )

    assert "\033[32mPASS\033[0m" in coloured.getvalue()
    assert "\033" not in plain.getvalue()


def test_confirm_defaults_to_no_and_reprompts() -> None:
    answers = iter(["perhaps", ""])
    output = StringIO()
    terminal = Terminal(output_stream=output, input_fn=lambda _prompt: next(answers))

    assert terminal.confirm("Install dependencies?") is False
    assert "Please answer y or n." in output.getvalue()


def test_secret_uses_hidden_input_function() -> None:
    prompts: list[str] = []
    terminal = Terminal(secret_fn=lambda prompt: prompts.append(prompt) or "secret")

    assert terminal.secret("Administrator token") == "secret"
    assert prompts == ["Administrator token: "]

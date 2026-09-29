from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


def test_public_demo_exposes_review_cases_and_complete_export_bundle():
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    assert not app.exception

    labels = app.selectbox[0].options
    assert any(label.startswith("A02 ·") for label in labels)
    assert any(label.startswith("U04 ·") for label in labels)
    assert any(label.startswith("R02 ·") for label in labels)

    generate = next(button for button in app.button if button.label == "生成候选规则")
    generate.click().run(timeout=30)
    assert not app.exception
    assert {button.label for button in app.get("download_button")} == {
        "下载完整验证包（ZIP，推荐）",
        "下载 Home Assistant YAML",
        "下载验证报告",
    }


def test_blocked_simulation_does_not_hide_export_explanation():
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    u04 = next(label for label in app.selectbox[0].options if label.startswith("U04 ·"))
    app.selectbox[0].set_value(u04).run(timeout=30)

    next(button for button in app.button if button.label == "生成候选规则").click().run(timeout=30)
    next(button for button in app.button if button.label == "运行状态仿真").click().run(timeout=30)

    assert not app.exception
    messages = [error.value for error in app.error]
    assert any("不能仿真可执行规则" in message for message in messages)
    assert any("YAML 下载已关闭" in message for message in messages)
    assert not app.get("download_button")

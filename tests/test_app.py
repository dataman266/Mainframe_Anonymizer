from streamlit.testing.v1 import AppTest


def test_app_boots_without_exception():
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    assert not at.exception
    assert at.title[0].value == "🛡️ Mainframe File Anonymizer"


def test_upload_step_asks_for_both_files():
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    assert any("Upload both files" in info.value for info in at.info)

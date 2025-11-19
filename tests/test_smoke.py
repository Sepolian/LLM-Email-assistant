from llm_email_app.main import run_sample_pipeline


def test_sample_pipeline_runs():
    assert run_sample_pipeline() is True

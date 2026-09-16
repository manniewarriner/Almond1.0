import asyncio

from almond_ai.evaluation.runner import EvaluationRunner


def test_evaluation_runner_records_measured_pass():
    async def exercise():
        runner = EvaluationRunner()
        result = await runner.run("tool-permissions", lambda: (True, "denied correctly"))
        assert result.passed is True
        assert result.detail == "denied correctly"
        assert result.latency_ms >= 0
        assert runner.list()[2].status == "pass"

    asyncio.run(exercise())


def test_evaluation_runner_records_probe_failure():
    async def exercise():
        runner = EvaluationRunner()

        def broken_probe():
            raise RuntimeError("probe broke")

        result = await runner.run("retrieval-baseline", broken_probe)
        assert result.passed is False
        assert "probe broke" in result.detail
        assert runner.list()[1].status == "fail"

    asyncio.run(exercise())

from taskpps.domain import task as domain_task_module


def test_domain_task_exports():
    assert hasattr(domain_task_module, "ResolvedPipeline")
    assert hasattr(domain_task_module, "ResolvedTask")
    assert "__all__" in dir(domain_task_module)
    assert "ResolvedPipeline" in domain_task_module.__all__
    assert "ResolvedTask" in domain_task_module.__all__

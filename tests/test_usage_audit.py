from agentkit.db.repositories import AuditRepo, Repositories, UsageRepo


def test_usage_repo_totals(repos: Repositories):
    repos.usage.add(conversation_id="cli:1", requests=1, input_tokens=10, output_tokens=5, total_tokens=15)
    repos.usage.add(conversation_id="cli:1", requests=2, input_tokens=20, output_tokens=8, total_tokens=28)
    totals = repos.usage.totals()
    assert totals == {
        "requests": 3,
        "input_tokens": 30,
        "output_tokens": 13,
        "total_tokens": 43,
        "cost_usd": 0.0,
    }


def test_audit_chain_verifies(repos: Repositories):
    repos.audit.append("transaction.create", target="txn:1", detail={"amount_minor": 500}, actor="owner")
    repos.audit.append("transaction.delete", target="txn:1", actor="owner")
    assert repos.audit.verify() is True
    assert len(repos.audit.entries()) == 2


def test_audit_tamper_detected(repos: Repositories):
    repos.audit.append("a", target="x")
    repos.audit.append("b", target="y")
    entry = repos.audit.entries()[0]
    entry.action = "tampered"
    repos.session.add(entry)
    repos.session.flush()
    assert repos.audit.verify() is False


def test_repos_expose_usage_and_audit(repos: Repositories):
    assert isinstance(repos.usage, UsageRepo)
    assert isinstance(repos.audit, AuditRepo)

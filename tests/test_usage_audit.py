from agentkit.db.repositories import AuditRepo, Repositories, UsageRepo


async def test_usage_repo_totals(repos: Repositories):
    await repos.usage.add(
        conversation_id="cli:1", requests=1, input_tokens=10, output_tokens=5, total_tokens=15
    )
    await repos.usage.add(
        conversation_id="cli:1", requests=2, input_tokens=20, output_tokens=8, total_tokens=28
    )
    totals = await repos.usage.totals()
    assert totals == {
        "requests": 3,
        "input_tokens": 30,
        "output_tokens": 13,
        "total_tokens": 43,
        "cost_usd": 0.0,
    }


async def test_audit_chain_verifies(repos: Repositories):
    await repos.audit.append(
        "transaction.create", target="txn:1", detail={"amount_minor": 500}, actor="owner"
    )
    await repos.audit.append("transaction.delete", target="txn:1", actor="owner")
    assert await repos.audit.verify() is True
    assert len(await repos.audit.entries()) == 2


async def test_audit_tamper_detected(repos: Repositories):
    await repos.audit.append("a", target="x")
    await repos.audit.append("b", target="y")
    entry = (await repos.audit.entries())[0]
    entry.action = "tampered"
    repos.session.add(entry)
    await repos.session.flush()
    assert await repos.audit.verify() is False


async def test_repos_expose_usage_and_audit(repos: Repositories):
    assert isinstance(repos.usage, UsageRepo)
    assert isinstance(repos.audit, AuditRepo)

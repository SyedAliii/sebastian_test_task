async def test_fair_pop_alternates(redis_client) -> None:
    from app.repo.queues import Queues

    for index in range(10):
        await redis_client.rpush("queue:ws_unverified", f"u{index}")
    await redis_client.rpush("queue:ws_verified", "v0", "v1")
    queues = Queues(redis_client)
    prefer = "ws_verified"
    seen = []
    ids = []
    for _ in range(4):
        popped = await queues.pop_fair(prefer)
        assert popped is not None
        workspace_id, job_id = popped
        seen.append(workspace_id)
        ids.append(job_id)
        prefer = "ws_unverified" if workspace_id == "ws_verified" else "ws_verified"
    assert seen == ["ws_verified", "ws_unverified", "ws_verified", "ws_unverified"]
    assert ids[0] == "v0"
    assert ids[-1] != "v0"

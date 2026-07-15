import asyncio
import tempfile
import os

fd, p = tempfile.mkstemp(suffix='.db')
os.close(fd)

async def t():
    from app.agents.graph import ChatWorkflow
    w = ChatWorkflow('sk-test', 'https://test', db_path=p)
    await w._ensure_checkpointer()
    edges = w.app.get_graph().edges
    print('type:', type(edges))
    for e in edges:
        print(repr(e))
    os.unlink(p)

asyncio.run(t())

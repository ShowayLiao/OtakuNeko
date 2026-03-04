import asyncio
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from app.services.bangumi_client import bangumi_client

async def test_get_persons_raw():
    # 初始化 FastAPICache
    FastAPICache.init(InMemoryBackend())
    
    # 测试一个已知的动画 Bangumi ID
    subject_id = 1867  # ONE PIECE OVA
    
    print(f"Testing get_persons_raw with subject_id: {subject_id}")
    
    try:
        result = await bangumi_client.get_persons_raw(subject_id)
        print(f"\nTest result:")
        print(f"Type: {type(result)}")
        print(f"Length: {len(result)}")
        
        if result:
            # 显示第一个 person 的数据结构
            print(f"\nFirst person data:")
            print(f"Keys: {list(result[0].keys())}")
            
            # 显示 relations 字段
            relations = result[0].get('relations', [])
            print(f"\nRelations ({len(relations)}):")
            for i, relation in enumerate(relations[:3]):  # 只显示前3个关系
                print(f"Relation {i+1}:")
                print(f"  Keys: {list(relation.keys())}")
                print(f"  Name: {relation.get('name')}")
                print(f"  Actors: {relation.get('actors', [])}")
                
    except Exception as e:
        print(f"Test failed with error: {e}")
    finally:
        # 清理 FastAPICache
        await FastAPICache.clear()

if __name__ == "__main__":
    asyncio.run(test_get_persons_raw())

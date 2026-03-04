import asyncio
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from app.services.bangumi_service import fetch_subject_by_id

async def test_fetch_subject_by_id():
    # 初始化 FastAPICache
    FastAPICache.init(InMemoryBackend())
    
    # 测试一个已知的 Bangumi ID，比如 "鬼灭之刃" 第一季的 ID
    subject_id = 100444
    
    print(f"Testing fetch_subject_by_id with subject_id: {subject_id}")
    
    try:
        result = await fetch_subject_by_id(subject_id)
        print("\nTest result:")
        print(f"Type: {type(result)}")
        
        # 转成 dict
        result_dict = result.model_dump(exclude_none=True)
        print(f"Keys: {list(result_dict.keys())}")
        
        print(f"\nAnime Info:")
        print(f"ID: {result_dict.get('id')}")
        print(f"Name: {result_dict.get('name')}")
        print(f"Name CN: {result_dict.get('name_cn')}")
        print(f"Summary: {result_dict.get('summary', '')[:100]}...")
        print(f"Score: {result_dict.get('score')}")
        print(f"Rank: {result_dict.get('rank')}")
        
        # 测试新增的 main_cast 字段
        main_cast = result_dict.get('main_cast', [])
        print(f"\nMain Cast ({len(main_cast)}):")
        for cast in main_cast[:3]:  # 只显示前3个角色
            print(f"- {cast.get('character_name')} ({cast.get('role')}): {', '.join(cast.get('cv_names', []))}")
        
        # 测试 core_staff 字段
        core_staff = result_dict.get('core_staff', [])
        print(f"\nCore Staff ({len(core_staff)}):")
        for staff in core_staff[:3]:  # 只显示前3个 staff
            print(f"- {staff.get('name')}: {staff.get('role')}")
            
    except Exception as e:
        print(f"Test failed with error: {e}")
    finally:
        # 清理 FastAPICache
        FastAPICache.clear()

if __name__ == "__main__":
    asyncio.run(test_fetch_subject_by_id())

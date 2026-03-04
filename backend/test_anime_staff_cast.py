import asyncio
from app.services.bangumi_service import get_staff_info, get_cast_info

async def test_get_staff_info():
    # 测试一个已知的 Bangumi ID，比如 "四月是你的谎言" 的 ID
    subject_id = 100444
    
    print(f"Testing get_staff_info with subject_id: {subject_id}")
    
    try:
        result = await get_staff_info(subject_id)
        print("\nTest result:")
        print(f"Type: {type(result)}")
        print(f"Length: {len(result)}")
        
        print("\nStaff Info:")
        for i, staff in enumerate(result[:5]):  # 只显示前5个 staff
            print(f"{i+1}. {staff.name}: {staff.role}")
            
    except Exception as e:
        print(f"Test failed with error: {e}")

async def test_get_cast_info():
    # 测试一个已知的 Bangumi ID，比如 "四月是你的谎言" 的 ID
    subject_id = 100444
    
    print(f"\nTesting get_cast_info with subject_id: {subject_id}")
    
    try:
        result = await get_cast_info(subject_id)
        print("\nTest result:")
        print(f"Type: {type(result)}")
        print(f"Length: {len(result)}")
        
        print("\nCast Info:")
        for i, cast in enumerate(result[:5]):  # 只显示前5个角色
            print(f"{i+1}. {cast.character_name} ({cast.role}): {', '.join(cast.cv_names)}")
            
    except Exception as e:
        print(f"Test failed with error: {e}")

async def main():
    await test_get_staff_info()
    await test_get_cast_info()

if __name__ == "__main__":
    asyncio.run(main())

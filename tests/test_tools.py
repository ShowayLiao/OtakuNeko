#!/usr/bin/env python3
"""
测试 app/agents/tools.py 中的 get_anime_info 函数的可用性
"""

import asyncio
from app.agents.tools import get_anime_info

async def test_get_anime_info():
    """测试获取动漫信息的函数"""
    print("测试 get_anime_info 函数...")
    
    # 使用一个有效的 Bangumi 条目 ID 进行测试
    # 例如：进击的巨人 第一季 (ID: 5114)
    subject_id = 5114
    
    try:
        # 调用函数获取动漫信息
        result = await get_anime_info(subject_id)
        
        # 打印结果
        print(f"\n测试结果 (Bangumi ID: {subject_id}):")
        print("=" * 80)
        
        if "error" in result:
            # 打印错误信息
            print(f"错误: {result['error']}")
        else:
            # 打印成功结果
            print(f"名称: {result.get('name', 'N/A')}")
            print(f"中文名称: {result.get('name_cn', 'N/A')}")
            print(f"评分: {result.get('score', 'N/A')}")
            print(f"排名: {result.get('rank', 'N/A')}")
            print(f"\n简介:")
            print(result.get('summary', 'N/A'))
            
            # 打印核心制作人员
            core_staff = result.get('core_staff', [])
            if core_staff:
                print(f"\n核心制作人员:")
                for staff in core_staff:
                    print(f"  - {staff.get('name', 'N/A')}: {staff.get('role', 'N/A')}")
        
        print("=" * 80)
        print("测试完成")
        
    except Exception as e:
        print(f"测试失败: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_get_anime_info())

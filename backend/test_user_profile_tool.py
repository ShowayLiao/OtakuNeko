#!/usr/bin/env python3
"""
测试用户画像生成工具
"""

import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.agents.tools import generate_user_profile_tool

# 模拟用户收藏数据
def create_mock_collections():
    """创建模拟的用户收藏数据"""
    return [
        {
            "collection": {
                "rate": 8,  # 评分8分
                "type": 2,  # 看过
                "comment": "非常治愈的动画"
            },
            "subject": {
                "id": 1001,
                "name": "日常",
                "name_cn": "日常",
                "tags": [
                    {"name": "治愈"},
                    {"name": "日常"},
                    {"name": "搞笑"}
                ]
            }
        },
        {
            "collection": {
                "rate": 9,  # 评分9分
                "type": 2,  # 看过
                "comment": "神作！"
            },
            "subject": {
                "id": 1002,
                "name": "Clannad",
                "name_cn": "Clannad",
                "tags": [
                    {"name": "治愈"},
                    {"name": "催泪"},
                    {"name": "校园"},
                    {"name": "恋爱"}
                ]
            }
        },
        {
            "collection": {
                "rate": 7,  # 评分7分
                "type": 2,  # 看过
                "comment": "还不错"
            },
            "subject": {
                "id": 1003,
                "name": "K-ON!",
                "name_cn": "轻音少女",
                "tags": [
                    {"name": "日常"},
                    {"name": "音乐"},
                    {"name": "校园"},
                    {"name": "萌系"}
                ]
            }
        },
        {
            "collection": {
                "rate": 6,  # 评分6分
                "type": 2,  # 看过
                "comment": "一般般"
            },
            "subject": {
                "id": 1004,
                "name": "Sword Art Online",
                "name_cn": "刀剑神域",
                "tags": [
                    {"name": "战斗"},
                    {"name": "冒险"},
                    {"name": "游戏"},
                    {"name": "科幻"}
                ]
            }
        },
        {
            "collection": {
                "rate": 9,  # 评分9分
                "type": 2,  # 看过
                "comment": "经典之作"
            },
            "subject": {
                "id": 1005,
                "name": "Fullmetal Alchemist: Brotherhood",
                "name_cn": "钢之炼金术师FA",
                "tags": [
                    {"name": "战斗"},
                    {"name": "热血"},
                    {"name": "冒险"},
                    {"name": "科幻"}
                ]
            }
        },
        {
            "collection": {
                "rate": 8,  # 评分8分
                "type": 2,  # 看过
                "comment": "很感人"
            },
            "subject": {
                "id": 1006,
                "name": "Anohana",
                "name_cn": "未闻花名",
                "tags": [
                    {"name": "治愈"},
                    {"name": "催泪"},
                    {"name": "日常"}
                ]
            }
        },
        {
            "collection": {
                "rate": 0,  # 没有评分（应该被过滤掉）
                "type": 2,  # 看过
                "comment": "还没看完"
            },
            "subject": {
                "id": 1007,
                "name": "Test Anime",
                "name_cn": "测试动画",
                "tags": [
                    {"name": "测试"}
                ]
            }
        }
    ]

async def test_user_profile_tool():
    """测试用户画像生成工具"""
    print("=== 测试用户画像生成工具 ===")
    
    # 创建模拟数据
    collections = create_mock_collections()
    print(f"模拟数据：{len(collections)}个收藏（其中1个无评分）")
    
    # 调用工具
    print("\n调用generate_user_profile_tool...")
    result = await generate_user_profile_tool(collections)
    
    # 打印结果
    print(f"\n工具调用结果：")
    print(f"成功：{result.get('success', False)}")
    
    if result.get('success'):
        print(f"摘要：{result.get('summary', '')}")
        
        profile = result.get('profile', {})
        
        # 打印LLM摘要
        llm_summary = profile.get('llm_summary', {})
        print(f"\nLLM摘要：")
        print(f"  有效评分数量：{llm_summary.get('total_rated', 0)}")
        
        taste_dict = llm_summary.get('taste_dictionary', {})
        print(f"  标签全景字典（{len(taste_dict)}个标签）：")
        for tag, stats in taste_dict.items():
            print(f"    {tag}: 频次={stats[0]}, 平均分={stats[1]}")
        
        # 打印图表数据
        chart_data = profile.get('chart_data', {})
        print(f"\n图表数据：")
        
        radar_data = chart_data.get('radar', [])
        print(f"  雷达图数据（前{len(radar_data)}个标签）：")
        for item in radar_data:
            print(f"    {item.get('name')}: {item.get('value')}")
        
        bar_count_data = chart_data.get('bar_count', [])
        print(f"  频次柱状图数据（前{len(bar_count_data)}个标签）：")
        for item in bar_count_data:
            print(f"    {item.get('name')}: {item.get('value')}次")
        
        bar_score_data = chart_data.get('bar_score', [])
        print(f"  质量柱状图数据（前{len(bar_score_data)}个标签）：")
        for item in bar_score_data:
            print(f"    {item.get('name')}: {item.get('value')}分")
        
        # 打印观看ID列表
        watched_ids = profile.get('watched_ids', [])
        print(f"\n已观看动画ID列表（{len(watched_ids)}个）：")
        print(f"  {watched_ids}")
    
    else:
        print(f"错误：{result.get('error', '未知错误')}")
    
    print("\n=== 测试完成 ===")

async def test_edge_cases():
    """测试边界情况"""
    print("\n=== 测试边界情况 ===")
    
    # 测试空列表
    print("\n1. 测试空列表：")
    result = await generate_user_profile_tool([])
    print(f"  结果：{result.get('success', False)}")
    print(f"  摘要：{result.get('summary', '')}")
    
    # 测试无效数据
    print("\n2. 测试无效数据：")
    invalid_data = [
        {
            "collection": {"rate": None},  # 无评分
            "subject": {"tags": []}  # 无标签
        }
    ]
    result = await generate_user_profile_tool(invalid_data)
    print(f"  结果：{result.get('success', False)}")
    print(f"  有效评分：{result.get('profile', {}).get('llm_summary', {}).get('total_rated', 0)}")
    
    # 测试小样本数据
    print("\n3. 测试小样本数据：")
    small_sample = [
        {
            "collection": {"rate": 8},
            "subject": {
                "id": 2001,
                "tags": [{"name": "测试标签"}]
            }
        }
    ]
    result = await generate_user_profile_tool(small_sample)
    print(f"  结果：{result.get('success', False)}")
    print(f"  标签数量：{len(result.get('profile', {}).get('llm_summary', {}).get('taste_dictionary', {}))}")

async def main():
    """主函数"""
    try:
        await test_user_profile_tool()
        await test_edge_cases()
    except Exception as e:
        print(f"测试过程中发生错误：{e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
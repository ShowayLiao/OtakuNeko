import datetime
import pandas as pd
import streamlit as st

def generate_schedule_ui(decision_json):
    """
    排程核心逻辑：
    输入: AI 的决策 JSON {'weekday_show': 'xxx', 'weekend_movie': 'xxx'}
    输出: 在 Streamlit 界面渲染表格和指令
    """
    show_name = decision_json.get('weekday_show', 'AI未指定')
    movie_name = decision_json.get('weekend_movie', 'AI未指定')
    reason = decision_json.get('reason', '主人加油补番！')

    # 1. 界面反馈
    st.success(f"📅 规划完毕！\n\n📺 主力追番：**《{show_name}》**\n\n🎬 周末影院：**《{movie_name}》**\n\n💡 理由：{reason}")

    # 2. 算法：生成未来 7 天的时间表
    today = datetime.datetime.now()
    schedule_data = []
    
    # 定义映射
    week_map = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    
    for i in range(7):
        date = today + datetime.timedelta(days=i)
        date_str = date.strftime("%m月%d日")
        weekday = date.weekday() # 0=周一 ... 6=周日
        
        # 逻辑：周五(4)、周六(5) 看电影；其他时间(0,1,2,3,6) 看番
        if weekday in [4, 5]: 
            content = f"🎬 电影：《{movie_name}》"
            note = "周末影院 (20:00 - 22:00)"
        else:
            content = f"📺 剧集：《{show_name}》"
            note = "单线程补番 (22:00 - 24:00)"
            
        schedule_data.append({
            "日期": date_str,
            "星期": week_map[weekday],
            "推荐内容": content,
            "备注": note
        })

    # 3. 渲染 Pandas 表格
    df = pd.DataFrame(schedule_data)
    st.table(df)

    # 4. 生成手机日历指令
    cmd_text = f"""
请帮我创建日程：
1. 从今天开始，每晚22点提醒我看《{show_name}》（周日到周四）；
2. 这周五和周六晚上20点，提醒我看电影《{movie_name}》。
备注：{reason}
    """
    with st.expander("📱 点击复制手机日历指令"):
        st.code(cmd_text, language="text")
    
    # 返回一段文本用于存入聊天记录
    return f"📅 已生成排期表：主力《{show_name}》+ 周末《{movie_name}》"
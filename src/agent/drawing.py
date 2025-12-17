import os
import io
import textwrap
from PIL import Image, ImageDraw, ImageFont, ImageOps
import plotly.graph_objects as go
from src.BgmServe import bgm_service
import streamlit as st

# ==========================================
# 🔌 图表生成器 (Plotly -> PIL)
# ==========================================

def _generate_radar_pil(radar_data, size=(400, 350)):
    """生成静态雷达图"""
    if not radar_data: return None
    try:
        categories = list(radar_data.keys()) + [list(radar_data.keys())[0]]
        values = list(radar_data.values()) + [list(radar_data.values())[0]]

        fig = go.Figure(go.Scatterpolar(
            r=values, theta=categories, fill='toself',
            line_color='#FF4B4B', fillcolor='rgba(255, 75, 75, 0.2)',
            marker=dict(size=8, color='#FF4B4B')
        ))
        fig.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 100], showticklabels=False, gridcolor="rgba(180,180,180,0.3)"),
                angularaxis=dict(tickfont=dict(size=16, color="#333"), rotation=90, direction="clockwise")
            ),
            showlegend=False, 
            # 🔧 调整边距防止文字切边
            margin=dict(l=60, r=60, t=50, b=50),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            width=size[0], height=size[1]
        )
        
        img_bytes = fig.to_image(format="png", engine="kaleido", scale=2)
        img = Image.open(io.BytesIO(img_bytes))
        img.thumbnail(size, Image.Resampling.LANCZOS)
        return img
    except Exception as e:
        print(f"❌ 雷达图生成失败: {e}")
        return None

def _generate_pie_pil(comp_data, size=(400, 350)):
    """
    生成赛博风格甜甜圈饼图
    """
    if not comp_data: return None

    labels = [item.get('label', '?') for item in comp_data]
    values = [item.get('value', 0) for item in comp_data]
    colors = [item.get('color', '#888888') for item in comp_data]

    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values,
        marker=dict(colors=colors, line=dict(color='#FFF', width=2)),
        hole=0.5,
        textinfo='label+percent',
        textposition='outside',   
        textfont=dict(size=14, color='#333'), # 字体稍微加大
        showlegend=False
    )])

    fig.update_layout(
        # 🔧 核心修复：大幅增加边距，给 outside 的文字留出空间
        margin=dict(l=80, r=80, t=50, b=50),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        width=size[0], height=size[1]
    )
    
    try:
        img_bytes = fig.to_image(format="png", engine="kaleido", scale=2)
        img = Image.open(io.BytesIO(img_bytes))
        img.thumbnail(size, Image.Resampling.LANCZOS)
        return img
    except Exception as e:
        print(f"❌ 饼图生成失败: {e}")
        return None

# ==========================================
# 🎨 主绘图逻辑
# ==========================================

def draw_grid_image(items_data, output_filename="report.png", cols=4, 
                   title_text="OtakuNeko · 年度报告", subtitle_text=None, 
                   font_path="./font/AlibabaPuHuiTi-3-65-Medium.ttf",
                   user_name="None",
                   **kwargs):
    """
    主绘图函数
    """
    
    # 1. 提取外挂数据
    radar_data = kwargs.get('radar_data')
    comp_data = kwargs.get('composition_data')
    
    has_dashboard = bool(radar_data or comp_data)
    print(f"🎨 [Drawing] 绘制任务: {title_text} (含仪表盘: {has_dashboard})")

    # --- 基础配置 ---
    cell_w, cell_h = 220, 380
    margin = 40
    footer_h = 80
    dashboard_h = 430 if has_dashboard else 0

    # 字体加载
    def get_font(size):
        try: return ImageFont.truetype(font_path, size)
        except: return ImageFont.load_default()

    font_h1 = get_font(56)
    font_h2 = get_font(28)
    font_card_t = get_font(20)
    font_card_c = get_font(15) # 评论字体
    font_tag = get_font(13)

    # --- 计算总尺寸 ---
    header_h = 160 + (40 if subtitle_text else 0)
    
    count = len(items_data)
    rows = (count + cols - 1) // cols
    grid_h = rows * (cell_h + margin)

    total_w = max(1000, cols * (cell_w + margin) + margin)
    total_h = header_h + dashboard_h + grid_h + footer_h + 30

    canvas = Image.new('RGB', (total_w, total_h), (246, 247, 249))
    draw = ImageDraw.Draw(canvas)

    # --- 1. 绘制 Header ---
    curr_y = 60
    draw.text((margin, curr_y), title_text, font=font_h1, fill=(40, 40, 45))
    curr_y += 75
    if subtitle_text:
        draw.text((margin, curr_y), subtitle_text, font=font_h2, fill=(100, 100, 110))
        curr_y += 50
    
    draw.line([(margin, curr_y), (total_w - margin, curr_y)], fill=(220, 220, 230), width=2)
    curr_y += 30

    # --- 2. 绘制 Dashboard ---
    if has_dashboard:
        dash_y = curr_y
        half_w = (total_w - margin * 2) // 2
        
        # 左侧：雷达图
        if radar_data:
            draw.text((margin + 20, dash_y), "🧬 属性分析 / RADAR", font=font_h2, fill=(80, 80, 90))
            radar_img = _generate_radar_pil(radar_data, size=(450, 380))
            if radar_img:
                offset_x = margin + (half_w - 450) // 2
                canvas.paste(radar_img, (offset_x, dash_y + 40), mask=radar_img)

        # 右侧：饼图
        if comp_data:
            right_start_x = margin + half_w 
            draw.text((right_start_x + 20, dash_y), "🧪 核心成分 / COMPOSITION", font=font_h2, fill=(80, 80, 90))
            
            # 饼图尺寸稍作调整，配合 increased margin
            pie_img = _generate_pie_pil(comp_data, size=(480, 380))
            if pie_img:
                offset_x = right_start_x + (half_w - 480) // 2
                canvas.paste(pie_img, (offset_x, dash_y + 30), mask=pie_img)

        curr_y += dashboard_h
    
    # --- 3. 绘制 Grid ---
    for i, item in enumerate(items_data):
        col, row = i % cols, i // cols
        x = margin + col * (cell_w + margin)
        y = curr_y + row * (cell_h + margin)

        # 卡片背景
        draw.rounded_rectangle([x, y, x + cell_w, y + cell_h], radius=12, fill=(255, 255, 255))
        
        # 图片
        img_url = item.get('image')
        has_img = False
        if img_url:
            img = bgm_service.download_image(img_url)
            if img:
                try:
                    img = ImageOps.fit(img, (cell_w, 240), method=Image.LANCZOS)
                    mask = Image.new("L", (cell_w, 240), 0)
                    ImageDraw.Draw(mask).rounded_rectangle([(0,0), (cell_w, 240)], radius=12, fill=255)
                    ImageDraw.Draw(mask).rectangle([(0, 230), (cell_w, 240)], fill=255) 
                    canvas.paste(img, (x, y), mask=mask)
                    has_img = True
                except: pass
        
        if not has_img:
            draw.rounded_rectangle([x, y, x + cell_w, y + 240], radius=12, fill=(240, 240, 245))
            draw.text((x+60, y+110), "No Image", font=font_card_t, fill=(200, 200, 210))

        # 标签
        cat = item.get('category')
        if cat:
            cat_w = font_tag.getlength(cat) + 20
            draw.rounded_rectangle([x+10, y+10, x+10+cat_w, y+34], radius=4, fill=(50, 50, 50))
            draw.text((x+20, y+12), cat, font=font_tag, fill=(255, 255, 255))

        # 标题 (限制长度)
        text_y = y + 255
        title = item.get('title', 'Unknown')
        draw.text((x+15, text_y), title[:11] + ('...' if len(title)>11 else ''), font=font_card_t, fill=(40,40,40))
        
        # 评论/理由 (🔧 修复: 最多显示3行，超出省略)
        comment = item.get('reason') or item.get('comment')
        if comment:
            # textwrap.wrap 自动按宽度换行
            lines = textwrap.wrap(comment, width=13)
            
            # 截取前3行
            if len(lines) > 3:
                lines = lines[:3]
                # 第三行末尾加省略号
                if len(lines[-1]) > 0:
                     lines[-1] = lines[-1][:-1] + "..."
            
            text_y += 30 # 标题下方的间距
            for line in lines:
                draw.text((x+15, text_y), line, font=font_card_c, fill=(120,120,130))
                text_y += 20 # 行高
    
    # --- 4. Footer ---
    f_text = f"Generated by OtakuNeko | User: {user_name} | 基于 Bangumi 数据驱动"
    bbox = font_card_c.getbbox(f_text)
    f_x = (total_w - (bbox[2] - bbox[0])) // 2
    f_y = total_h - footer_h + 30
    draw.text((f_x, f_y), f_text, font=font_card_c, fill=(150, 150, 160))

    # 保存
    save_path = os.path.join("data", output_filename)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    canvas.save(save_path, quality=95)
    print(f"✅ 图片生成完毕: {save_path}")
    return save_path

def plot_radar_chart(radar_data):
    """
    绘制六维雷达图
    :param radar_data: 字典格式，例如 {"Hardcore": 80, "Love": 90...}
    """
    if not radar_data:
        st.warning("暂无雷达数据")
        return

    # 1. 数据预处理
    categories = list(radar_data.keys())
    values = list(radar_data.values())

    # ⚠️ 关键步骤：为了让线条闭合，必须把第一个点重复拼接到最后
    categories.append(categories[0])
    values.append(values[0])

    # 2. 创建 Plotly 图形
    fig = go.Figure()

    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=categories,
        fill='toself',          # 填充区域
        name='Otaku Stats',
        line_color='#FF4B4B',   # 线条颜色 (Streamlit 红，或者换成赛博紫 #9D00FF)
        fillcolor='rgba(255, 75, 75, 0.2)', # 半透明填充
        marker=dict(size=8)
    ))

    # 3. 样式美化 (去除去多余的网格线，使其更清爽)
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100], # 固定量程 0-100
                tickfont=dict(size=10, color="gray"), # 刻度字体
                gridcolor="rgba(128,128,128,0.2)",    # 网格颜色淡化
            ),
            angularaxis=dict(
                tickfont=dict(size=14, color="white" if st.get_option("theme.base")=="dark" else "black"),
                rotation=90, # 旋转一下，让第一个属性在正上方
                direction="clockwise"
            )
        ),
        showlegend=False,
        margin=dict(l=40, r=40, t=40, b=40), # 减少留白
        paper_bgcolor="rgba(0,0,0,0)",       # 背景透明，适配深色/浅色模式
        plot_bgcolor="rgba(0,0,0,0)",
        height=500  # 控制高度
    )

    # 4. 在 Streamlit 中渲染
    # use_container_width=True 让图表自适应列宽
    st.plotly_chart(fig, use_container_width=True)
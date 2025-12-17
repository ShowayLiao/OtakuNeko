# src/utils/drawing.py
import os
import textwrap
from PIL import Image, ImageDraw, ImageFont, ImageOps
from src.BgmServe import bgm_service

def draw_grid_image(items_data, output_filename="grid_output.png", cols=5, title_text="OtakuNeko · 成分鉴定", subtitle_text=None, font_path="./font/AlibabaPuHuiTi-3-65-Medium.ttf"):
    """
    🎨 Standalone utility to draw a grid image of anime cards.
    """
    print(f"🎨 [Drawing Util] 开始绘制图片: {title_text} | {subtitle_text}...")

    # --- 1. 基础配置 ---
    cell_w, cell_h = 220, 380
    margin, card_radius = 30, 12
    footer_h = 80

    # --- 颜色配置 ---
    bg_color = (246, 247, 249)
    card_bg_color = (255, 255, 255)
    card_outline = (225, 225, 230)
    title_color = (40, 40, 45)
    subtitle_color = (100, 100, 110)
    comment_color = (130, 130, 140)
    sub_text_color = (160, 160, 170)
    tag_bg_color = (235, 245, 255)
    tag_text_color = (0, 100, 200)
    accent_line_color = (50, 120, 255)

    # --- 字体加载 ---
    def load_font(size):
        try:
            return ImageFont.truetype(font_path, size)
        except IOError:
            print(f"⚠️ Font not found at {font_path}, using default.")
            return ImageFont.load_default()

    font_title = load_font(46)
    font_subtitle = load_font(26)
    font_card_title = load_font(19)
    font_comment = load_font(15)
    font_tag = load_font(14)
    font_footer = load_font(16)
    font_placeholder = load_font(24)

    # --- 布局计算 ---
    total_w = cols * (cell_w + margin) + margin
    header_top_padding = 50
    title_line_h, subtitle_line_h = 60, 36

    chars_per_line = int((total_w - margin * 2 - 20) / 48 * 1.8)
    title_lines = textwrap.wrap(title_text, width=chars_per_line)

    subtitle_lines = []
    if subtitle_text:
        sub_chars_per_line = int((total_w - margin * 2 - 20) / 26 * 1.9)
        subtitle_lines = textwrap.wrap(subtitle_text, width=sub_chars_per_line)

    header_content_h = len(title_lines) * title_line_h
    if subtitle_lines:
        header_content_h += 15 + (len(subtitle_lines) * subtitle_line_h)

    header_h = header_top_padding + header_content_h + 30

    # --- 准备画布 ---
    count = len(items_data)
    rows = (count + cols - 1) // cols
    total_h = header_h + rows * (cell_h + margin) + footer_h

    canvas = Image.new('RGB', (total_w, total_h), bg_color)
    draw = ImageDraw.Draw(canvas)

    # --- 绘制 Header ---
    accent_h = header_content_h + 4
    draw.rounded_rectangle([margin, header_top_padding + 8, margin + 6, header_top_padding + 8 + accent_h], radius=3, fill=accent_line_color)

    curr_y = header_top_padding
    for line in title_lines:
        draw.text((margin + 25, curr_y), line, font=font_title, fill=title_color)
        curr_y += title_line_h

    if subtitle_lines:
        curr_y += 10
        for line in subtitle_lines:
            draw.text((margin + 25, curr_y), line, font=font_subtitle, fill=subtitle_color)
            curr_y += subtitle_line_h

    # --- 循环绘制卡片 ---
    for i, item in enumerate(items_data):
        cat = item.get('category') or item.get('type') or ""
        title = str(item.get('title', 'Unknown'))
        comment = str(item.get('comment') or "")
        img_url = item.get('image')

        col, row = i % cols, i // cols
        x, y = margin + col * (cell_w + margin), header_h + row * (cell_h + margin)

        draw.rounded_rectangle([x, y, x + cell_w, y + cell_h], radius=card_radius, fill=card_bg_color, outline=card_outline, width=1)

        img_area_h = 240
        has_img = False
        if img_url:
            dl_img = bgm_service.download_image(img_url)
            if dl_img:
                try:
                    dl_img = ImageOps.fit(dl_img, (cell_w, img_area_h), method=Image.LANCZOS)
                    mask = Image.new("L", (cell_w, img_area_h), 0)
                    m_draw = ImageDraw.Draw(mask)
                    m_draw.rounded_rectangle([(0, 0), (cell_w, img_area_h + card_radius)], radius=card_radius, fill=255)
                    canvas.paste(dl_img, (x, y), mask=mask)
                    has_img = True
                except Exception as e:
                    print(f"Image processing error: {e}")

        if not has_img:
            draw.rounded_rectangle([x, y, x + cell_w, y + img_area_h], radius=card_radius, fill=(235, 235, 240))
            draw.rectangle([x, y + img_area_h - card_radius, x + cell_w, y + img_area_h], fill=(235, 235, 240))
            draw.text((x + cell_w // 2 - 45, y + img_area_h // 2 - 12), "No Image", font=font_placeholder, fill=(180, 180, 190))

        if cat:
            tag_txt = f"{cat}"
            bbox = font_tag.getbbox(tag_txt)
            tag_w, tag_h = bbox[2] - bbox[0] + 20, bbox[3] - bbox[1] + 10
            draw.rounded_rectangle([x + 10, y + 10, x + 10 + tag_w, y + 10 + tag_h], radius=6, fill=tag_bg_color)
            draw.text((x + 20, y + 15), tag_txt, font=font_tag, fill=tag_text_color)

        text_start_x = x + 15
        cursor_y = y + img_area_h + 12

        title_wrapper = textwrap.wrap(title, width=11)
        display_title = title_wrapper[:2]
        if len(title_wrapper) > 2:
            display_title[-1] += "..."

        for line in display_title:
            draw.text((text_start_x, cursor_y), line, font=font_card_title, fill=title_color)
            cursor_y += 24

        if comment and comment != "None":
            cursor_y += 6
            comment_wrapper = textwrap.wrap(comment, width=13)
            display_comment = comment_wrapper[:2]
            if len(comment_wrapper) > 2:
                display_comment[-1] += "..."

            for line in display_comment:
                draw.text((text_start_x, cursor_y), line, font=font_comment, fill=comment_color)
                cursor_y += 20

    # --- Footer ---
    footer_text = "OtakuNeko 基于AI以及动画记录生成，仅供娱乐"
    f_bbox = font_footer.getbbox(footer_text)
    f_x = (total_w - (f_bbox[2] - f_bbox[0])) // 2
    f_y = total_h - footer_h + 30

    draw.text((f_x, f_y), footer_text, font=font_footer, fill=sub_text_color)

    save_path = os.path.join("data", output_filename)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    canvas.save(save_path, quality=95)
    print(f"✅ 图片生成完毕: {save_path}")
    return save_path

import streamlit as st
import plotly.graph_objects as go

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
        margin=dict(l=40, r=40, t=20, b=20), # 减少留白
        paper_bgcolor="rgba(0,0,0,0)",       # 背景透明，适配深色/浅色模式
        plot_bgcolor="rgba(0,0,0,0)",
        height=400  # 控制高度
    )

    # 4. 在 Streamlit 中渲染
    # use_container_width=True 让图表自适应列宽
    st.plotly_chart(fig, use_container_width=True)

import os
import io
import textwrap
import threading
from PIL import Image, ImageDraw, ImageFont, ImageOps
import plotly.graph_objects as go
from src.BgmServe import BangumiService
import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

# 全局信号量，确保同一时间只有一个用户在进行图片合成操作
IMAGE_GENERATION_SEMAPHORE = threading.Semaphore(1)

# ==========================================
# 📦 缓存函数 (提高资源加载效率)
# ==========================================

@st.cache_resource
def get_cached_font_properties(font_path: str) -> FontProperties:
    """
    缓存matplotlib字体属性，避免重复加载
    """
    try:
        return FontProperties(fname=font_path)
    except:
        return FontProperties(family='sans-serif')

@st.cache_resource
def get_cached_pil_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    """
    缓存PIL字体对象，避免重复加载
    """
    try:
        return ImageFont.truetype(font_path, size)
    except:
        return ImageFont.load_default()

# ==========================================
# 🔌 图表生成器 (Plotly -> PIL)
# ==========================================

PLOTLY_FONT_FAMILY = "Alibaba PuHuiTi 3.0, Alibaba PuHuiTi 3, SimHei, Arial, sans-serif"

def _generate_radar_pil(radar_data, size=(450, 380), font_path="./font/AlibabaPuHuiTi-3-65-Medium.ttf"):
    if not radar_data: return None
    try:
        categories = list(radar_data.keys())
        values = list(radar_data.values())
        N = len(categories)

        # 闭合数据环
        angles = [n / float(N) * 2 * np.pi for n in range(N)]
        angles += angles[:1]
        values += values[:1]

        # 创建画布，背景透明
        fig = plt.figure(figsize=(size[0]/100, size[1]/100), dpi=100)
        try:
            ax = fig.add_subplot(111, polar=True)
            ax.set_facecolor('none')

            # 绘图：线条色和填充色
            ax.plot(angles, values, color='#FF4B4B', linewidth=2)
            ax.fill(angles, values, color='#FF4B4B', alpha=0.2)

            # 样式设置：起始点在正上方，顺时针方向
            ax.set_theta_offset(np.pi / 2)
            ax.set_theta_direction(-1)

            # 坐标轴美化
            ax.set_ylim(0, 100)
            ax.set_yticklabels([]) # 隐藏圈圈上的数字
            ax.grid(color='gray', alpha=0.2, linestyle='--')

            # 字体加载 - 使用缓存
            prop = get_cached_font_properties(font_path)

            # 设置轴标签
            ax.set_xticks(angles[:-1])
            ax.set_xticklabels(categories, fontproperties=prop, color='#333333', size=11)

            # 导出为 PIL 对象
            buf = io.BytesIO()
            plt.savefig(buf, format='png', transparent=True, bbox_inches='tight', pad_inches=0.1)
            return Image.open(buf)
        finally:
            plt.close(fig)
    except Exception as e:
        print(f"❌ Matplotlib 雷达图生成失败: {e}")
        return None

def _generate_pie_pil(comp_data, size=(480, 380), font_path="./font/AlibabaPuHuiTi-3-65-Medium.ttf"):
    if not comp_data: return None
    try:
        labels = [item.get('label', '?') for item in comp_data]
        values = [item.get('value', 0) for item in comp_data]
        colors = [item.get('color', '#888888') for item in comp_data]

        # 创建画布
        fig, ax = plt.subplots(figsize=(size[0]/100, size[1]/100), dpi=100)
        try:
            fig.patch.set_alpha(0) # 背景透明

            # 绘制甜甜圈 (wedgeprops 的 width 控制孔的大小)
            wedges, texts, autotexts = ax.pie(
                values, labels=labels, colors=colors,
                autopct='%1.1f%%', pctdistance=0.75,
                wedgeprops=dict(width=0.4, edgecolor='white', linewidth=2),
                startangle=90
            )

            # 字体处理 - 使用缓存
            prop = get_cached_font_properties(font_path)

            # 美化文字标签
            plt.setp(texts, fontproperties=prop, size=10, color='#333333')
            plt.setp(autotexts, fontproperties=prop, size=9, color='white', weight='bold')

            # 导出为 PIL 对象
            buf = io.BytesIO()
            plt.savefig(buf, format='png', transparent=True, bbox_inches='tight')
            return Image.open(buf)
        finally:
            plt.close(fig)
    except Exception as e:
        print(f"❌ Matplotlib 饼图生成失败: {e}")
        return None
    

# ==========================================
# 🎨 主绘图逻辑
# ==========================================

def draw_grid_image(bgm_service, items_data, output_filename="report.png", cols=4, 
                   title_text="OtakuNeko · 年度报告", subtitle_text=None, 
                   font_path="./font/AlibabaPuHuiTi-3-65-Medium.ttf",
                   user_name="None",
                   **kwargs):
    """
    主绘图函数
    """
    # 尝试获取信号量，确保同一时间只有一个用户在进行图片合成操作
    with st.spinner('服务器正在忙碌排队，请稍等...'):
        if not IMAGE_GENERATION_SEMAPHORE.acquire(timeout=300):  # 5分钟超时
            st.error('图片生成超时，请稍后重试')
            return None
    
    try:
        # 1. 提取外挂数据
        radar_data = kwargs.get('radar_data')
        comp_data = kwargs.get('composition_data')
        otaku_score = kwargs.get('otaku_score') # <--- 获取浓度分数
        
        has_dashboard = bool(radar_data or comp_data)
        print(f"🎨 [Drawing] 绘制任务: {title_text} (含仪表盘: {has_dashboard}, 浓度: {otaku_score})")

        # --- 基础配置 ---
        cell_w, cell_h = 220, 380
        margin = 40
        footer_h = 80
        dashboard_h = 430 if has_dashboard else 0

        # 字体加载 - 使用缓存
        font_h1 = get_cached_pil_font(font_path, 56)
        font_h2 = get_cached_pil_font(font_path, 28)
        font_bar_label = get_cached_pil_font(font_path, 22) # 进度条专用字体
        font_card_t = get_cached_pil_font(font_path, 20)
        font_card_c = get_cached_pil_font(font_path, 15)
        font_tag = get_cached_pil_font(font_path, 13)

        # --- 计算总尺寸 ---
        # 动态计算 Header 高度：如果有浓度条，增加 60px
        header_h = 160 + (40 if subtitle_text else 0) + (60 if otaku_score is not None else 0)
        
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
        
        # === 🔥 新增：二次元浓度进度条 ===
        if otaku_score is not None:
            # 布局参数
            bar_height = 16
            label_text = "二次元浓度"
            score_val = float(otaku_score)
            bar_color = "#FF4B4B" # 保持和雷达图一致的主题色
            bg_color = "#E0E0E0"  # 浅灰底色

            # 1. 绘制左侧标签 "二次元浓度"
            draw.text((margin, curr_y), label_text, font=font_bar_label, fill=(80, 80, 90))
            label_w = font_bar_label.getlength(label_text) + 20 # 文字宽度 + 间距

            # 2. 绘制右侧百分比 "85%"
            pct_text = f"{int(score_val)}%"
            pct_w = font_bar_label.getlength(pct_text) + 10
            draw.text((total_w - margin - pct_w + 10, curr_y), pct_text, font=font_bar_label, fill=bar_color)

            # 3. 绘制中间进度条
            # 计算进度条的起止 X 坐标
            bar_start_x = margin + label_w
            bar_end_x = total_w - margin - pct_w - 10
            bar_max_w = bar_end_x - bar_start_x
            
            # 垂直居中微调
            bar_y = curr_y + 8 

            # 画底槽 (灰色)
            draw.rounded_rectangle(
                [bar_start_x, bar_y, bar_end_x, bar_y + bar_height], 
                radius=bar_height//2, 
                fill=bg_color
            )
            
            # 画进度 (红色)
            fill_w = int(bar_max_w * (score_val / 100))
            if fill_w > 0:
                # 确保最小宽度不小于圆角，否则很难看，或者直接限制 min
                fill_w = max(fill_w, bar_height) 
                draw.rounded_rectangle(
                    [bar_start_x, bar_y, bar_start_x + fill_w, bar_y + bar_height], 
                    radius=bar_height//2, 
                    fill=bar_color
                )

            curr_y += 60 # 增加垂直间距，为下面留空

        # ================================

        # 分割线
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
            
            # 评论/理由
            comment = item.get('reason') or item.get('comment')
            if comment:
                lines = textwrap.wrap(comment, width=13)
                if len(lines) > 3:
                    lines = lines[:3]
                    if len(lines[-1]) > 0:
                         lines[-1] = lines[-1][:-1] + "..."
                
                text_y += 30
                for line in lines:
                    draw.text((x+15, text_y), line, font=font_card_c, fill=(120,120,130))
                    text_y += 20
        
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
    except Exception as e:
        print(f"❌ 图片生成失败: {e}")
        st.error(f"图片生成失败: {str(e)}")
        return None
    finally:
        # 无论成功还是失败，都必须释放信号量
        IMAGE_GENERATION_SEMAPHORE.release()

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
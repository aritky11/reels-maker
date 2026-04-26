import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import io
import os
import math

# --- 基本設定 ---
st.set_page_config(page_title="AIリール生成ツール", layout="wide")

# ファイルパス設定
FONT_PATH = "font.ttf"
BASE_IMAGE_PATH = "base.png"

# --- サイドバー（デザイン設定） ---
st.sidebar.title("⚙️ デザイン設定")

# 太字設定
st.sidebar.subheader("【太字・太さ設定】")
is_bold_title = st.sidebar.checkbox("タイトルを太字にする", value=True)
is_bold_body = st.sidebar.checkbox("本文を太字にする", value=False)
is_bold_footer = st.sidebar.checkbox("フッターを太字にする", value=True)
bold_thickness = st.sidebar.slider("太字の強度", 0.5, 5.0, 1.5, step=0.1)

# 位置・サイズの微調整（アコーディオン）
with st.sidebar.expander("位置・サイズ・行間の微調整"):
    size_title = st.slider("タイトル文字サイズ", 50, 150, 80)
    spacing_title = st.slider("タイトルの行間", 0, 100, 10) # 初期値を10に短縮
    y_title = st.slider("タイトル上下位置 (Y)", 50, 600, 160)
    
    st.markdown("---")
    size_body = st.slider("本文文字サイズ", 30, 100, 48)
    spacing_body = st.slider("本文の行間", 0, 100, 12) # 初期値を12に短縮（以前は30）
    y_body_offset = st.slider("本文位置の微調整", -500, 500, 0)
    
    st.markdown("---")
    size_footer = st.slider("フッター文字サイズ", 30, 100, 55)
    y_footer = st.slider("フッター上下位置 (Y)", 1500, 1900, 1670)

# --- メイン画面 ---
st.title("🎬 AIリール動画自動生成ツール")

col1, col2 = st.columns([1, 1.2]) 

with col1:
    st.subheader("📝 テキスト入力")
    title_input = st.text_area("① タイトル（『\\n』で改行）", "「都合のいい女」の\\nLINEには共通点がある", height=80)
    body_input = st.text_area("② 本文", height=350)
    footer_input = st.text_area("③ フッター", "保存して、次にLINEを打つ前に見返しなさい。", height=80)

def draw_styled_text(draw_obj, xy, text, font, fill, align, spacing, is_bold, thickness):
    x, y = xy
    if is_bold:
        for degrees in range(0, 360, 45):
            dx = thickness * math.cos(math.radians(degrees))
            dy = thickness * math.sin(math.radians(degrees))
            draw_obj.multiline_text((x+dx, y+dy), text, font=font, fill=fill, align=align, spacing=spacing)
    draw_obj.multiline_text((x, y), text, font=font, fill=fill, align=align, spacing=spacing)

def create_preview_image():
    if not os.path.exists(BASE_IMAGE_PATH): return None, "画像なし"
    img = Image.open(BASE_IMAGE_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)
    
    font_t = ImageFont.truetype(FONT_PATH, size_title)
    font_b = ImageFont.truetype(FONT_PATH, size_body)
    font_f = ImageFont.truetype(FONT_PATH, size_footer)

    title_text = title_input.replace('\\n', '\n')
    W, H = 1080, 1920

    # 1. タイトル
    bbox_t = draw.multiline_textbbox((0, 0), title_text, font=font_t, align="center", spacing=spacing_title)
    draw_styled_text(draw, ((W-(bbox_t[2]-bbox_t[0]))/2-bbox_t[0], y_title), title_text, font_t, (255,255,255,255), "center", spacing_title, is_bold_title, bold_thickness)

    # 2. フッター
    bbox_f = draw.multiline_textbbox((0, 0), footer_input, font=font_f, align="center", spacing=20)
    draw_styled_text(draw, ((W-(bbox_f[2]-bbox_f[0]))/2-bbox_f[0], y_footer), footer_input, font_f, (255,255,255,255), "center", 20, is_bold_footer, bold_thickness)

    # 3. 本文
    bbox_b = draw.multiline_textbbox((0, 0), body_input, font=font_b, align="left", spacing=spacing_body)
    body_h = bbox_b[3] - bbox_b[1]
    title_bottom = y_title + (bbox_t[3] - bbox_t[1])
    y_b = max(title_bottom + 50, title_bottom + (y_footer - title_bottom - body_h) / 2 - bbox_b[1] + y_body_offset)
    draw_styled_text(draw, ((W-(bbox_b[2]-bbox_b[0]))/2-bbox_b[0], y_b), body_input, font_b, (255,255,255,255), "left", spacing_body, is_bold_body, bold_thickness)

    return img, None

with col2:
    st.subheader("👀 プレビュー")
    img, error = create_preview_image()
    if not error:
        st.image(img, use_container_width=True)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        st.download_button("⬇️ 画像をダウンロード", buf.getvalue(), "reels_image.png", "image/png", use_container_width=True)

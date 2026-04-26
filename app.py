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

# --- サイドバー（レイアウト微調整） ---
st.sidebar.title("⚙️ レイアウト微調整")
st.sidebar.write("基本はこのままでOKですが、重なる場合は数値を動かしてください。")

# タイトル調整
st.sidebar.markdown("---")
st.sidebar.subheader("① タイトル設定")
size_title = st.sidebar.slider("文字サイズ", 50, 150, 85) # 初期値を少し小さく調整
y_title = st.sidebar.slider("上下位置 (Y)", 50, 600, 250)
thickness_t = st.sidebar.slider("太さ", 1, 5, 3)

# 本文調整
st.sidebar.markdown("---")
st.sidebar.subheader("② 本文設定")
size_body = st.sidebar.slider("文字サイズ", 30, 100, 48)
y_body_offset = st.sidebar.slider("位置の微調整", -500, 500, 0)

# フッター調整
st.sidebar.markdown("---")
st.sidebar.subheader("③ フッター設定")
size_footer = st.sidebar.slider("文字サイズ", 30, 100, 55)
y_footer = st.sidebar.slider("上下位置 (Y)", 1500, 1900, 1670)
thickness_f = st.sidebar.slider("太さ", 1, 5, 2)

# --- メイン画面 ---
st.title("🎬 AIリール動画自動生成ツール")

col1, col2 = st.columns([1, 1.2]) 

with col1:
    st.subheader("📝 テキスト入力")
    title_input = st.text_area("① タイトル（『\\n』で改行）", "「都合のいい女」の\\nLINEには共通点がある", height=80)
    body_input = st.text_area("② 本文", "LINEの返信が早すぎる女は\n男に「いつでも来ていい」と\n思わせてしまう。\n\n既読をつけたら即返信、\nスタンプで感情を垂れ流す、\n「ねえ、怒ってる？」と先に謝る。\n\nこれ全部、\n自分から主導権を手放してる行動よ。\n\n男は「手に入れた」と確信した瞬間、\nあなたの優先順位を下げるの。\n\n返信の速さは\nあなたの価値じゃなく\n「暇さ」の証明になるわけ。", height=350)
    footer_input = st.text_area("③ フッター", "保存して、次にLINEを打つ前に見返しなさい。", height=80)

def draw_thick_text(draw_obj, xy, text, font, fill, align, spacing, thickness):
    x, y = xy
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
    bbox_t = draw.multiline_textbbox((0, 0), title_text, font=font_t, align="center", spacing=20)
    draw_thick_text(draw, ((W-(bbox_t[2]-bbox_t[0]))/2-bbox_t[0], y_title), title_text, font_t, (255,255,255,255), "center", 20, thickness_t)

    # 2. フッター
    bbox_f = draw.multiline_textbbox((0, 0), footer_input, font=font_f, align="center", spacing=20)
    draw_thick_text(draw, ((W-(bbox_f[2]-bbox_f[0]))/2-bbox_f[0], y_footer), footer_input, font_f, (255,255,255,255), "center", 20, thickness_f)

    # 3. 本文
    bbox_b = draw.multiline_textbbox((0, 0), body_input, font=font_b, align="left", spacing=30)
    body_h = bbox_b[3] - bbox_b[1]
    title_bottom = y_title + (bbox_t[3] - bbox_t[1])
    y_b = title_bottom + (y_footer - title_bottom - body_h) / 2 - bbox_b[1] + y_body_offset
    draw.multiline_text(((W-(bbox_b[2]-bbox_b[0]))/2-bbox_b[0], y_b), body_input, font=font_b, fill=(255,255,255,255), align="left", spacing=30)

    return img, None

with col2:
    st.subheader("👀 プレビュー")
    img, error = create_preview_image()
    if not error:
        st.image(img, use_container_width=True)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        st.download_button("⬇️ 画像をダウンロード", buf.getvalue(), "reels_image.png", "image/png", use_container_width=True)

import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import io

# --- 基本設定 ---
st.set_page_config(page_title="AIリール生成ツール", layout="wide")

FONT_PATH = "font.ttf" 
BASE_IMAGE_PATH = "base.png"

# --- サイドバー（デザイン・レイアウト調整） ---
st.sidebar.title("⚙️ デザイン設定")

# 太字設定
st.sidebar.subheader("【太字・太さ設定】")
is_bold_title = st.sidebar.checkbox("タイトルを太字にする", value=True, key="b_title")
is_bold_body = st.sidebar.checkbox("本文を太字にする", value=False, key="b_body")
is_bold_footer = st.sidebar.checkbox("フッターを太字にする", value=True, key="b_footer")
bold_strength = st.sidebar.slider("太字の強度", 1.0, 3.0, 1.5, step=0.1)

# 位置・サイズ・行間の微調整
with st.sidebar.expander("位置・サイズ・行間の微調整", expanded=True):
    
    st.subheader("① タイトル設定")
    # APIエラーを完全に防ぐため、sliderの初期値（value）にSession Stateを直接仕込みます
    size_title = st.slider("タイトル文字サイズ", 30, 150, value=st.session_state.get("s_title", 80), key="s_title_slider")
    spacing_title = st.slider("タイトルの行間", 0, 50, value=st.session_state.get("sp_title", 10), key="sp_title_slider")
    y_title = st.slider("タイトル上下位置 (Y)", 50, 500, value=st.session_state.get("y_title", 160), key="y_title_slider")
    x_title_offset = st.slider("タイトル左右のズレ", -500, 500, value=st.session_state.get("x_title", 0), key="x_title_slider")
    
    if st.button("🔄 タイトルを中央基準に戻す", use_container_width=True):
        st.session_state["s_title"] = 80
        st.session_state["sp_title"] = 10
        st.session_state["y_title"] = 160
        st.session_state["x_title"] = 0
        # スライダー側の内部状態もクリア
        st.session_state["s_title_slider"] = 80
        st.session_state["sp_title_slider"] = 10
        st.session_state["y_title_slider"] = 160
        st.session_state["x_title_slider"] = 0
        st.rerun()

    st.markdown("---")
    st.subheader("② 本文設定")
    size_body = st.slider("本文文字サイズ", 20, 100, value=st.session_state.get("s_body", 45), key="s_body_slider")
    spacing_body = st.slider("本文の行間", 10, 100, value=st.session_state.get("sp_body", 30), key="sp_body_slider")
    y_body_offset = st.slider("本文上下のズレ (中央基準)", -500, 500, value=st.session_state.get("y_body", 0), key="y_body_slider")
    x_body_offset = st.slider("本文左右のズレ", -500, 500, value=st.session_state.get("x_body", 0), key="x_body_slider")
    
    if st.button("🔄 本文を中央基準に戻す", use_container_width=True):
        st.session_state["s_body"] = 45
        st.session_state["sp_body"] = 30
        st.session_state["y_body"] = 0
        st.session_state["x_body"] = 0
        st.session_state["s_body_slider"] = 45
        st.session_state["sp_body_slider"] = 30
        st.session_state["y_body_slider"] = 0
        st.session_state["x_body_slider"] = 0
        st.rerun()

    st.markdown("---")
    st.subheader("③ フッター設定")
    size_footer = st.slider("フッター文字サイズ", 20, 100, value=st.session_state.get("s_footer", 40), key="s_footer_slider")
    spacing_footer = st.slider("フッターの行間", 0, 50, value=st.session_state.get("sp_footer", 10), key="sp_footer_slider")
    y_footer = st.slider("フッター上下位置 (Y)", 1000, 1900, value=st.session_state.get("y_footer", 1650), key="y_footer_slider")
    x_footer_offset = st.slider("フッター左右のズレ", -500, 500, value=st.session_state.get("x_footer", 0), key="x_footer_slider")
    
    if st.button("🔄 フッターを中央基準に戻す", use_container_width=True):
        st.session_state["s_footer"] = 40
        st.session_state["sp_footer"] = 10
        st.session_state["y_footer"] = 1650
        st.session_state["x_footer"] = 0
        st.session_state["s_footer_slider"] = 40
        st.session_state["sp_footer_slider"] = 10
        st.session_state["y_footer_slider"] = 1650
        st.session_state["x_footer_slider"] = 0
        st.rerun()

# --- メイン画面 ---
st.title("🎬 AIリール動画自動生成ツール")

col1, col2 = st.columns([1, 1.2])

# --- 入力エリア（左カラム） ---
with col1:
    st.subheader("📝 テキスト入力")
    title_input = st.text_area("① タイトル", "即レスする女が、\n男に飽きられる理由。", height=100)
    body_input = st.text_area("② 本文", "・即レスは「いつでも手に入る」という合図よ。\n・連絡を待つだけの女に、男は価値を感じない。\n・「俺に夢中だな」と確信されたら、そこで終了よ。\n・安心感を与えた瞬間、男は貴女を追うのをやめる。\n・画面にかじりつく暇があるなら、自分の生活を送りなさい。\n・追われたいなら、返信の速度を半分にしなさい。", height=250)
    footer_input = st.text_area("③ フッター", "※本気で追われたい女以外は\n 今すぐこの画面を閉じなさい。", height=100)

# --- 疑似太字（肉付け）描画関数 ---
def draw_text_with_bold(draw, position, text, font, fill, align, spacing, is_bold, strength):
    x, y = position
    if is_bold:
        for dx in [-strength, 0, strength]:
            for dy in [-strength, 0, strength]:
                draw.multiline_text((x + dx, y + dy), text, font=font, fill=fill, align=align, spacing=spacing)
    else:
        draw.multiline_text((x, y), text, font=font, fill=fill, align=align, spacing=spacing)

# --- 画像生成処理 ---
def create_preview_image():
    try:
        img = Image.open(BASE_IMAGE_PATH).convert("RGBA")
    except FileNotFoundError:
        img = Image.new("RGBA", (1080, 1920), (0, 0, 0, 255))
        
    draw = ImageDraw.Draw(img)
    try:
        font_t = ImageFont.truetype(FONT_PATH, size_title)
        font_b = ImageFont.truetype(FONT_PATH, size_body)
        font_f = ImageFont.truetype(FONT_PATH, size_footer)
    except IOError:
        return None, "エラー: font.ttf が見つかりません。GitHubにフォントを配置してください。"

    title_text = title_input.replace('\\n', '\n')
    body_text = body_input.replace('\\n', '\n')
    footer_text = footer_input.replace('\\n', '\n')

    # 1. タイトル描画 (中央揃え)
    bbox_t = draw.multiline_textbbox((0, 0), title_text, font=font_t, align="center", spacing=spacing_title)
    title_w, title_h = bbox_t[2] - bbox_t[0], bbox_t[3] - bbox_t[1]
    x_t = (1080 - title_w) / 2 - bbox_t[0] + x_title_offset
    draw_text_with_bold(draw, (x_t, y_title), title_text, font=font_t, fill=(255, 255, 255, 255), align="center", spacing=spacing_title, is_bold=is_bold_title, strength=bold_strength)
    title_bottom = y_title + title_h

    # 2. フッター描画 (中央揃え)
    bbox_f = draw.multiline_textbbox((0, 0), footer_text, font=font_f, align="center", spacing=spacing_footer)
    footer_w = bbox_f[2] - bbox_f[0]
    x_f = (1080 - footer_w) / 2 - bbox_f[0] + x_footer_offset
    draw_text_with_bold(draw, (x_f, y_footer), footer_text, font=font_f, fill=(255, 255, 255, 255), align="center", spacing=spacing_footer, is_bold=is_bold_footer, strength=bold_strength)

    # 3. 本文描画 (完全中央配置 ＆ 中央揃え)
    bbox_b = draw.multiline_textbbox((0, 0), body_text, font=font_b, align="center", spacing=spacing_body)
    body_w, body_h = bbox_b[2] - bbox_b[0], bbox_b[3] - bbox_b[1]
    x_b = (1080 - body_w) / 2 - bbox_b[0] + x_body_offset
    
    # タイトル下部からフッター上部までの空き空間に中央配置
    available_space = y_footer - title_bottom
    y_b = title_bottom + (available_space - body_h) / 2 - bbox_b[1] + y_body_offset

    draw_text_with_bold(draw, (x_b, y_b), body_text, font=font_b, fill=(255, 255, 255, 255), align="center", spacing=spacing_body, is_bold=is_bold_body, strength=bold_strength)

    return img, None

# --- プレビュー表示エリア（右カラム） ---
with col2:
    st.subheader("👀 プレビュー")
    img, error = create_preview_image()
    
    if error:
        st.error(error)
    else:
        st.image(img, use_container_width=True)
        
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        byte_im = buf.getvalue()
        
        st.download_button(
            label="⬇️ この画像をダウンロード",
            data=byte_im,
            file_name="reels_image.png",
            mime="image/png",
            use_container_width=True
        )

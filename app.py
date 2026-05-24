import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import io

# --- 基本設定 ---
st.set_page_config(page_title="AIリール生成ツール", layout="wide")

# フォントパスの設定
FONT_PATH = "font.ttf" 
# 背景画像のパス設定
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
    size_title = st.sidebar.slider("タイトル文字サイズ", 30, 150, 80, key="s_title")
    spacing_title = st.sidebar.slider("タイトルの行間", 0, 50, 10, key="sp_title")
    y_title = st.sidebar.slider("タイトル上下位置 (Y)", 50, 500, 160, key="y_title")
    x_title_offset = st.sidebar.slider("タイトル左右のズレ", -500, 500, 0, key="x_title")

    st.subheader("② 本文設定")
    size_body = st.sidebar.slider("本文文字サイズ", 20, 100, 45, key="s_body")
    spacing_body = st.sidebar.slider("本文の行間", 10, 100, 30, key="sp_body")
    y_body_offset = st.sidebar.slider("本文上下のズレ (中央基準)", -500, 500, 0, key="y_body")
    x_body_offset = st.sidebar.slider("本文左右のズレ", -500, 500, 0, key="x_body")

    st.subheader("③ フッター設定")
    size_footer = st.sidebar.slider("フッター文字サイズ", 20, 100, 40, key="s_footer")
    spacing_footer = st.sidebar.slider("フッターの行間", 0, 50, 10, key="sp_footer")
    y_footer = st.sidebar.slider("フッター上下位置 (Y)", 1000, 1900, 1650, key="y_footer")
    x_footer_offset = st.sidebar.slider("フッター左右のズレ", -500, 500, 0, key="x_footer")

# --- メイン画面 ---
st.title("🎬 AIリール動画自動生成ツール")

# 画面を左右の2カラムに分ける
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
    # ★安全設計：まずベース画像（base.png）の読み込みにトライする
    try:
        img = Image.open(BASE_IMAGE_PATH).convert("RGBA")
    except FileNotFoundError:
        # もしbase.pngがGitHub上に見つからなくても、自動で「純黒背景」を作ってエラーを完全に回避する
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

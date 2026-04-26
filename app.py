import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import io
import os

# --- 基本設定 ---
st.set_page_config(page_title="AIリール生成ツール", layout="wide")

# クラウド用のファイル名設定
FONT_PATH = "font.ttf" 
BASE_IMAGE_PATH = "base.png"

# --- サイドバー（レイアウト調整） ---
st.sidebar.title("⚙️ レイアウト調整")
st.sidebar.write("数値を動かすと即座に右側のプレビューに反映されます。")

# タイトル用の調整
st.sidebar.markdown("---")
st.sidebar.subheader("① タイトル設定")
size_title = st.sidebar.slider("文字サイズ", 50, 150, 90, key="s_title")
y_title = st.sidebar.slider("上下位置 (Y座標)", 50, 500, 200, key="y_title")
x_title_offset = st.sidebar.slider("左右のズレ", -500, 500, 0, key="x_title")

# 本文用の調整
st.sidebar.markdown("---")
st.sidebar.subheader("② 本文設定")
size_body = st.sidebar.slider("文字サイズ", 30, 100, 50, key="s_body")
y_body_offset = st.sidebar.slider("上下のズレ (中央基準)", -500, 500, 0, key="y_body")
x_body_offset = st.sidebar.slider("左右のズレ", -500, 500, 0, key="x_body")

# フッター用の調整
st.sidebar.markdown("---")
st.sidebar.subheader("③ フッター設定")
size_footer = st.sidebar.slider("文字サイズ", 30, 100, 55, key="s_footer")
y_footer = st.sidebar.slider("上下位置 (Y座標)", 1000, 1900, 1650, key="y_footer")
x_footer_offset = st.sidebar.slider("左右のズレ", -500, 500, 0, key="x_footer")


# --- メイン画面 ---
st.title("🎬 AIリール動画自動生成ツール")

# 画面を左右の2カラムに分ける
col1, col2 = st.columns([1, 1.2]) 

# --- 入力エリア（左カラム） ---
with col1:
    st.subheader("📝 テキスト入力")
    title_input = st.text_area("① タイトル", "追いかける女は、\n今夜で終わり", height=100)
    body_input = st.text_area("② 本文", "不安に駆られて\n追いLINEを送った瞬間、\n男に「こいつは離れない」という\n絶対的な“余裕”を与えてしまうわ。\n\n彼が冷たいのは、愛情不足じゃない。\n「完全に手に入った獲物」には\n見向きもしなくなる。\n\nそれが男の残酷な“本能の仕様”なのよ。\n\nだから、今夜から一つだけ約束しなさい。\n\n彼に連絡したくてたまらなくなったら、\n彼とのトーク画面は閉じて、\n自分のためだけに夜を使いなさい。\n\n自分の感情を制した女だけが、\n男の脳を支配できる。", height=350)
    footer_input = st.text_area("③ フッター", "焦る必要はないわ。\n貴女が、彼を動かすのよ。", height=100)

# --- 画像生成処理（エラー対策を強化） ---
def create_preview_image():
    # 1. 画像ファイルの存在確認
    if not os.path.exists(BASE_IMAGE_PATH):
        return None, f"エラー: {BASE_IMAGE_PATH} がGitHubにアップロードされていません。"
    try:
        img = Image.open(BASE_IMAGE_PATH).convert("RGBA")
    except Exception as e:
        return None, f"画像の読み込みに失敗しました: {e}"
    
    draw = ImageDraw.Draw(img)
    
    # 2. フォントファイルの存在確認
    if not os.path.exists(FONT_PATH):
        return None, f"エラー: {FONT_PATH} がGitHubにアップロードされていません。"
    try:
        font_t = ImageFont.truetype(FONT_PATH, size_title)
        font_b = ImageFont.truetype(FONT_PATH, size_body)
        font_f = ImageFont.truetype(FONT_PATH, size_footer)
    except Exception as e:
        return None, f"フォントの読み込みに失敗しました: {e}"

    title_text = title_input.replace('\\n', '\n')
    body_text = body_input.replace('\\n', '\n')
    footer_text = footer_input.replace('\\n', '\n')

    # タイトル
    bbox_t = draw.multiline_textbbox((0, 0), title_text, font=font_t, align="center", spacing=20)
    title_w, title_h = bbox_t[2] - bbox_t[0], bbox_t[3] - bbox_t[1]
    x_t = (1080 - title_w) / 2 - bbox_t[0] + x_title_offset
    draw.multiline_text((x_t, y_title), title_text, font=font_t, fill=(255, 255, 255, 255), align="center", spacing=20)
    title_bottom = y_title + title_h

    # フッター
    bbox_f = draw.multiline_textbbox((0, 0), footer_text, font=font_f, align="center", spacing=20)
    footer_w = bbox_f[2] - bbox_f[0]
    x_f = (1080 - footer_w) / 2 - bbox_f[0] + x_footer_offset
    draw.multiline_text((x_f, y_footer), footer_text, font=font_f, fill=(255, 255, 255, 255), align="center", spacing=20)

    # 本文
    bbox_b = draw.multiline_textbbox((0, 0), body_text, font=font_b, align="left", spacing=30)
    body_w, body_h = bbox_b[2] - bbox_b[0], bbox_b[3] - bbox_b[1]
    x_b = (1080 - body_w) / 2 - bbox_b[0] + x_body_offset
    available_space = y_footer - title_bottom
    y_b = title_bottom + (available_space - body_h) / 2 - bbox_b[1] + y_body_offset
    draw.multiline_text((x_b, y_b), body_text, font=font_b, fill=(255, 255, 255, 255), align="left", spacing=30)

    return img, None

# --- プレビュー表示エリア（右カラム） ---
with col2:
    st.subheader("👀 プレビュー")
    img, error = create_preview_image()
    
    if error:
        # 赤いエラーの代わりに、分かりやすい警告メッセージを出すように変更
        st.warning(error)
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

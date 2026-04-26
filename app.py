import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import os

# --- 基本設定 ---
st.set_page_config(page_title="AIリール生成ツール", layout="wide")

# クラウド用のファイル名設定
FONT_PATH = "font.ttf"  # 現在使用しているフォントファイル
BASE_IMAGE_PATH = "base.png"

# --- 画面レイアウト（サイドバーを廃止） ---
st.title("🎬 AIリール動画自動生成ツール")
st.write("左に入力したテキストが、右側のプレビューに即座に反映されます。")

# 画面を左右の2カラムに分ける
col1, col2 = st.columns([1, 1.2]) 

# --- 入力エリア（左カラム） ---
with col1:
    st.subheader("📝 テキスト入力")
    title_input = st.text_area("① タイトル（『\\n』で改行）", "「都合のいい女」の\\nLINEには共通点がある", height=80)
    body_input = st.text_area("② 本文", "LINEの返信が早すぎる女は\n男に「いつでも来ていい」と\n思わせてしまう。\n\n既読をつけたら即返信、\nスタンプで感情を垂れ流す、\n「ねえ、怒ってる？」と先に謝る。\n\nこれ全部、\n自分から主導権を手放してる行動よ。\n\n男は「手に入れた」と確信した瞬間、\nあなたの優先順位を下げるの。\n\n返信の速さは\nあなたの価値じゃなく\n「暇さ」の証明になるわけ。", height=350)
    footer_input = st.text_area("③ フッター", "保存して、次にLINEを打つ前に見返しなさい。", height=80)

# --- 画像生成処理（フォントを太く、レイアウトを完全固定に改良） ---
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
        # 【改良ポイント】フォントサイズを少し大きくし、太く見せる
        font_t = ImageFont.truetype(FONT_PATH, size=100) # タイトル
        font_b = ImageFont.truetype(FONT_PATH, size=52)  # 本文
        font_f = ImageFont.truetype(FONT_PATH, size=58)  # フッター
    except Exception as e:
        return None, f"フォントの読み込みに失敗しました: {e}"

    # テキストの処理（入力の\nを実際の改行に変換）
    title_text = title_input.replace('\\n', '\n')
    body_text = body_input
    footer_text = footer_input

    # --- 【改良ポイント】レイアウト数値を完全に固定 ---
    W, H = 1080, 1920 # 画像の全体サイズ

    # テキストの描画設定
    text_color = (255, 255, 255, 255) # 白
    align_t = "center" # タイトルは中央寄せ
    align_b = "left"   # 本文は左寄せ
    align_f = "center" # フッターは中央寄せ
    spacing_t = 30 # タイトルの行間
    spacing_b = 30 # 本文の行間

    # 文字を太く見せるための「疑似ボールド」描画関数
    def draw_thick_text(draw_obj, xy, text, font, fill, align, spacing, thickness=2):
        x, y = xy
        # 0度から360度まで少しずつずらして重ね書きすることで、太く見せる
        for degrees in range(0, 360, 45):
            import math
            dx = thickness * math.cos(math.radians(degrees))
            dy = thickness * math.sin(math.radians(degrees))
            draw_obj.multiline_text((x+dx, y+dy), text, font=font, fill=fill, align=align, spacing=spacing)
        # 最後に中央に描画
        draw_obj.multiline_text((x, y), text, font=font, fill=fill, align=align, spacing=spacing)

    # 1. タイトル（中央・上部・擬似ボールド）
    bbox_t = draw.multiline_textbbox((0, 0), title_text, font=font_t, align=align_t, spacing=spacing_t)
    title_w, title_h = bbox_t[2] - bbox_t[0], bbox_t[3] - bbox_t[1]
    # 固定位置：上部から220pxの位置
    y_title_fixed = 220 
    x_t = (W - title_w) / 2 - bbox_t[0]
    # 疑似ボールドで描画（太さ3px）
    draw_thick_text(draw, (x_t, y_title_fixed), title_text, font=font_t, fill=text_color, align=align_t, spacing=spacing_t, thickness=3)

    # 2. フッター（中央・下部・擬似ボールド）
    bbox_f = draw.multiline_textbbox((0, 0), footer_text, font=font_f, align=align_f, spacing=20)
    footer_w = bbox_f[2] - bbox_f[0]
    # 固定位置：下部から250pxの位置（Y座標 1670px）
    y_footer_fixed = 1670 
    x_f = (W - footer_w) / 2 - bbox_f[0]
    # 疑似ボールドで描画（太さ2px）
    draw_thick_text(draw, (x_f, y_footer_fixed), footer_text, font=font_f, fill=text_color, align=align_f, spacing=20, thickness=2)

    # 3. 本文（左寄せ・中央配置）
    bbox_b = draw.multiline_textbbox((0, 0), body_text, font=font_b, align=align_b, spacing=spacing_b)
    body_w, body_h = bbox_b[2] - bbox_b[0], bbox_b[3] - bbox_b[1]
    x_b = (W - body_w) / 2 - bbox_b[0] # 本文全体のブロックを中央に寄せる
    
    # 中央配置のための計算
    title_bottom = y_title_fixed + title_h
    available_space = y_footer_fixed - title_bottom
    y_b = title_bottom + (available_space - body_h) / 2 - bbox_b[1]
    
    # 本文はそのまま描画（細いままで読みやすく）
    draw.multiline_text((x_b, y_b), body_text, font=font_b, fill=text_color, align=align_b, spacing=spacing_b)

    return img, None

# --- プレビュー表示エリア（右カラム） ---
with col2:
    st.subheader("👀 プレビュー")
    img, error = create_preview_image()
    
    if error:
        st.warning(error)
    else:
        # プレビュー表示
        st.image(img, use_container_width=True)
        
        # ダウンロードボタンを画像のすぐ下に配置
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        byte_im = buf.getvalue()
        
        st.download_button(
            label="⬇️ この画像をダウンロードしてPremiere Proで使用",
            data=byte_im,
            file_name="reels_image.png",
            mime="image/png",
            use_container_width=True
        )

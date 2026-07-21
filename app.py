import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import io
import base64

# --- 基本設定 ---
st.set_page_config(page_title="AIリール生成ツール", layout="wide")

FONT_PATH = "font.ttf"
BASE_IMAGE_PATH = "base.png"
CANVAS_W, CANVAS_H = 1080, 1920  # Instagram推奨サイズ（9:16）

# --- レスポンシブ・プレビュー用CSS ---
# 右カラムのプレビュー画像が、画面幅に応じてアスペクト比(9:16)を保ったまま
# 等倍で綺麗に縮小表示されるようにする。
st.markdown(
    """
    <style>
        /* プレビュー画像をカードっぽく中央寄せしつつ、アスペクト比を保って縮小 */
        div[data-testid="stImage"] {
            display: flex;
            justify-content: center;
        }
        div[data-testid="stImage"] img {
            max-width: 100%;
            height: auto;
            aspect-ratio: 1080 / 1920;
            border-radius: 12px;
            box-shadow: 0 4px 18px rgba(0, 0, 0, 0.25);
        }
        /* 画像保存ボタンを目立たせる */
        div[data-testid="stDownloadButton"] button {
            background-color: #E1306C;
            color: #FFFFFF;
            font-weight: 700;
            font-size: 1.05rem;
            border: none;
            padding: 0.75rem 0;
        }
        div[data-testid="stDownloadButton"] button:hover {
            background-color: #c72a5e;
            color: #FFFFFF;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- 修正の最重要ポイント: リセット用のカウンター（Key）の管理 ---
# ボタンが押されたらこの数値を増やすことで、Streamlitにスライダーを「新品」に交換させます
if "reset_counter" not in st.session_state:
    st.session_state["reset_counter"] = 0

# --- サイドバー（デザイン・レイアウト調整） ---
st.sidebar.title("⚙️ デザイン設定")

# 太字設定
st.sidebar.subheader("【太字・太さ設定】")
is_bold_title = st.sidebar.checkbox("タイトルを太字にする", value=True, key="b_title")
is_bold_body = st.sidebar.checkbox("本文を太字にする", value=False, key="b_body")
is_bold_footer = st.sidebar.checkbox("フッターを太字にする", value=True, key="b_footer")
bold_strength = st.sidebar.slider("太字の強度", 1.0, 3.0, 1.5, step=0.1)

# スマート・リサイズ設定
st.sidebar.subheader("【自動フォントサイズ調整】")
auto_fit_enabled = st.sidebar.checkbox(
    "はみ出し防止（スマート・リサイズ）を有効にする",
    value=True,
    help="文字数が多い場合、枠内に収まるようフォントサイズと行間を自動で縮小します。",
    key="auto_fit_enabled",
)
min_scale_percent = st.sidebar.slider(
    "自動縮小の下限（元サイズ比）",
    30, 100, value=45, step=5,
    help="これ以上は縮小しません。小さくしすぎると読みにくくなります。",
    disabled=not auto_fit_enabled,
)

# 位置・サイズ・行間の微調整
with st.sidebar.expander("位置・サイズ・行間の微調整", expanded=True):

    # 動的に一意のキーを作ることで、ボタンを押した瞬間にスライダーを完全初期化します
    run_id = st.session_state["reset_counter"]

    st.subheader("① タイトル設定")
    size_title = st.slider("タイトル文字サイズ", 30, 150, value=80, key=f"s_title_{run_id}")
    spacing_title = st.slider("タイトルの行間", 0, 50, value=10, key=f"sp_title_{run_id}")
    y_title = st.slider("タイトル上下位置 (Y)", 50, 500, value=160, key=f"y_title_{run_id}")
    x_title_offset = st.slider("タイトル左右のズレ", -500, 500, value=0, key=f"x_title_{run_id}")

    if st.button("🔄 タイトルを中央基準に戻す", use_container_width=True):
        st.session_state["reset_counter"] += 1
        st.rerun()

    st.markdown("---")
    st.subheader("② 本文設定")
    size_body = st.slider("本文文字サイズ", 20, 100, value=45, key=f"s_body_{run_id}")
    spacing_body = st.slider("本文の行間", 10, 100, value=30, key=f"sp_body_{run_id}")
    y_body_offset = st.slider("本文上下のズレ (中央基準)", -500, 500, value=0, key=f"y_body_{run_id}")
    x_body_offset = st.slider("本文左右のズレ", -500, 500, value=0, key=f"x_body_{run_id}")

    if st.button("🔄 本文を中央基準に戻す", use_container_width=True):
        st.session_state["reset_counter"] += 1
        st.rerun()

    st.markdown("---")
    st.subheader("③ フッター設定")
    size_footer = st.slider("フッター文字サイズ", 20, 100, value=40, key=f"s_footer_{run_id}")
    spacing_footer = st.slider("フッターの行間", 0, 50, value=10, key=f"sp_footer_{run_id}")
    y_footer = st.slider("フッター上下位置 (Y)", 1000, 1900, value=1650, key=f"y_footer_{run_id}")
    x_footer_offset = st.slider("フッター左右のズレ", -500, 500, value=0, key=f"x_footer_{run_id}")

    if st.button("🔄 フッターを中央基準に戻す", use_container_width=True):
        st.session_state["reset_counter"] += 1
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


# --- スマート・リサイズ: 指定した幅・高さに収まるようフォントサイズと行間を自動調整 ---
def fit_font_and_spacing(
    measure_draw,
    text,
    base_size,
    base_spacing,
    max_width,
    max_height,
    align="center",
    min_scale=0.45,
    absolute_min_size=14,
    step=1,
):
    """
    テキストが max_width x max_height の枠に収まるように、
    base_size を上限としてフォントサイズと行間(spacing)を同じ比率で縮小していく。
    戻り値: (font, spacing, bbox, scale)
    """
    size = max(int(base_size), absolute_min_size)
    min_size = max(absolute_min_size, int(round(base_size * min_scale)))

    font = ImageFont.truetype(FONT_PATH, size)
    spacing = base_spacing
    bbox = measure_draw.multiline_textbbox((0, 0), text, font=font, align=align, spacing=spacing)

    while True:
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        fits = (w <= max_width and h <= max_height)
        if fits or size <= min_size:
            break
        size = max(size - step, min_size)
        font = ImageFont.truetype(FONT_PATH, size)
        spacing = max(base_spacing * (size / base_size), 0)
        bbox = measure_draw.multiline_textbbox((0, 0), text, font=font, align=align, spacing=spacing)

    scale = size / base_size if base_size else 1.0
    return font, spacing, bbox, scale


# --- 画像生成処理 ---
def create_preview_image():
    try:
        img = Image.open(BASE_IMAGE_PATH).convert("RGBA")
    except FileNotFoundError:
        img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 255))

    draw = ImageDraw.Draw(img)

    try:
        # フォントが存在するか事前チェック（実際のフォントはfit関数内で都度読み込む）
        ImageFont.truetype(FONT_PATH, 10)
    except IOError:
        return None, "エラー: font.ttf が見つかりません。GitHubにフォントを配置してください。", {}

    title_text = title_input.replace('\\n', '\n')
    body_text = body_input.replace('\\n', '\n')
    footer_text = footer_input.replace('\\n', '\n')

    # 左右マージンを考慮した最大幅（デザインの装飾枠に文字がぶつからないように）
    side_margin = 90
    max_text_width = CANVAS_W - side_margin * 2

    min_scale = min_scale_percent / 100.0
    fit_info = {"title": 1.0, "body": 1.0, "footer": 1.0}

    # ---------- 1. タイトル：まず幅に収まるようにサイズを自動調整 ----------
    if auto_fit_enabled:
        # タイトルは高さ制約が緩いので、幅方向のはみ出し防止を優先
        title_max_height = 10 ** 6  # 実質無制限（幅だけを制約）
        font_t, spacing_title_fit, bbox_t, scale_t = fit_font_and_spacing(
            draw, title_text, size_title, spacing_title,
            max_text_width, title_max_height, min_scale=min_scale,
        )
        fit_info["title"] = scale_t
    else:
        font_t = ImageFont.truetype(FONT_PATH, size_title)
        spacing_title_fit = spacing_title
        bbox_t = draw.multiline_textbbox((0, 0), title_text, font=font_t, align="center", spacing=spacing_title_fit)

    title_w, title_h = bbox_t[2] - bbox_t[0], bbox_t[3] - bbox_t[1]
    x_t = (CANVAS_W - title_w) / 2 - bbox_t[0] + x_title_offset
    draw_text_with_bold(
        draw, (x_t, y_title), title_text, font=font_t, fill=(255, 255, 255, 255),
        align="center", spacing=spacing_title_fit, is_bold=is_bold_title, strength=bold_strength,
    )
    title_bottom = y_title + title_h

    # ---------- 2. フッター：幅に収まるようにサイズを自動調整 ----------
    if auto_fit_enabled:
        footer_max_height = 10 ** 6
        font_f, spacing_footer_fit, bbox_f, scale_f = fit_font_and_spacing(
            draw, footer_text, size_footer, spacing_footer,
            max_text_width, footer_max_height, min_scale=min_scale,
        )
        fit_info["footer"] = scale_f
    else:
        font_f = ImageFont.truetype(FONT_PATH, size_footer)
        spacing_footer_fit = spacing_footer
        bbox_f = draw.multiline_textbbox((0, 0), footer_text, font=font_f, align="center", spacing=spacing_footer_fit)

    footer_w, footer_h = bbox_f[2] - bbox_f[0], bbox_f[3] - bbox_f[1]
    x_f = (CANVAS_W - footer_w) / 2 - bbox_f[0] + x_footer_offset
    draw_text_with_bold(
        draw, (x_f, y_footer), footer_text, font=font_f, fill=(255, 255, 255, 255),
        align="center", spacing=spacing_footer_fit, is_bold=is_bold_footer, strength=bold_strength,
    )

    # ---------- 3. 本文：タイトル〜フッターの間の空きスペースに収まるよう自動調整 ----------
    available_space = max(y_footer - title_bottom, 0)

    if auto_fit_enabled:
        # 上下に少し余白(padding)を確保してから本文用の高さ制約とする
        vertical_padding = 40
        body_max_height = max(available_space - vertical_padding * 2, 10)
        font_b, spacing_body_fit, bbox_b, scale_b = fit_font_and_spacing(
            draw, body_text, size_body, spacing_body,
            max_text_width, body_max_height, min_scale=min_scale,
        )
        fit_info["body"] = scale_b
    else:
        font_b = ImageFont.truetype(FONT_PATH, size_body)
        spacing_body_fit = spacing_body
        bbox_b = draw.multiline_textbbox((0, 0), body_text, font=font_b, align="center", spacing=spacing_body_fit)

    body_w, body_h = bbox_b[2] - bbox_b[0], bbox_b[3] - bbox_b[1]
    x_b = (CANVAS_W - body_w) / 2 - bbox_b[0] + x_body_offset

    # タイトル下部からフッター上部までの空き空間に中央配置
    y_b = title_bottom + (available_space - body_h) / 2 - bbox_b[1] + y_body_offset

    draw_text_with_bold(
        draw, (x_b, y_b), body_text, font=font_b, fill=(255, 255, 255, 255),
        align="center", spacing=spacing_body_fit, is_bold=is_bold_body, strength=bold_strength,
    )

    return img, None, fit_info


# --- プレビュー表示エリア（右カラム） ---
with col2:
    st.subheader("👀 プレビュー")
    img, error, fit_info = create_preview_image()

    if error:
        st.error(error)
    else:
        # レスポンシブ表示：アスペクト比(9:16)を保ったまま画面幅に応じて縮小表示される
        st.image(img, use_container_width=True)

        # 自動調整が発生した場合はユーザーに通知
        shrunk = [name for name, scale in fit_info.items() if scale < 0.999]
        if auto_fit_enabled and shrunk:
            label_map = {"title": "タイトル", "body": "本文", "footer": "フッター"}
            details = " / ".join(
                f"{label_map[name]}: {int(fit_info[name] * 100)}%" for name in shrunk
            )
            st.info(f"📐 はみ出し防止のため、文字サイズを自動縮小しました（{details}）")

        st.markdown("### 📤 画像を書き出す")

        # 高画質PNG（インスタ推奨サイズ 1080 x 1920）で保存
        export_img = img.convert("RGB")
        if export_img.size != (CANVAS_W, CANVAS_H):
            export_img = export_img.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)

        buf = io.BytesIO()
        export_img.save(buf, format="PNG", optimize=True)
        byte_im = buf.getvalue()

        st.download_button(
            label="⬇️ このページを画像として保存（PNG / 1080×1920）",
            data=byte_im,
            file_name="reels_image.png",
            mime="image/png",
            use_container_width=True,
            type="primary",
        )
        st.caption("※ Instagramリール／ストーリーズ推奨サイズ（1080×1920px）の高解像度PNGで書き出されます。")

import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import base64
import io
import os
import shutil
import subprocess
import tempfile

import streamlit.components.v1 as components

# --- 基本設定 ---
st.set_page_config(page_title="AIリール生成ツール", layout="wide")

FONT_PATH = "font.ttf"
BASE_IMAGE_PATH = "base.png"   # 装飾（枠・ヘッダー）の供給元。緑は抜いて使う
W, H = 1080, 1920

MIME_MAP = {".mp4": "video/mp4", ".m4v": "video/mp4",
            ".mov": "video/quicktime", ".webm": "video/webm"}


# --- ffmpeg ユーティリティ -------------------------------------------------
def find_ffmpeg():
    """システムのffmpeg、無ければimageio-ffmpeg同梱のバイナリを返す。"""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def extract_frame(video_bytes, suffix, at_sec):
    """背景動画から1フレーム抜いて返す。 (画像, エラー文) のタプル。"""
    exe = find_ffmpeg()
    if not exe:
        return None, "ffmpegが見つかりません。"

    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in" + suffix)
        dst = os.path.join(tmp, "frame.png")
        with open(src, "wb") as f:
            f.write(video_bytes)

        last_err = ""
        for ss in (str(at_sec), "0"):
            cmd = [
                exe, "-y", "-ss", ss, "-i", src, "-frames:v", "1",
                "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
                dst,
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode == 0 and os.path.exists(dst):
                frame = Image.open(dst)
                frame.load()
                return frame.convert("RGBA").copy(), None
            last_err = proc.stderr[-800:]
        return None, f"フレーム抽出に失敗しました:\n{last_err}"


def build_mp4(video_bytes, suffix, overlay_img, duration, fps, loop_bg):
    """背景動画の上に透過PNGを重ねてMP4のバイト列を返す。"""
    exe = find_ffmpeg()
    if not exe:
        raise RuntimeError(
            "ffmpegが見つかりません。ローカルなら `pip install imageio-ffmpeg`、"
            "Streamlit Cloudならリポジトリ直下の packages.txt に `ffmpeg` の1行を追加してください。"
        )
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in" + suffix)
        png = os.path.join(tmp, "overlay.png")
        out = os.path.join(tmp, "reel.mp4")
        with open(src, "wb") as f:
            f.write(video_bytes)
        overlay_img.save(png)

        cmd = [exe, "-y"]
        if loop_bg:
            cmd += ["-stream_loop", "-1"]
        cmd += [
            "-i", src,
            "-i", png,
            "-filter_complex",
            (
                f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},setsar=1,fps={fps}[bg];"
                "[bg][1:v]overlay=0:0:format=auto[v]"
            ),
            "-map", "[v]",
            "-t", str(duration),
            "-an",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",      # Instagram互換に必須。外さないこと
            "-preset", "medium",
            "-crf", "20",
            "-movflags", "+faststart",
            out,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpegが失敗しました:\n{proc.stderr[-1500:]}")
        with open(out, "rb") as f:
            return f.read()


# --- base.png から緑だけを抜く（装飾は残す） -------------------------------
@st.cache_data(show_spinner=False)
def keyed_decoration(path, tolerance):
    """緑背景のbase.pngから緑を透明化し、枠やヘッダーだけを残したRGBAを返す。"""
    try:
        img = Image.open(path).convert("RGBA").resize((W, H))
    except FileNotFoundError:
        return None
    arr = np.array(img).astype(np.int16)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    green_mask = (g > r + tolerance) & (g > b + tolerance)
    arr[..., 3] = np.where(green_mask, 0, arr[..., 3])
    return Image.fromarray(arr.astype(np.uint8))


# --- リセット用のカウンター（Key）の管理 -----------------------------------
if "reset_counter" not in st.session_state:
    st.session_state["reset_counter"] = 0


# --- サイドバー ------------------------------------------------------------
st.sidebar.title("⚙️ デザイン設定")

# ffmpeg診断
_exe = find_ffmpeg()
if _exe:
    st.sidebar.success("ffmpeg 検出済み")
    st.sidebar.caption(_exe)
else:
    st.sidebar.error(
        "ffmpegが見つかりません。静止プレビューとMP4書き出しができません。\n\n"
        "ローカル: `pip install imageio-ffmpeg`\n\n"
        "Streamlit Cloud: packages.txt に `ffmpeg` を1行追加"
    )

st.sidebar.subheader("【背景・動画設定】")
scrim = st.sidebar.slider(
    "背景の暗幕（文字の可読性）", 0, 220, 110,
    help="0で動画そのまま。上げるほど背景が沈み、白文字が読みやすくなる。",
)
use_decoration = st.sidebar.checkbox("base.pngの装飾を重ねる（緑は自動で透過）", value=True)
green_tolerance = st.sidebar.slider(
    "緑の抜き具合", 5, 80, 25, disabled=not use_decoration,
    help="装飾まで消えるなら下げる。緑が残るなら上げる。",
)
preview_at = st.sidebar.slider("プレビューに使う秒数", 0.0, 10.0, 0.5, step=0.5)
duration = st.sidebar.slider("動画の尺（秒）", 3.0, 30.0, 8.0, step=0.5)
fps = st.sidebar.selectbox("フレームレート", [24, 30, 60], index=1)
loop_bg = st.sidebar.checkbox("背景素材が短い場合ループさせる", value=True)

st.sidebar.subheader("【太字・太さ設定】")
is_bold_title = st.sidebar.checkbox("タイトルを太字にする", value=True, key="b_title")
is_bold_body = st.sidebar.checkbox("本文を太字にする", value=False, key="b_body")
is_bold_footer = st.sidebar.checkbox("フッターを太字にする", value=True, key="b_footer")
bold_strength = st.sidebar.slider("太字の強度", 1.0, 3.0, 1.5, step=0.1)

with st.sidebar.expander("位置・サイズ・行間の微調整", expanded=True):

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


# --- メイン画面 ------------------------------------------------------------
st.title("🎬 AIリール動画自動生成ツール")

col1, col2 = st.columns([1, 1.2])

with col1:
    st.subheader("🎞 背景動画")
    video_file = st.file_uploader(
        "Higgsfieldで生成したレイラの動画",
        type=["mp4", "mov", "webm", "m4v"],
        help="未アップでもテキストレイヤーの調整はできます。",
    )

    st.subheader("📝 テキスト入力")
    title_input = st.text_area("① タイトル", "即レスする女が、\n男に飽きられる理由。", height=100)
    body_input = st.text_area(
        "② 本文",
        "・即レスは「いつでも手に入る」という合図よ。\n"
        "・連絡を待つだけの女に、男は価値を感じない。\n"
        "・「俺に夢中だな」と確信されたら、そこで終了よ。\n"
        "・安心感を与えた瞬間、男は貴女を追うのをやめる。\n"
        "・画面にかじりつく暇があるなら、自分の生活を送りなさい。\n"
        "・追われたいなら、返信の速度を半分にしなさい。",
        height=250,
    )
    footer_input = st.text_area("③ フッター", "※本気で追われたい女以外は\n 今すぐこの画面を閉じなさい。", height=100)


# --- 疑似太字（肉付け）描画関数 --------------------------------------------
def draw_text_with_bold(draw, position, text, font, fill, align, spacing, is_bold, strength):
    x, y = position
    if is_bold:
        for dx in [-strength, 0, strength]:
            for dy in [-strength, 0, strength]:
                draw.multiline_text((x + dx, y + dy), text, font=font, fill=fill, align=align, spacing=spacing)
    else:
        draw.multiline_text((x, y), text, font=font, fill=fill, align=align, spacing=spacing)


# --- オーバーレイ生成（完全透過） ------------------------------------------
def create_overlay():
    """暗幕 → 装飾 → テキスト の順に重ねた、背景が透明なRGBAを返す。"""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    if scrim > 0:
        layer = Image.alpha_composite(layer, Image.new("RGBA", (W, H), (0, 0, 0, scrim)))

    if use_decoration:
        deco = keyed_decoration(BASE_IMAGE_PATH, green_tolerance)
        if deco is not None:
            layer = Image.alpha_composite(layer, deco)

    draw = ImageDraw.Draw(layer)
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
    x_t = (W - title_w) / 2 - bbox_t[0] + x_title_offset
    draw_text_with_bold(draw, (x_t, y_title), title_text, font=font_t, fill=(255, 255, 255, 255),
                        align="center", spacing=spacing_title, is_bold=is_bold_title, strength=bold_strength)
    title_bottom = y_title + title_h

    # 2. フッター描画 (中央揃え)
    bbox_f = draw.multiline_textbbox((0, 0), footer_text, font=font_f, align="center", spacing=spacing_footer)
    footer_w = bbox_f[2] - bbox_f[0]
    x_f = (W - footer_w) / 2 - bbox_f[0] + x_footer_offset
    draw_text_with_bold(draw, (x_f, y_footer), footer_text, font=font_f, fill=(255, 255, 255, 255),
                        align="center", spacing=spacing_footer, is_bold=is_bold_footer, strength=bold_strength)

    # 3. 本文描画 (完全中央配置 ＆ 中央揃え)
    bbox_b = draw.multiline_textbbox((0, 0), body_text, font=font_b, align="center", spacing=spacing_body)
    body_w, body_h = bbox_b[2] - bbox_b[0], bbox_b[3] - bbox_b[1]
    x_b = (W - body_w) / 2 - bbox_b[0] + x_body_offset

    available_space = y_footer - title_bottom
    y_b = title_bottom + (available_space - body_h) / 2 - bbox_b[1] + y_body_offset

    draw_text_with_bold(draw, (x_b, y_b), body_text, font=font_b, fill=(255, 255, 255, 255),
                        align="center", spacing=spacing_body, is_bold=is_bold_body, strength=bold_strength)

    return layer, None


# --- ライブプレビュー（HTML合成・エンコード不要） ---------------------------
@st.cache_data(show_spinner=False)
def video_data_url(video_bytes, mime):
    return f"data:{mime};base64," + base64.b64encode(video_bytes).decode()


def overlay_data_url(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def render_live_preview(video_url, overlay_url, box_h=620):
    box_w = int(box_h * W / H)
    html = f"""
    <div style="display:flex;justify-content:center;">
      <div style="position:relative;width:{box_w}px;height:{box_h}px;
                  background:#000;border-radius:6px;overflow:hidden;">
        <video src="{video_url}" autoplay loop muted playsinline
               style="position:absolute;top:0;left:0;width:100%;height:100%;
                      object-fit:cover;"></video>
        <img src="{overlay_url}" alt=""
             style="position:absolute;top:0;left:0;width:100%;height:100%;
                    object-fit:cover;pointer-events:none;"/>
      </div>
    </div>
    """
    components.html(html, height=box_h + 24)


# --- プレビュー表示エリア（右カラム） --------------------------------------
with col2:
    st.subheader("👀 プレビュー")
    overlay, error = create_overlay()

    if error:
        st.error(error)
    else:
        mode = st.radio(
            "プレビュー方式",
            ["静止（位置調整用）", "動画（動きの確認）"],
            horizontal=True,
            help="位置はまず静止で詰めて、最後に動画で最終確認するのが速い。",
        )

        if video_file is not None:
            suffix = os.path.splitext(video_file.name)[1].lower() or ".mp4"
            vbytes = video_file.getvalue()
        else:
            suffix, vbytes = None, None

        if mode.startswith("動画") and vbytes:
            mime = MIME_MAP.get(suffix, "video/mp4")
            render_live_preview(video_data_url(vbytes, mime), overlay_data_url(overlay))
            st.caption("実素材をそのまま再生して重ねています。書き出し結果と同じ切り取りになります。")
        else:
            if vbytes:
                frame, frame_err = extract_frame(vbytes, suffix, preview_at)
                if frame is None:
                    st.warning(f"背景フレームを取得できませんでした。\n\n{frame_err}")
                    bg = Image.new("RGBA", (W, H), (18, 18, 18, 255))
                else:
                    bg = frame
            else:
                bg = Image.new("RGBA", (W, H), (18, 18, 18, 255))
                st.caption("背景動画をアップすると、実際のフレームに対して位置を調整できます。")
            st.image(Image.alpha_composite(bg, overlay), use_container_width=True)

        st.markdown("---")

        # --- MP4書き出し ---
        if st.button("🎬 MP4を書き出す", type="primary",
                     use_container_width=True, disabled=vbytes is None):
            with st.spinner("合成中..."):
                try:
                    st.session_state["mp4_bytes"] = build_mp4(
                        vbytes, suffix, overlay,
                        duration=duration, fps=fps, loop_bg=loop_bg,
                    )
                except RuntimeError as err:
                    st.session_state["mp4_bytes"] = None
                    st.error(str(err))

        if st.session_state.get("mp4_bytes"):
            st.download_button(
                label="⬇️ MP4をダウンロード",
                data=st.session_state["mp4_bytes"],
                file_name="reel.mp4",
                mime="video/mp4",
                use_container_width=True,
            )

        # --- 透過PNG書き出し（別編集用の保険） ---
        buf = io.BytesIO()
        overlay.save(buf, format="PNG")
        st.download_button(
            label="⬇️ 透過PNGをダウンロード（クロマキー不要）",
            data=buf.getvalue(),
            file_name="reels_overlay.png",
            mime="image/png",
            use_container_width=True,
        )

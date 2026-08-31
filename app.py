import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import io
import os
import shutil
import subprocess
import tempfile

# --- 基本設定 ---
st.set_page_config(page_title="AIリール生成ツール", layout="wide")

FONT_PATH = "font.ttf"
BASE_IMAGE_PATH = "base.png"   # 動画未アップ時のプレビュー背景としてのみ使用
W, H = 1080, 1920


# --- ffmpeg ユーティリティ -------------------------------------------------
def find_ffmpeg():
    """システムのffmpeg、無ければimageio-ffmpeg同梱のバイナリを返す。"""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return None


@st.cache_data(show_spinner=False)
def extract_frame(video_bytes, suffix):
    """背景動画から1フレーム抜き、1080x1920にセンタークロップして返す。"""
    exe = find_ffmpeg()
    if not exe:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in" + suffix)
        dst = os.path.join(tmp, "frame.png")
        with open(src, "wb") as f:
            f.write(video_bytes)
        cmd = [
            exe, "-y", "-ss", "0.5", "-i", src, "-frames:v", "1",
            "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
            dst,
        ]
        if subprocess.run(cmd, capture_output=True).returncode != 0:
            # 0.5秒地点が無い短尺素材への保険
            cmd[3] = "0"
            if subprocess.run(cmd, capture_output=True).returncode != 0:
                return None
        if not os.path.exists(dst):
            return None
        frame = Image.open(dst)
        frame.load()
        return frame.convert("RGBA").copy()


def build_mp4(video_bytes, suffix, overlay_img, duration, fps, loop_bg):
    """背景動画の上に透過PNGを重ねてMP4のバイト列を返す。"""
    exe = find_ffmpeg()
    if not exe:
        raise RuntimeError(
            "ffmpegが見つかりません。ローカルなら `pip install imageio-ffmpeg`、"
            "Streamlit Cloudならリポジトリ直下の packages.txt に `ffmpeg` を追記してください。"
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


# --- リセット用のカウンター（Key）の管理 -----------------------------------
if "reset_counter" not in st.session_state:
    st.session_state["reset_counter"] = 0


# --- サイドバー（デザイン・レイアウト調整） --------------------------------
st.sidebar.title("⚙️ デザイン設定")

st.sidebar.subheader("【背景・動画設定】")
scrim = st.sidebar.slider(
    "背景の暗幕（文字の可読性）", 0, 220, 110,
    help="0で動画そのまま。上げるほど背景が沈み、白文字が読みやすくなる。",
)
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


# --- テキストレイヤー生成（完全透過） --------------------------------------
def create_text_layer():
    """背景は透明。暗幕＋テキストだけを載せたRGBA画像を返す。"""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    if scrim > 0:
        veil = Image.new("RGBA", (W, H), (0, 0, 0, scrim))
        layer = Image.alpha_composite(layer, veil)

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


def preview_background():
    """プレビュー用の下地。動画があれば実フレーム、無ければbase.pngかベタ黒。"""
    if video_file is not None:
        suffix = os.path.splitext(video_file.name)[1] or ".mp4"
        frame = extract_frame(video_file.getvalue(), suffix)
        if frame is not None:
            return frame
    try:
        return Image.open(BASE_IMAGE_PATH).convert("RGBA").resize((W, H))
    except FileNotFoundError:
        return Image.new("RGBA", (W, H), (18, 18, 18, 255))


# --- プレビュー表示エリア（右カラム） --------------------------------------
with col2:
    st.subheader("👀 プレビュー")
    layer, error = create_text_layer()

    if error:
        st.error(error)
    else:
        composed = Image.alpha_composite(preview_background(), layer)
        st.image(composed, use_container_width=True)

        if video_file is None:
            st.caption("背景動画をアップすると、実際のフレームに対して位置を調整できます。")

        # --- MP4書き出し ---
        if st.button("🎬 MP4を書き出す", type="primary",
                     use_container_width=True, disabled=video_file is None):
            suffix = os.path.splitext(video_file.name)[1] or ".mp4"
            with st.spinner("合成中..."):
                try:
                    mp4_bytes = build_mp4(
                        video_file.getvalue(), suffix, layer,
                        duration=duration, fps=fps, loop_bg=loop_bg,
                    )
                except RuntimeError as err:
                    st.error(str(err))
                    mp4_bytes = None

            if mp4_bytes:
                st.session_state["mp4_bytes"] = mp4_bytes

        if st.session_state.get("mp4_bytes"):
            st.video(st.session_state["mp4_bytes"])
            st.download_button(
                label="⬇️ MP4をダウンロード",
                data=st.session_state["mp4_bytes"],
                file_name="reel.mp4",
                mime="video/mp4",
                use_container_width=True,
            )

        # --- 透過PNG書き出し（Premiere等で別編集したい場合の保険） ---
        buf = io.BytesIO()
        layer.save(buf, format="PNG")
        st.download_button(
            label="⬇️ 透過PNGをダウンロード（クロマキー不要）",
            data=buf.getvalue(),
            file_name="reels_overlay.png",
            mime="image/png",
            use_container_width=True,
        )

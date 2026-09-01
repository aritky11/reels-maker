import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import hashlib
import io
import os
import shutil
import subprocess
import tempfile

# --- 基本設定 ---
st.set_page_config(page_title="AIリール生成ツール", layout="wide")

FONT_PATH = "font.ttf"
BASE_IMAGE_PATH = "base.png"   # 装飾（枠・ヘッダー）の供給元。緑は抜いて使う
W, H = 1080, 1920

# --- 固定値（UIから外した設定。変えたいときはここを書き換える） -------------
USE_DECORATION = True      # base.pngの枠・ヘッダーを重ねるか
GREEN_TOLERANCE = 18       # 緑の抜き具合。装飾が消えるなら下げる／緑が残るなら上げる
PREVIEW_FRAME_SEC = 0.5    # 静止プレビューに使う、動画の何秒地点か


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


def build_mp4(video_bytes, suffix, overlay_img, duration, fps, loop_bg,
              out_w=W, out_h=H, preset="medium", crf=20):
    """背景動画の上に透過PNGを重ねてMP4のバイト列を返す。

    out_w / out_h を小さくし preset を軽くすると、確認用の高速プレビューになる。
    合成のロジックは本番と共通なので、見え方は必ず一致する。
    """
    exe = find_ffmpeg()
    if not exe:
        raise RuntimeError(
            "ffmpegが見つかりません。ローカルなら `pip install imageio-ffmpeg`、"
            "Streamlit Cloudなら requirements.txt に `imageio-ffmpeg` を追加してください。"
        )

    # x264は偶数サイズを要求する
    out_w -= out_w % 2
    out_h -= out_h % 2

    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in" + suffix)
        png = os.path.join(tmp, "overlay.png")
        out = os.path.join(tmp, "reel.mp4")
        with open(src, "wb") as f:
            f.write(video_bytes)
        overlay_img.resize((out_w, out_h), Image.LANCZOS).save(png)

        cmd = [exe, "-y"]
        if loop_bg:
            cmd += ["-stream_loop", "-1"]
        cmd += [
            "-i", src,
            "-i", png,
            "-filter_complex",
            (
                f"[0:v]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                f"crop={out_w}:{out_h},setsar=1,fps={fps}[bg];"
                "[bg][1:v]overlay=0:0:format=auto[v]"
            ),
            "-map", "[v]",
            "-t", str(duration),
            "-an",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",      # Instagram互換とブラウザ再生に必須
            "-preset", preset,
            "-crf", str(crf),
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


# --- セッション初期化 ------------------------------------------------------
for k, v in {"reset_counter": 0, "show_video": False,
             "prev_bytes": None, "prev_fp": None,
             "mp4_bytes": None, "mp4_fp": None}.items():
    st.session_state.setdefault(k, v)


# --- サイドバー ------------------------------------------------------------
st.sidebar.title("⚙️ デザイン設定")

_exe = find_ffmpeg()
if _exe:
    st.sidebar.success("ffmpeg 検出済み")
else:
    st.sidebar.error(
        "ffmpegが見つかりません。\n\n"
        "ローカル: `pip install imageio-ffmpeg`\n\n"
        "Streamlit Cloud: requirements.txt に `imageio-ffmpeg` を追加"
    )

st.sidebar.subheader("【表示設定】")
preview_pct = st.sidebar.slider(
    "プレビューの大きさ（%）", 20, 100, 55, step=5,
    help="表示上の大きさだけを変えます。書き出される動画には影響しません。",
)

st.sidebar.subheader("【背景・動画設定】")
scrim = st.sidebar.slider(
    "背景の暗幕（文字の可読性）", 0, 220, 110,
    help="0で動画そのまま。上げるほど背景が沈み、白文字が読みやすくなる。",
)
prev_len = st.sidebar.slider("動作確認の尺（秒）", 2.0, 10.0, 4.0, step=1.0)
duration = st.sidebar.slider("本番動画の尺（秒）", 3.0, 30.0, 8.0, step=0.5)
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

    if USE_DECORATION:
        deco = keyed_decoration(BASE_IMAGE_PATH, GREEN_TOLERANCE)
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


def settings_fingerprint(overlay_img, video_bytes):
    """現在の見た目を表す指紋。生成済み動画が古いかどうかの判定に使う。"""
    h = hashlib.md5()
    h.update(overlay_img.tobytes())
    h.update(str(len(video_bytes) if video_bytes else 0).encode())
    h.update(f"{duration}-{prev_len}-{fps}-{loop_bg}".encode())
    return h.hexdigest()


def preview_slot(pct):
    """プレビューを表示する枠。左右に余白カラムを入れて幅を絞る。"""
    f = max(0.05, min(pct / 100.0, 1.0))
    if f >= 0.99:
        return st.container()
    pad = (1.0 - f) / (2.0 * f)
    _left, center, _right = st.columns([pad, 1.0, pad])
    return center


# --- プレビュー表示エリア（右カラム） --------------------------------------
with col2:
    overlay, error = create_overlay()
    if error:
        st.error(error)
        st.stop()

    if video_file is not None:
        suffix = os.path.splitext(video_file.name)[1].lower() or ".mp4"
        vbytes = video_file.getvalue()
    else:
        suffix, vbytes = None, None

    fp = settings_fingerprint(overlay, vbytes)

    # 設定が変わったら自動で静止に戻す（古い映像を見続けないため）
    stale = st.session_state["prev_bytes"] is not None and st.session_state["prev_fp"] != fp
    if stale:
        st.session_state["show_video"] = False

    head, btn = st.columns([1, 1])
    with head:
        st.subheader("👀 プレビュー")
    with btn:
        if st.session_state["show_video"]:
            if st.button("🖼 静止に戻す", use_container_width=True):
                st.session_state["show_video"] = False
                st.rerun()
        else:
            if st.button("▶️ 動きを確認する", use_container_width=True, disabled=vbytes is None):
                with st.spinner("プレビューを生成中..."):
                    try:
                        st.session_state["prev_bytes"] = build_mp4(
                            vbytes, suffix, overlay,
                            duration=min(prev_len, duration), fps=fps, loop_bg=loop_bg,
                            out_w=540, out_h=960, preset="ultrafast", crf=30,
                        )
                        st.session_state["prev_fp"] = fp
                        st.session_state["show_video"] = True
                        st.rerun()
                    except RuntimeError as err:
                        st.error(str(err))

    slot = preview_slot(preview_pct)

    if st.session_state["show_video"] and st.session_state["prev_bytes"]:
        with slot:
            st.video(st.session_state["prev_bytes"], loop=True, autoplay=True, muted=True)
        st.caption("動作確認モード。本番と同じ合成処理で、解像度と画質だけ落としています。")
    else:
        if vbytes:
            frame, frame_err = extract_frame(vbytes, suffix, PREVIEW_FRAME_SEC)
            if frame is None:
                st.warning(f"背景フレームを取得できませんでした。\n\n{frame_err}")
                bg = Image.new("RGBA", (W, H), (18, 18, 18, 255))
            else:
                bg = frame
        else:
            bg = Image.new("RGBA", (W, H), (18, 18, 18, 255))
            st.caption("背景動画をアップすると、実際のフレームに対して位置を調整できます。")

        with slot:
            st.image(Image.alpha_composite(bg, overlay), use_container_width=True)

        if stale:
            st.caption("設定を変更したので静止表示に戻しました。もう一度「動きを確認する」で再生成できます。")

    st.markdown("---")
    st.subheader("⬇️ 書き出し")

    if st.button("🎬 本番MP4を書き出す（1080x1920）", type="primary",
                 use_container_width=True, disabled=vbytes is None):
        with st.spinner("合成中... 尺によっては1分ほどかかります"):
            try:
                st.session_state["mp4_bytes"] = build_mp4(
                    vbytes, suffix, overlay,
                    duration=duration, fps=fps, loop_bg=loop_bg,
                )
                st.session_state["mp4_fp"] = fp
            except RuntimeError as err:
                st.session_state["mp4_bytes"] = None
                st.error(str(err))

    if st.session_state["mp4_bytes"]:
        if st.session_state["mp4_fp"] != fp:
            st.warning("下のMP4は、変更前の設定で書き出したものです。")
        st.download_button(
            label="⬇️ MP4をダウンロード",
            data=st.session_state["mp4_bytes"],
            file_name="reel.mp4",
            mime="video/mp4",
            use_container_width=True,
        )

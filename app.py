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
st.set_page_config(page_title="レイラ 投稿生成ツール", layout="wide")

FONT_PATH = "font.ttf"
BASE_IMAGE_PATH = "base.png"   # 装飾（枠・ヘッダー）の供給元。緑は抜いて使う

# 出力サイズ（モードで切り替える）
REEL_W, REEL_H = 1080, 1920   # リール 9:16
FEED_W, FEED_H = 1080, 1350   # フィード 4:5

# --- 固定値（UIから外した設定。変えたいときはここを書き換える） -------------
GREEN_TOLERANCE = 18       # 緑の抜き具合。装飾が消えるなら下げる／緑が残るなら上げる
PREVIEW_FRAME_SEC = 0.5    # 静止プレビューに使う、動画の何秒地点か

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


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
def extract_frame(video_bytes, suffix, at_sec, cw, ch):
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
                "-vf", f"scale={cw}:{ch}:force_original_aspect_ratio=increase,crop={cw}:{ch}",
                dst,
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode == 0 and os.path.exists(dst):
                frame = Image.open(dst)
                frame.load()
                return frame.convert("RGBA").copy(), None
            last_err = proc.stderr[-800:]
        return None, f"フレーム抽出に失敗しました:\n{last_err}"


def cover_resize(img, cw, ch):
    """アスペクト比を保ったまま、指定サイズを覆うように拡大して中央で切り出す。"""
    src_w, src_h = img.size
    scale = max(cw / src_w, ch / src_h)
    nw, nh = max(1, int(src_w * scale + 0.5)), max(1, int(src_h * scale + 0.5))
    img = img.convert("RGBA").resize((nw, nh), Image.LANCZOS)
    left, top = (nw - cw) // 2, (nh - ch) // 2
    return img.crop((left, top, left + cw, top + ch))


def build_mp4(video_bytes, suffix, overlay_img, duration, fps, loop_bg,
              out_w=REEL_W, out_h=REEL_H, preset="medium", crf=20):
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
def keyed_decoration(path, tolerance, cw, ch):
    """緑背景のbase.pngから緑を透明化し、枠やヘッダーだけを残したRGBAを返す。

    縦横比が違うキャンバスでも装飾を縦に潰さない。
    幅だけ比率どおりに合わせ、高さは中央を捨てて上下の飾りを残す。
    """
    try:
        img = Image.open(path).convert("RGBA")
    except FileNotFoundError:
        return None

    sw, sh = img.size

    # 幅をキャンバスに合わせる（縦横比は保つ）
    if sw != cw:
        nh = max(1, int(sh * cw / sw + 0.5))
        img = img.resize((cw, nh), Image.LANCZOS)
        sw, sh = cw, nh

    # 高さの調整：潰さずに、上下の装飾だけを残す
    if sh > ch:
        canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        top_h = ch // 2
        bot_h = ch - top_h
        canvas.paste(img.crop((0, 0, cw, top_h)), (0, 0))
        canvas.paste(img.crop((0, sh - bot_h, cw, sh)), (0, ch - bot_h))
        img = canvas
    elif sh < ch:
        canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        top_h = sh // 2
        bot_h = sh - top_h
        canvas.paste(img.crop((0, 0, cw, top_h)), (0, 0))
        canvas.paste(img.crop((0, top_h, cw, sh)), (0, ch - bot_h))
        img = canvas

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

MODE_REEL = "リール（MP4・1080×1920）"
MODE_FEED = "フィード（PNG・1080×1350）"
output_mode = st.sidebar.radio("出力形式", [MODE_REEL, MODE_FEED], index=0)
is_feed = output_mode == MODE_FEED

CW, CH = (FEED_W, FEED_H) if is_feed else (REEL_W, REEL_H)
mode_key = "feed" if is_feed else "reel"

_exe = find_ffmpeg()
if _exe:
    st.sidebar.success("ffmpeg 検出済み")
else:
    msg = (
        "ffmpegが見つかりません。\n\n"
        "ローカル: `pip install imageio-ffmpeg`\n\n"
        "Streamlit Cloud: requirements.txt に `imageio-ffmpeg` を追加"
    )
    if is_feed:
        st.sidebar.info(msg + "\n\n※PNG出力だけならffmpegは不要です。")
    else:
        st.sidebar.error(msg)

st.sidebar.subheader("【表示設定】")
preview_pct = st.sidebar.slider(
    "プレビューの大きさ（%）", 20, 100, 55, step=5,
    help="表示上の大きさだけを変えます。書き出される画像・動画には影響しません。",
)

st.sidebar.subheader("【背景設定】")
use_decoration = st.sidebar.checkbox(
    "装飾枠（base.png）を重ねる", value=True,
    help="base.pngは9:16向けなので、フィード（4:5）では縦に詰まって見えることがあります。",
)
scrim = st.sidebar.slider(
    "背景の暗幕（文字の可読性）", 0, 220, 110,
    help="0で背景そのまま。上げるほど背景が沈み、白文字が読みやすくなる。",
)

if is_feed:
    # フィードでは動画設定は使わないが、指紋計算のために値だけ持たせる
    prev_len, duration, fps, loop_bg = 4.0, 8.0, 30, True
    feed_bg_mode = st.sidebar.selectbox(
        "背景の種類", ["単色（#000000）", "アップロードした素材を使う"], index=0,
    )
else:
    feed_bg_mode = None
    st.sidebar.subheader("【動画設定】")
    prev_len = st.sidebar.slider("動作確認の尺（秒）", 2.0, 10.0, 4.0, step=1.0)
    duration = st.sidebar.slider("本番動画の尺（秒）", 3.0, 30.0, 8.0, step=0.5)
    fps = st.sidebar.selectbox("フレームレート", [24, 30, 60], index=1)
    loop_bg = st.sidebar.checkbox("背景素材が短い場合ループさせる", value=True)

st.sidebar.subheader("【太字・太さ設定】")
is_bold_title = st.sidebar.checkbox("タイトルを太字にする", value=True, key="b_title")
is_bold_body = st.sidebar.checkbox("本文を太字にする", value=False, key="b_body")
is_bold_footer = st.sidebar.checkbox("フッターを太字にする", value=True, key="b_footer")
bold_strength = st.sidebar.slider("太字の強度", 1.0, 3.0, 1.5, step=0.1)

# モードごとの既定値（1920基準の値を1350へ比例縮小したもの）
if is_feed:
    DEF = dict(size_title=72, y_title=115, y_title_max=400,
               size_body=42, size_footer=36,
               y_footer=1165, y_footer_min=700, y_footer_max=1330)
else:
    DEF = dict(size_title=80, y_title=160, y_title_max=500,
               size_body=45, size_footer=40,
               y_footer=1650, y_footer_min=1000, y_footer_max=1900)

with st.sidebar.expander("位置・サイズ・行間の微調整", expanded=True):

    run_id = st.session_state["reset_counter"]
    kk = f"{mode_key}_{run_id}"   # モードを跨いでも値が混ざらないようにする

    st.subheader("① タイトル設定")
    size_title = st.slider("タイトル文字サイズ", 30, 150, value=DEF["size_title"], key=f"s_title_{kk}")
    spacing_title = st.slider("タイトルの行間", 0, 50, value=10, key=f"sp_title_{kk}")
    y_title = st.slider("タイトル上下位置 (Y)", 30, DEF["y_title_max"], value=DEF["y_title"], key=f"y_title_{kk}")
    x_title_offset = st.slider("タイトル左右のズレ", -500, 500, value=0, key=f"x_title_{kk}")

    if st.button("🔄 タイトルを中央基準に戻す", use_container_width=True):
        st.session_state["reset_counter"] += 1
        st.rerun()

    st.markdown("---")
    st.subheader("② 本文設定")
    size_body = st.slider("本文文字サイズ", 20, 100, value=DEF["size_body"], key=f"s_body_{kk}")
    spacing_body = st.slider("本文の行間", 10, 100, value=30, key=f"sp_body_{kk}")
    y_body_offset = st.slider("本文上下のズレ (中央基準)", -500, 500, value=0, key=f"y_body_{kk}")
    x_body_offset = st.slider("本文左右のズレ", -500, 500, value=0, key=f"x_body_{kk}")

    if st.button("🔄 本文を中央基準に戻す", use_container_width=True):
        st.session_state["reset_counter"] += 1
        st.rerun()

    st.markdown("---")
    st.subheader("③ フッター設定")
    size_footer = st.slider("フッター文字サイズ", 20, 100, value=DEF["size_footer"], key=f"s_footer_{kk}")
    spacing_footer = st.slider("フッターの行間", 0, 50, value=10, key=f"sp_footer_{kk}")
    y_footer = st.slider("フッター上下位置 (Y)", DEF["y_footer_min"], DEF["y_footer_max"],
                         value=DEF["y_footer"], key=f"y_footer_{kk}")
    x_footer_offset = st.slider("フッター左右のズレ", -500, 500, value=0, key=f"x_footer_{kk}")

    if st.button("🔄 フッターを中央基準に戻す", use_container_width=True):
        st.session_state["reset_counter"] += 1
        st.rerun()


# --- メイン画面 ------------------------------------------------------------
st.title("🎬 レイラ 投稿生成ツール")
st.caption(f"現在の出力：{output_mode}")

col1, col2 = st.columns([1, 1.2])

with col1:
    if is_feed:
        st.subheader("🖼 背景素材（任意）")
        upload_types = ["png", "jpg", "jpeg", "webp", "mp4", "mov", "webm", "m4v"]
        upload_help = "未アップなら黒背景で書き出します。画像でも動画（1フレーム抽出）でも可。"
    else:
        st.subheader("🎞 背景動画")
        upload_types = ["mp4", "mov", "webm", "m4v"]
        upload_help = "未アップでもテキストレイヤーの調整はできます。"

    media_file = st.file_uploader(
        "Higgsfieldで生成したレイラの素材", type=upload_types, help=upload_help,
    )

    st.subheader("📝 テキスト入力")

    if is_feed:
        d_title = "【このアカウントについて】"
        d_body = (
            "レイラは、実在の人物ではないわ。\n\n"
            "ある男が2年かけて記録した、\n"
            "\"都合のいい関係\"を\n"
            "\"一生手放せない相手\"に変えた、\n"
            "その判断基準のログ。\n\n"
            "それを、女のあなたにも分かる言葉に\n"
            "翻訳するために生まれた人格が、レイラ。\n\n"
            "慰めも、共感も期待しないで。\n"
            "ここにあるのは、\n"
            "男という生き物の、動かしようのない事実だけ。"
        )
        d_footer = "信じるかどうかは、あなたが決めなさい。\n苦しくたっていい。その経験を、武器にするのよ。"
        body_h = 320
    else:
        d_title = "即レスする女が、\n男に飽きられる理由。"
        d_body = (
            "・即レスは「いつでも手に入る」という合図よ。\n"
            "・連絡を待つだけの女に、男は価値を感じない。\n"
            "・「俺に夢中だな」と確信されたら、そこで終了よ。\n"
            "・安心感を与えた瞬間、男は貴女を追うのをやめる。\n"
            "・画面にかじりつく暇があるなら、自分の生活を送りなさい。\n"
            "・追われたいなら、返信の速度を半分にしなさい。"
        )
        d_footer = "※本気で追われたい女以外は\n 今すぐこの画面を閉じなさい。"
        body_h = 250

    title_input = st.text_area("① タイトル", d_title, height=100, key=f"t_{mode_key}")
    body_input = st.text_area("② 本文", d_body, height=body_h, key=f"b_{mode_key}")
    footer_input = st.text_area("③ フッター", d_footer, height=100, key=f"f_{mode_key}")


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
def create_overlay(cw, ch):
    """暗幕 → 装飾 → テキスト の順に重ねた、背景が透明なRGBAを返す。

    戻り値は (画像, エラー文, 警告文)。
    """
    layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    warn = None

    if scrim > 0:
        layer = Image.alpha_composite(layer, Image.new("RGBA", (cw, ch), (0, 0, 0, scrim)))

    if use_decoration:
        deco = keyed_decoration(BASE_IMAGE_PATH, GREEN_TOLERANCE, cw, ch)
        if deco is not None:
            layer = Image.alpha_composite(layer, deco)

    draw = ImageDraw.Draw(layer)
    try:
        font_t = ImageFont.truetype(FONT_PATH, size_title)
        font_b = ImageFont.truetype(FONT_PATH, size_body)
        font_f = ImageFont.truetype(FONT_PATH, size_footer)
    except IOError:
        return None, "エラー: font.ttf が見つかりません。GitHubにフォントを配置してください。", None

    title_text = title_input.replace('\\n', '\n')
    body_text = body_input.replace('\\n', '\n')
    footer_text = footer_input.replace('\\n', '\n')

    # 1. タイトル描画 (中央揃え)
    bbox_t = draw.multiline_textbbox((0, 0), title_text, font=font_t, align="center", spacing=spacing_title)
    title_w, title_h = bbox_t[2] - bbox_t[0], bbox_t[3] - bbox_t[1]
    x_t = (cw - title_w) / 2 - bbox_t[0] + x_title_offset
    draw_text_with_bold(draw, (x_t, y_title), title_text, font=font_t, fill=(255, 255, 255, 255),
                        align="center", spacing=spacing_title, is_bold=is_bold_title, strength=bold_strength)
    title_bottom = y_title + title_h

    # 2. フッター描画 (中央揃え)
    bbox_f = draw.multiline_textbbox((0, 0), footer_text, font=font_f, align="center", spacing=spacing_footer)
    footer_w, footer_h = bbox_f[2] - bbox_f[0], bbox_f[3] - bbox_f[1]
    x_f = (cw - footer_w) / 2 - bbox_f[0] + x_footer_offset
    draw_text_with_bold(draw, (x_f, y_footer), footer_text, font=font_f, fill=(255, 255, 255, 255),
                        align="center", spacing=spacing_footer, is_bold=is_bold_footer, strength=bold_strength)

    # 3. 本文描画 (完全中央配置 ＆ 中央揃え)
    bbox_b = draw.multiline_textbbox((0, 0), body_text, font=font_b, align="center", spacing=spacing_body)
    body_w, body_h_px = bbox_b[2] - bbox_b[0], bbox_b[3] - bbox_b[1]
    x_b = (cw - body_w) / 2 - bbox_b[0] + x_body_offset

    available_space = y_footer - title_bottom
    y_b = title_bottom + (available_space - body_h_px) / 2 - bbox_b[1] + y_body_offset

    draw_text_with_bold(draw, (x_b, y_b), body_text, font=font_b, fill=(255, 255, 255, 255),
                        align="center", spacing=spacing_body, is_bold=is_bold_body, strength=bold_strength)

    # はみ出しの検知（フィードは面積が狭いので特に起きやすい）
    if body_h_px > available_space:
        warn = "本文がタイトルとフッターの間に収まっていません。文字サイズか行間を下げてください。"
    elif body_w > cw - 80 or title_w > cw - 80 or footer_w > cw - 80:
        warn = "文字が左右の余白を越えています。文字サイズを下げるか、改行を入れてください。"
    elif y_footer + footer_h > ch - 20:
        warn = "フッターが下端からはみ出しています。フッターのY位置を上げてください。"

    return layer, None, warn


def settings_fingerprint(overlay_img, media_bytes):
    """現在の見た目を表す指紋。生成済み動画が古いかどうかの判定に使う。"""
    h = hashlib.md5()
    h.update(overlay_img.tobytes())
    h.update(str(len(media_bytes) if media_bytes else 0).encode())
    h.update(f"{duration}-{prev_len}-{fps}-{loop_bg}-{mode_key}".encode())
    return h.hexdigest()


def preview_slot(pct):
    """プレビューを表示する枠。左右に余白カラムを入れて幅を絞る。"""
    f = max(0.05, min(pct / 100.0, 1.0))
    if f >= 0.99:
        return st.container()
    pad = (1.0 - f) / (2.0 * f)
    _left, center, _right = st.columns([pad, 1.0, pad])
    return center


def png_bytes_from(image_rgba):
    """RGBAを、Instagramが受け付けるRGBのPNGバイト列にする。"""
    buf = io.BytesIO()
    image_rgba.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# --- プレビュー表示エリア（右カラム） --------------------------------------
with col2:
    overlay, error, warn = create_overlay(CW, CH)
    if error:
        st.error(error)
        st.stop()

    if media_file is not None:
        suffix = os.path.splitext(media_file.name)[1].lower() or ".mp4"
        mbytes = media_file.getvalue()
        is_still = suffix in IMAGE_EXTS
    else:
        suffix, mbytes, is_still = None, None, False

    fp = settings_fingerprint(overlay, mbytes)

    # 設定が変わったら自動で静止に戻す（古い映像を見続けないため）
    stale = st.session_state["prev_bytes"] is not None and st.session_state["prev_fp"] != fp
    if stale:
        st.session_state["show_video"] = False

    head, btn = st.columns([1, 1])
    with head:
        st.subheader("👀 プレビュー")
    with btn:
        if is_feed:
            st.write("")   # フィードは常に静止なのでボタンなし
        elif st.session_state["show_video"]:
            if st.button("🖼 静止に戻す", use_container_width=True):
                st.session_state["show_video"] = False
                st.rerun()
        else:
            if st.button("▶️ 動きを確認する", use_container_width=True, disabled=mbytes is None):
                with st.spinner("プレビューを生成中..."):
                    try:
                        st.session_state["prev_bytes"] = build_mp4(
                            mbytes, suffix, overlay,
                            duration=min(prev_len, duration), fps=fps, loop_bg=loop_bg,
                            out_w=540, out_h=960, preset="ultrafast", crf=30,
                        )
                        st.session_state["prev_fp"] = fp
                        st.session_state["show_video"] = True
                        st.rerun()
                    except RuntimeError as err:
                        st.error(str(err))

    slot = preview_slot(preview_pct)

    # 背景の決定
    def resolve_background():
        """プレビュー／PNG書き出しに使う不透明な背景を返す。"""
        if is_feed and feed_bg_mode == "単色（#000000）":
            return Image.new("RGBA", (CW, CH), (0, 0, 0, 255)), None
        if mbytes is None:
            fallback = (0, 0, 0, 255) if is_feed else (18, 18, 18, 255)
            return Image.new("RGBA", (CW, CH), fallback), None
        if is_still:
            try:
                return cover_resize(Image.open(io.BytesIO(mbytes)), CW, CH), None
            except Exception as e:
                return Image.new("RGBA", (CW, CH), (0, 0, 0, 255)), f"画像を読めませんでした: {e}"
        frame, frame_err = extract_frame(mbytes, suffix, PREVIEW_FRAME_SEC, CW, CH)
        if frame is None:
            return Image.new("RGBA", (CW, CH), (18, 18, 18, 255)), frame_err
        return frame, None

    if (not is_feed) and st.session_state["show_video"] and st.session_state["prev_bytes"]:
        with slot:
            st.video(st.session_state["prev_bytes"], loop=True, autoplay=True, muted=True)
        st.caption("動作確認モード。本番と同じ合成処理で、解像度と画質だけ落としています。")
        composed = None
    else:
        bg, bg_err = resolve_background()
        if bg_err:
            st.warning(bg_err)
        composed = Image.alpha_composite(bg, overlay)
        with slot:
            st.image(composed, use_container_width=True)

        if mbytes is None and not is_feed:
            st.caption("背景動画をアップすると、実際のフレームに対して位置を調整できます。")
        if stale:
            st.caption("設定を変更したので静止表示に戻しました。もう一度「動きを確認する」で再生成できます。")

    if warn:
        st.warning(warn)

    st.markdown("---")
    st.subheader("⬇️ 書き出し")

    if is_feed:
        # PNGは軽いので、ボタンを挟まず即ダウンロードできる
        if composed is None:
            bg, _ = resolve_background()
            composed = Image.alpha_composite(bg, overlay)
        st.download_button(
            label=f"⬇️ PNGをダウンロード（{FEED_W}×{FEED_H}）",
            data=png_bytes_from(composed),
            file_name="feed.png",
            mime="image/png",
            type="primary",
            use_container_width=True,
        )
        st.caption("上のプレビューがそのまま書き出されます。")
    else:
        if st.button(f"🎬 本番MP4を書き出す（{REEL_W}x{REEL_H}）", type="primary",
                     use_container_width=True, disabled=mbytes is None):
            with st.spinner("合成中... 尺によっては1分ほどかかります"):
                try:
                    st.session_state["mp4_bytes"] = build_mp4(
                        mbytes, suffix, overlay,
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

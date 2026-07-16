/* ============================================================
   AIリール動画自動生成ツール（ブラウザ完結版）
   - Canvas APIでプレビュー画像(1080x1920)を描画
   - スマート・リサイズ（はみ出し防止のための自動フォント縮小）
   - PNGとして高画質(1080x1920)ダウンロード
   ============================================================ */

const CANVAS_W = 1080;
const CANVAS_H = 1920;
const FONT_FAMILY = "NotoSerifJPCustom";
const SIDE_MARGIN = 90; // 左右マージン（デザイン枠に文字が被らないように）
const MAX_TEXT_WIDTH = CANVAS_W - SIDE_MARGIN * 2;
const ABSOLUTE_MIN_FONT_SIZE = 14;

const canvas = document.getElementById("previewCanvas");
const ctx = canvas.getContext("2d");

let baseImage = null;
let baseImageLoaded = false;
let fontReady = false;

/* ---------------- 入力要素の参照 ---------------- */
const el = (id) => document.getElementById(id);

const inputs = {
  boldTitle: el("boldTitle"),
  boldBody: el("boldBody"),
  boldFooter: el("boldFooter"),
  boldStrength: el("boldStrength"),

  autoFitEnabled: el("autoFitEnabled"),
  minScalePercent: el("minScalePercent"),

  sizeTitle: el("sizeTitle"),
  spacingTitle: el("spacingTitle"),
  yTitle: el("yTitle"),
  xTitleOffset: el("xTitleOffset"),

  sizeBody: el("sizeBody"),
  spacingBody: el("spacingBody"),
  yBodyOffset: el("yBodyOffset"),
  xBodyOffset: el("xBodyOffset"),

  sizeFooter: el("sizeFooter"),
  spacingFooter: el("spacingFooter"),
  yFooter: el("yFooter"),
  xFooterOffset: el("xFooterOffset"),

  titleInput: el("titleInput"),
  bodyInput: el("bodyInput"),
  footerInput: el("footerInput"),
};

/* デフォルト値（リセットボタン用） */
const DEFAULTS = {
  sizeTitle: 80, spacingTitle: 10, yTitle: 160, xTitleOffset: 0,
  sizeBody: 45, spacingBody: 30, yBodyOffset: 0, xBodyOffset: 0,
  sizeFooter: 40, spacingFooter: 10, yFooter: 1650, xFooterOffset: 0,
};

/* スライダーの値表示を更新するmap */
const valueSpanMap = {
  boldStrength: "boldStrengthVal",
  minScalePercent: "minScalePercentVal",
  sizeTitle: "sizeTitleVal",
  spacingTitle: "spacingTitleVal",
  yTitle: "yTitleVal",
  xTitleOffset: "xTitleOffsetVal",
  sizeBody: "sizeBodyVal",
  spacingBody: "spacingBodyVal",
  yBodyOffset: "yBodyOffsetVal",
  xBodyOffset: "xBodyOffsetVal",
  sizeFooter: "sizeFooterVal",
  spacingFooter: "spacingFooterVal",
  yFooter: "yFooterVal",
  xFooterOffset: "xFooterOffsetVal",
};

function refreshValueLabels() {
  for (const [inputId, spanId] of Object.entries(valueSpanMap)) {
    const inputEl = inputs[inputId];
    const spanEl = el(spanId);
    if (!inputEl || !spanEl) continue;
    if (inputId === "minScalePercent") {
      spanEl.textContent = `${inputEl.value}%`;
    } else {
      spanEl.textContent = inputEl.value;
    }
  }
}

/* ---------------- フォント・画像の読み込み ---------------- */
function loadFont() {
  const fontFace = new FontFace(FONT_FAMILY, "url('font.woff2') format('woff2')");
  return fontFace.load().then((loaded) => {
    document.fonts.add(loaded);
    fontReady = true;
  }).catch((err) => {
    console.error("フォントの読み込みに失敗しました", err);
    fontReady = true; // フォールバックフォントで続行
  });
}

function loadBaseImage() {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      baseImage = img;
      baseImageLoaded = true;
      resolve();
    };
    img.onerror = () => {
      console.error("base.png の読み込みに失敗しました");
      baseImageLoaded = false;
      resolve();
    };
    img.src = "base.png";
  });
}

/* ---------------- テキスト計測・自動縮小ロジック ---------------- */

// フォントの ascent/descent（行の高さ計算用）を取得
function getFontMetrics(measureCtx, cssFont, fallbackSize) {
  measureCtx.font = cssFont;
  const m = measureCtx.measureText("あ漢g");
  let ascent = m.fontBoundingBoxAscent;
  let descent = m.fontBoundingBoxDescent;
  if (!isFinite(ascent) || !isFinite(descent) || (ascent === 0 && descent === 0)) {
    // 古いブラウザ向けフォールバック（Noto Serif JP相当の比率で推定）
    ascent = fallbackSize * 0.93;
    descent = fallbackSize * 0.23;
  }
  return { ascent, descent };
}

// 複数行テキストのブロックサイズを計測
function measureBlock(measureCtx, text, size, spacing, weight) {
  const cssFont = `${weight} ${size}px "${FONT_FAMILY}"`;
  measureCtx.font = cssFont;
  const lines = text.split("\n");
  let maxLineWidth = 0;
  for (const line of lines) {
    const w = measureCtx.measureText(line).width;
    if (w > maxLineWidth) maxLineWidth = w;
  }
  const { ascent, descent } = getFontMetrics(measureCtx, cssFont, size);
  const lineHeight = ascent + descent;
  const totalHeight = lines.length > 0
    ? lineHeight * lines.length + spacing * (lines.length - 1)
    : 0;
  return { lines, maxLineWidth, ascent, descent, lineHeight, totalHeight, cssFont };
}

// スマート・リサイズ：指定した幅・高さに収まるまでフォントサイズと行間を縮小
function fitFontAndSpacing(measureCtx, text, baseSize, baseSpacing, maxWidth, maxHeight, weight, minScalePercent) {
  const minScale = minScalePercent / 100;
  const minSize = Math.max(ABSOLUTE_MIN_FONT_SIZE, Math.round(baseSize * minScale));

  let size = Math.max(Math.round(baseSize), ABSOLUTE_MIN_FONT_SIZE);
  let spacing = baseSpacing;
  let metrics = measureBlock(measureCtx, text, size, spacing, weight);

  while (true) {
    const fits = metrics.maxLineWidth <= maxWidth && metrics.totalHeight <= maxHeight;
    if (fits || size <= minSize) break;
    size = Math.max(size - 1, minSize);
    spacing = baseSpacing * (size / baseSize);
    metrics = measureBlock(measureCtx, text, size, spacing, weight);
  }

  const scale = baseSize > 0 ? size / baseSize : 1;
  return { size, spacing, metrics, scale };
}

/* ---------------- 描画処理 ---------------- */

// 疑似太字（肉付け）付きで複数行テキストを描画する
function drawTextBlock(drawCtx, text, centerX, topY, metrics, size, spacing, weight, isBold, strength) {
  drawCtx.font = `${weight} ${size}px "${FONT_FAMILY}"`;
  drawCtx.fillStyle = "#FFFFFF";
  drawCtx.textAlign = "center";
  drawCtx.textBaseline = "alphabetic";

  const lines = metrics.lines;
  const lineHeight = metrics.lineHeight;
  let baselineY = topY + metrics.ascent;

  for (const line of lines) {
    if (isBold) {
      for (const dx of [-strength, 0, strength]) {
        for (const dy of [-strength, 0, strength]) {
          drawCtx.fillText(line, centerX + dx, baselineY + dy);
        }
      }
    } else {
      drawCtx.fillText(line, centerX, baselineY);
    }
    baselineY += lineHeight + spacing;
  }
}

function normalizeText(raw) {
  return raw.replace(/\\n/g, "\n");
}

// メインのレンダリング関数：現在の入力値からプレビューを再描画する
function renderPreview() {
  if (!baseImageLoaded || !fontReady) return;

  // --- 背面画像を描画 ---
  ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);
  ctx.drawImage(baseImage, 0, 0, CANVAS_W, CANVAS_H);

  // --- 入力値を取得 ---
  const isBoldTitle = inputs.boldTitle.checked;
  const isBoldBody = inputs.boldBody.checked;
  const isBoldFooter = inputs.boldFooter.checked;
  const boldStrength = parseFloat(inputs.boldStrength.value);

  const autoFitEnabled = inputs.autoFitEnabled.checked;
  const minScalePercent = parseFloat(inputs.minScalePercent.value);

  const sizeTitle = parseFloat(inputs.sizeTitle.value);
  const spacingTitle = parseFloat(inputs.spacingTitle.value);
  const yTitle = parseFloat(inputs.yTitle.value);
  const xTitleOffset = parseFloat(inputs.xTitleOffset.value);

  const sizeBody = parseFloat(inputs.sizeBody.value);
  const spacingBody = parseFloat(inputs.spacingBody.value);
  const yBodyOffset = parseFloat(inputs.yBodyOffset.value);
  const xBodyOffset = parseFloat(inputs.xBodyOffset.value);

  const sizeFooter = parseFloat(inputs.sizeFooter.value);
  const spacingFooter = parseFloat(inputs.spacingFooter.value);
  const yFooter = parseFloat(inputs.yFooter.value);
  const xFooterOffset = parseFloat(inputs.xFooterOffset.value);

  const titleText = normalizeText(inputs.titleInput.value);
  const bodyText = normalizeText(inputs.bodyInput.value);
  const footerText = normalizeText(inputs.footerInput.value);

  const titleWeight = isBoldTitle ? "700" : "300";
  const bodyWeight = isBoldBody ? "700" : "300";
  const footerWeight = isBoldFooter ? "700" : "300";

  // 太字は横に肉付けされる分、幅の余裕を持たせる
  const titleBoldMargin = isBoldTitle ? boldStrength * 2 : 0;
  const bodyBoldMargin = isBoldBody ? boldStrength * 2 : 0;
  const footerBoldMargin = isBoldFooter ? boldStrength * 2 : 0;

  const fitInfo = { title: 1, body: 1, footer: 1 };

  // ---------- 1. タイトル：幅に収まるようにサイズを自動調整 ----------
  let titleFontSize, titleSpacingFit, titleMetrics;
  if (autoFitEnabled) {
    const fit = fitFontAndSpacing(
      ctx, titleText, sizeTitle, spacingTitle,
      MAX_TEXT_WIDTH - titleBoldMargin, Infinity, titleWeight, minScalePercent
    );
    titleFontSize = fit.size;
    titleSpacingFit = fit.spacing;
    titleMetrics = fit.metrics;
    fitInfo.title = fit.scale;
  } else {
    titleFontSize = sizeTitle;
    titleSpacingFit = spacingTitle;
    titleMetrics = measureBlock(ctx, titleText, titleFontSize, titleSpacingFit, titleWeight);
  }

  const titleCenterX = CANVAS_W / 2 + xTitleOffset;
  drawTextBlock(ctx, titleText, titleCenterX, yTitle, titleMetrics, titleFontSize, titleSpacingFit, titleWeight, isBoldTitle, boldStrength);
  const titleBottom = yTitle + titleMetrics.totalHeight;

  // ---------- 2. フッター：幅に収まるようにサイズを自動調整 ----------
  let footerFontSize, footerSpacingFit, footerMetrics;
  if (autoFitEnabled) {
    const fit = fitFontAndSpacing(
      ctx, footerText, sizeFooter, spacingFooter,
      MAX_TEXT_WIDTH - footerBoldMargin, Infinity, footerWeight, minScalePercent
    );
    footerFontSize = fit.size;
    footerSpacingFit = fit.spacing;
    footerMetrics = fit.metrics;
    fitInfo.footer = fit.scale;
  } else {
    footerFontSize = sizeFooter;
    footerSpacingFit = spacingFooter;
    footerMetrics = measureBlock(ctx, footerText, footerFontSize, footerSpacingFit, footerWeight);
  }

  const footerCenterX = CANVAS_W / 2 + xFooterOffset;
  drawTextBlock(ctx, footerText, footerCenterX, yFooter, footerMetrics, footerFontSize, footerSpacingFit, footerWeight, isBoldFooter, boldStrength);

  // ---------- 3. 本文：タイトル〜フッターの空きスペースに収まるように自動調整 ----------
  const availableSpace = Math.max(yFooter - titleBottom, 0);

  let bodyFontSize, bodySpacingFit, bodyMetrics;
  if (autoFitEnabled) {
    const verticalPadding = 40;
    const bodyMaxHeight = Math.max(availableSpace - verticalPadding * 2, 10);
    const fit = fitFontAndSpacing(
      ctx, bodyText, sizeBody, spacingBody,
      MAX_TEXT_WIDTH - bodyBoldMargin, bodyMaxHeight, bodyWeight, minScalePercent
    );
    bodyFontSize = fit.size;
    bodySpacingFit = fit.spacing;
    bodyMetrics = fit.metrics;
    fitInfo.body = fit.scale;
  } else {
    bodyFontSize = sizeBody;
    bodySpacingFit = spacingBody;
    bodyMetrics = measureBlock(ctx, bodyText, bodyFontSize, bodySpacingFit, bodyWeight);
  }

  const bodyCenterX = CANVAS_W / 2 + xBodyOffset;
  const bodyTopY = titleBottom + (availableSpace - bodyMetrics.totalHeight) / 2 + yBodyOffset;
  drawTextBlock(ctx, bodyText, bodyCenterX, bodyTopY, bodyMetrics, bodyFontSize, bodySpacingFit, bodyWeight, isBoldBody, boldStrength);

  updateFitNotice(fitInfo, autoFitEnabled);
}

/* ---------------- 自動縮小通知 ---------------- */
function updateFitNotice(fitInfo, autoFitEnabled) {
  const notice = el("fitNotice");
  const labelMap = { title: "タイトル", body: "本文", footer: "フッター" };
  const shrunk = Object.entries(fitInfo).filter(([, scale]) => scale < 0.999);

  if (autoFitEnabled && shrunk.length > 0) {
    const details = shrunk.map(([name, scale]) => `${labelMap[name]}: ${Math.round(scale * 100)}%`).join(" / ");
    notice.textContent = `📐 はみ出し防止のため、文字サイズを自動縮小しました（${details}）`;
    notice.hidden = false;
  } else {
    notice.hidden = true;
  }
}

/* ---------------- 再描画のスケジューリング（デバウンス） ---------------- */
let renderScheduled = false;
function scheduleRender() {
  if (renderScheduled) return;
  renderScheduled = true;
  requestAnimationFrame(() => {
    renderScheduled = false;
    renderPreview();
  });
}

/* ---------------- イベント登録 ---------------- */
function attachEvents() {
  // すべてのスライダー・チェックボックス・テキストエリアの変更で再描画
  const watchedInputs = [
    inputs.boldTitle, inputs.boldBody, inputs.boldFooter, inputs.boldStrength,
    inputs.autoFitEnabled, inputs.minScalePercent,
    inputs.sizeTitle, inputs.spacingTitle, inputs.yTitle, inputs.xTitleOffset,
    inputs.sizeBody, inputs.spacingBody, inputs.yBodyOffset, inputs.xBodyOffset,
    inputs.sizeFooter, inputs.spacingFooter, inputs.yFooter, inputs.xFooterOffset,
    inputs.titleInput, inputs.bodyInput, inputs.footerInput,
  ];

  watchedInputs.forEach((inputEl) => {
    if (!inputEl) return;
    const eventName = (inputEl.tagName === "TEXTAREA") ? "input" : "input";
    inputEl.addEventListener(eventName, () => {
      refreshValueLabels();
      scheduleRender();
    });
  });

  // リセットボタン（各セクションのスライダーのみを初期値に戻す）
  el("resetTitleBtn").addEventListener("click", () => {
    inputs.sizeTitle.value = DEFAULTS.sizeTitle;
    inputs.spacingTitle.value = DEFAULTS.spacingTitle;
    inputs.yTitle.value = DEFAULTS.yTitle;
    inputs.xTitleOffset.value = DEFAULTS.xTitleOffset;
    refreshValueLabels();
    scheduleRender();
  });

  el("resetBodyBtn").addEventListener("click", () => {
    inputs.sizeBody.value = DEFAULTS.sizeBody;
    inputs.spacingBody.value = DEFAULTS.spacingBody;
    inputs.yBodyOffset.value = DEFAULTS.yBodyOffset;
    inputs.xBodyOffset.value = DEFAULTS.xBodyOffset;
    refreshValueLabels();
    scheduleRender();
  });

  el("resetFooterBtn").addEventListener("click", () => {
    inputs.sizeFooter.value = DEFAULTS.sizeFooter;
    inputs.spacingFooter.value = DEFAULTS.spacingFooter;
    inputs.yFooter.value = DEFAULTS.yFooter;
    inputs.xFooterOffset.value = DEFAULTS.xFooterOffset;
    refreshValueLabels();
    scheduleRender();
  });

  // 高画質PNGダウンロード（キャンバスは常に1080x1920のネイティブ解像度で描画されている）
  el("downloadBtn").addEventListener("click", () => {
    canvas.toBlob((blob) => {
      if (!blob) {
        alert("画像の生成に失敗しました。もう一度お試しください。");
        return;
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "reels_image.png";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    }, "image/png");
  });
}

/* ---------------- 初期化 ---------------- */
async function init() {
  refreshValueLabels();
  attachEvents();
  await Promise.all([loadFont(), loadBaseImage()]);
  renderPreview();
}

init();

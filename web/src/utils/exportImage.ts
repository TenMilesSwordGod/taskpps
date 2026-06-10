/**
 * 图片导出工具：使用动态 import 让 html-to-image 仅在用户点击导出时加载，
 * 避免首屏或非导出页面承担约 30 KB gzip 体积。
 */

/** 内部缓存：避免同会话内重复动态 import */
let loaderPromise: Promise<typeof import('html-to-image')> | null = null;

function loadHtmlToImage() {
  if (!loaderPromise) loaderPromise = import('html-to-image');
  return loaderPromise;
}

/** 导出为 PNG */
export async function exportAsPng(element: HTMLElement, filename = 'pipeline.png') {
  const { toPng } = await loadHtmlToImage();
  const dataUrl = await toPng(element, { backgroundColor: '#ffffff' });
  const link = document.createElement('a');
  link.download = filename;
  link.href = dataUrl;
  link.click();
}

/** 导出为 SVG */
export async function exportAsSvg(element: HTMLElement, filename = 'pipeline.svg') {
  const { toSvg } = await loadHtmlToImage();
  const dataUrl = await toSvg(element, { backgroundColor: '#ffffff' });
  const link = document.createElement('a');
  link.download = filename;
  link.href = dataUrl;
  link.click();
}

/** 复制到剪贴板 */
export async function copyToClipboard(element: HTMLElement) {
  const { toBlob } = await loadHtmlToImage();
  const blob = await toBlob(element, { backgroundColor: '#ffffff' });
  if (!blob) throw new Error('生成图片失败');
  await navigator.clipboard.write([
    new ClipboardItem({ 'image/png': blob }),
  ]);
}

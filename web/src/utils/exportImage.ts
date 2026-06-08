import { toPng, toSvg, toBlob } from 'html-to-image';

/** 导出为 PNG */
export async function exportAsPng(element: HTMLElement, filename = 'pipeline.png') {
  const dataUrl = await toPng(element, { backgroundColor: '#ffffff' });
  const link = document.createElement('a');
  link.download = filename;
  link.href = dataUrl;
  link.click();
}

/** 导出为 SVG */
export async function exportAsSvg(element: HTMLElement, filename = 'pipeline.svg') {
  const dataUrl = await toSvg(element, { backgroundColor: '#ffffff' });
  const link = document.createElement('a');
  link.download = filename;
  link.href = dataUrl;
  link.click();
}

/** 复制到剪贴板 */
export async function copyToClipboard(element: HTMLElement) {
  const blob = await toBlob(element, { backgroundColor: '#ffffff' });
  if (!blob) throw new Error('生成图片失败');
  await navigator.clipboard.write([
    new ClipboardItem({ 'image/png': blob }),
  ]);
}

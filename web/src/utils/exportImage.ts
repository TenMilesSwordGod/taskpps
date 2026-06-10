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

/** 通用导出选项：处理 ReactFlow SVG 元素的兼容性 */
const commonOptions = {
  backgroundColor: '#ffffff',
  pixelRatio: 2,
  // 跳过无法序列化的字体和跨域资源
  skipFonts: true,
  // 包含内联样式以确保节点正确渲染
  includeQueryParams: true,
};

/** 导出为 PNG */
export async function exportAsPng(element: HTMLElement, filename = 'pipeline.png') {
  const { toPng } = await loadHtmlToImage();
  try {
    const dataUrl = await toPng(element, commonOptions);
    const link = document.createElement('a');
    link.download = filename;
    link.href = dataUrl;
    link.click();
  } catch (e) {
    // 回退：使用 canvas 截图
    console.warn('html-to-image toPng failed, trying canvas fallback:', e);
    await exportWithCanvas(element, filename);
  }
}

/** 导出为 SVG */
export async function exportAsSvg(element: HTMLElement, filename = 'pipeline.svg') {
  const { toSvg } = await loadHtmlToImage();
  try {
    const dataUrl = await toSvg(element, commonOptions);
    const link = document.createElement('a');
    link.download = filename;
    link.href = dataUrl;
    link.click();
  } catch (e) {
    // SVG 导出失败时回退到 PNG
    console.warn('html-to-image toSvg failed, falling back to PNG:', e);
    await exportAsPng(element, filename.replace('.svg', '.png'));
  }
}

/** 复制到剪贴板 */
export async function copyToClipboard(element: HTMLElement) {
  const { toBlob } = await loadHtmlToImage();
  try {
    const blob = await toBlob(element, commonOptions);
    if (!blob) throw new Error('生成图片失败');
    await navigator.clipboard.write([
      new ClipboardItem({ 'image/png': blob }),
    ]);
  } catch (e) {
    // 回退：复制为文本描述
    console.warn('html-to-image toBlob failed, trying canvas fallback:', e);
    try {
      const canvas = await renderToCanvas(element);
      const blob = await new Promise<Blob | null>((resolve) =>
        canvas.toBlob(resolve, 'image/png')
      );
      if (!blob) throw new Error('Canvas 生成图片失败');
      await navigator.clipboard.write([
        new ClipboardItem({ 'image/png': blob }),
      ]);
    } catch {
      throw new Error('复制失败，请尝试导出下载');
    }
  }
}

/** Canvas 回退方案：将 DOM 元素渲染到 canvas */
async function renderToCanvas(element: HTMLElement): Promise<HTMLCanvasElement> {
  const { toPng } = await loadHtmlToImage();
  const dataUrl = await toPng(element, { ...commonOptions, pixelRatio: 1 });

  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        reject(new Error('无法创建 Canvas 2D 上下文'));
        return;
      }
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0);
      resolve(canvas);
    };
    img.onerror = () => reject(new Error('图片加载失败'));
    img.src = dataUrl;
  });
}

/** Canvas 回退导出 */
async function exportWithCanvas(element: HTMLElement, filename: string) {
  const canvas = await renderToCanvas(element);
  const link = document.createElement('a');
  link.download = filename;
  link.href = canvas.toDataURL('image/png');
  link.click();
}

import { describe, it, expect, vi, beforeEach } from 'vitest'

/** 拦截动态 import：单元测试不真正执行导出逻辑（避免 jsdom 截屏），只验证入口 */
const htmlToImageMock = {
  toPng: vi.fn(async () => 'data:image/png;base64,AAA'),
  toSvg: vi.fn(async () => 'data:image/svg+xml;base64,AAA'),
  toBlob: vi.fn(async () => new Blob(['x'], { type: 'image/png' })),
}
vi.mock('html-to-image', () => htmlToImageMock)

import { exportAsPng, exportAsSvg, copyToClipboard } from './exportImage'

function makeElement(): HTMLElement {
  return document.createElement('div')
}

describe('utils/exportImage', () => {
  beforeEach(() => {
    htmlToImageMock.toPng.mockClear()
    htmlToImageMock.toSvg.mockClear()
    htmlToImageMock.toBlob.mockClear()
  })

  it('exportAsPng 调用 toPng 并触发下载', async () => {
    const el = makeElement()
    await exportAsPng(el, 'test.png')
    expect(htmlToImageMock.toPng).toHaveBeenCalledTimes(1)
    expect(htmlToImageMock.toPng).toHaveBeenCalledWith(el, { backgroundColor: '#ffffff' })
  })

  it('exportAsSvg 调用 toSvg 并触发下载', async () => {
    const el = makeElement()
    await exportAsSvg(el, 'test.svg')
    expect(htmlToImageMock.toSvg).toHaveBeenCalledTimes(1)
  })

  it('copyToClipboard 调用 toBlob 并写入 ClipboardItem', async () => {
    const writeTextSpy = vi.fn()
    const writeSpy = vi.fn(async () => undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { write: writeSpy, writeText: writeTextSpy },
      configurable: true,
    })
    const el = makeElement()
    await copyToClipboard(el)
    expect(htmlToImageMock.toBlob).toHaveBeenCalledTimes(1)
    expect(writeSpy).toHaveBeenCalledTimes(1)
  })

  it('copyToClipboard 在 toBlob 返回 null 时抛错', async () => {
    htmlToImageMock.toBlob.mockResolvedValueOnce(null)
    const el = makeElement()
    await expect(copyToClipboard(el)).rejects.toThrow('生成图片失败')
  })
})

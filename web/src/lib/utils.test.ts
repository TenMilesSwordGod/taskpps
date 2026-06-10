import { describe, it, expect } from 'vitest'
import { cn } from './utils'

describe('cn()', () => {
  it('拼接简单字符串', () => {
    expect(cn('a', 'b')).toBe('a b')
  })

  it('过滤 falsy 值（false / null / undefined / 0 / ""）', () => {
    expect(cn('a', false, null, undefined, '', 'b', 0)).toBe('a b')
  })

  it('支持 clsx 对象语法', () => {
    expect(cn('a', { b: true, c: false })).toBe('a b')
  })

  it('支持数组', () => {
    expect(cn(['a', 'b'], { c: true })).toBe('a b c')
  })

  it('空入参返回空字符串', () => {
    expect(cn()).toBe('')
  })
})

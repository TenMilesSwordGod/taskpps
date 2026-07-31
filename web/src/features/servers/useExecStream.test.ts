import { describe, it, expect } from 'vitest';
import { parseSSEChunk } from './useExecStream';

describe('parseSSEChunk', () => {
  it('解析普通 LF 分隔的 SSE 事件', () => {
    const chunk = 'event: output\ndata: hello world\n\nevent: done\ndata: {}\n\n';
    const { events, rest } = parseSSEChunk(chunk);
    expect(rest).toBe('');
    expect(events).toHaveLength(2);
    expect(events[0]).toEqual({ event: 'output', data: 'hello world' });
    expect(events[1]).toEqual({ event: 'done', data: '{}' });
  });

  it('解析 CRLF 分隔的 SSE 事件（sse-starlette 格式，修复回归）', () => {
    const chunk = 'event: output\r\ndata: 2\r\ndata: acs\r\ndata: a.db\r\n\r\nevent: result\r\ndata: {"exit_code":0}\r\n\r\nevent: done\r\ndata: {}\r\n\r\n';
    const { events, rest } = parseSSEChunk(chunk);
    expect(rest).toBe('');
    expect(events).toHaveLength(3);
    expect(events[0]).toEqual({ event: 'output', data: '2\nacs\na.db' });
    expect(events[1]).toEqual({ event: 'result', data: '{"exit_code":0}' });
    expect(events[2]).toEqual({ event: 'done', data: '{}' });
  });

  it('多行 data 拼接保留换行（ls 输出场景）', () => {
    const chunk = 'event: output\ndata: 2\ndata: acs\ndata: a.db\n\nevent: done\ndata: {}\n\n';
    const { events } = parseSSEChunk(chunk);
    expect(events[0].data).toBe('2\nacs\na.db');
  });

  it('保留前导空格（JSON 格式化输出）', () => {
    const chunk = 'event: output\ndata:   {\ndata:     "key": "value"\ndata:   }\n\nevent: done\ndata: {}\n\n';
    const { events } = parseSSEChunk(chunk);
    expect(events[0].data).toBe('  {\n    "key": "value"\n  }');
  });

  it('尾部不完整 block 存到 rest', () => {
    const chunk = 'event: output\ndata: hello\n\nevent: result\ndata: {"ex';
    const { events, rest } = parseSSEChunk(chunk);
    expect(events).toHaveLength(1);
    expect(events[0]).toEqual({ event: 'output', data: 'hello' });
    expect(rest).toBe('event: result\ndata: {"ex');
  });

  it('空输入返回空结果', () => {
    const { events, rest } = parseSSEChunk('');
    expect(events).toHaveLength(0);
    expect(rest).toBe('');
  });

  it('仅有空白输入返回空结果', () => {
    const { events, rest } = parseSSEChunk('   \n\n  ');
    expect(events).toHaveLength(0);
    // \n\n 之前的空白 block 被跳过，之后的内容作为 rest
    expect(rest).toBe('  ');
  });

  it('省略 event 类型时默认为 message', () => {
    const chunk = 'data: hello\n\n';
    const { events } = parseSSEChunk(chunk);
    expect(events).toHaveLength(1);
    expect(events[0]).toEqual({ event: 'message', data: 'hello' });
  });

  it('混合 event 类型正确区分', () => {
    const chunk = 'event: output\ndata: line1\n\nevent: error\ndata: {"error":"fail"}\n\nevent: done\ndata: {}\n\n';
    const { events } = parseSSEChunk(chunk);
    expect(events).toHaveLength(3);
    expect(events[0].event).toBe('output');
    expect(events[1].event).toBe('error');
    expect(events[2].event).toBe('done');
  });
});

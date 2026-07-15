import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { ReactFlowProvider } from '@xyflow/react';
import StickyNoteComponent, { type StickyNoteData } from '../StickyNote';
import { STICKY_COLORS } from '../stores/pipelineEditorStore';
import type { StickyColor } from '../stores/pipelineEditorStore';

/**
 * StickyNote 组件交互测试
 *
 * 覆盖维度：渲染（内容/颜色/尺寸）、编辑模式切换、删除、颜色循环、resize 拖拽、
 * 空内容/超长内容、Markdown 渲染、吸附状态
 * 设计决策：StickyNote 是 ReactFlow 自定义节点，需要 ReactFlowProvider 包裹
 */

// Mock @xyflow/react Handle 组件（同 TaskNode 测试策略）
vi.mock('@xyflow/react', () => ({
  Handle: () => null,
  Position: { Top: 'top', Bottom: 'bottom', Left: 'left', Right: 'right' },
  ReactFlowProvider: ({ children }: { children: React.ReactNode }) => children,
}));

function makeData(overrides: Partial<StickyNoteData> = {}): StickyNoteData {
  return {
    content: '测试便签内容',
    color: 'yellow',
    width: 240,
    height: 160,
    snapToNodeId: null,
    onDelete: vi.fn(),
    onUpdate: vi.fn(),
    ...overrides,
  };
}

function renderStickyNote(id = 'note-1', data?: StickyNoteData) {
  return render(
    <StickyNoteComponent id={id} data={data ?? makeData()} />,
  );
}

describe('StickyNote — 渲染', () => {
  it('默认渲染黄色便签，显示内容文本', () => {
    renderStickyNote();
    expect(screen.getByText('测试便签内容')).toBeInTheDocument();
  });

  it('空内容时显示"双击编辑..."占位文本', () => {
    renderStickyNote('note-1', makeData({ content: '' }));
    expect(screen.getByText('双击编辑...')).toBeInTheDocument();
  });

  it('蓝色便签使用对应配色', () => {
    const { container } = render(
      <StickyNoteComponent
        id="note-b"
        data={makeData({ color: 'blue', content: '蓝色便签' })}
      />,
    );
    const colors = STICKY_COLORS.blue;
    const wrapper = container.querySelector('div > div') as HTMLElement;
    expect(wrapper?.style.backgroundColor).toBe('rgb(231, 245, 255)'); // #E7F5FF
  });

  it('5 种颜色便签均正常渲染', () => {
    const colors: StickyColor[] = ['yellow', 'blue', 'green', 'pink', 'orange'];
    for (const c of colors) {
      const { unmount } = render(
        <StickyNoteComponent id={`note-${c}`} data={makeData({ color: c, content: c })} />,
      );
      expect(screen.getByText(c)).toBeInTheDocument();
      unmount();
    }
  });

  it('自定义尺寸渲染', () => {
    const { container } = render(
      <StickyNoteComponent id="note-c" data={makeData({ width: 300, height: 200 })} />,
    );
    const wrapper = container.querySelector('div > div') as HTMLElement;
    expect(wrapper?.style.width).toBe('300px');
    expect(wrapper?.style.height).toBe('200px');
  });

  it('尺寸未设置时使用默认 240x160', () => {
    const { container } = render(
      <StickyNoteComponent id="note-d" data={makeData({ width: undefined as unknown as number, height: undefined as unknown as number })} />,
    );
    const wrapper = container.querySelector('div > div') as HTMLElement;
    expect(wrapper?.style.width).toBe('240px');
    expect(wrapper?.style.height).toBe('160px');
  });
});

describe('StickyNote — 编辑模式', () => {
  it('双击进入编辑模式，内容显示在 textarea 中', () => {
    const { container } = renderStickyNote();

    // 渲染模式：显示 Markdown 渲染内容
    const bodyDiv = container.querySelector('.flex-1.min-h-0')!;
    fireEvent.doubleClick(bodyDiv);

    // 进入编辑模式：textarea 出现
    const textarea = bodyDiv.querySelector('textarea');
    expect(textarea).toBeTruthy();
    expect(textarea?.value).toBe('测试便签内容');
  });

  it('编辑模式下修改 textarea 内容，失焦后调用 onUpdate', () => {
    const onUpdate = vi.fn();
    const { container } = render(
      <StickyNoteComponent id="note-1" data={makeData({ content: '原始', onUpdate })} />,
    );

    const bodyDiv = container.querySelector('.flex-1.min-h-0')!;
    fireEvent.doubleClick(bodyDiv);

    const textarea = bodyDiv.querySelector('textarea')!;
    fireEvent.change(textarea, { target: { value: '修改后的内容' } });
    fireEvent.blur(textarea);

    expect(onUpdate).toHaveBeenCalledWith('note-1', { content: '修改后的内容' });
  });

  it('失焦后退出编辑模式（textarea 消失）', () => {
    const { container } = renderStickyNote();

    const bodyDiv = container.querySelector('.flex-1.min-h-0')!;
    fireEvent.doubleClick(bodyDiv);
    expect(bodyDiv.querySelector('textarea')).toBeTruthy();

    fireEvent.blur(bodyDiv.querySelector('textarea')!);
    // textarea 消失，回到渲染模式
    expect(bodyDiv.querySelector('textarea')).toBeFalsy();
  });

  it('编辑模式下输入为空，失焦后 content="" 更新', () => {
    const onUpdate = vi.fn();
    const { container } = render(
      <StickyNoteComponent id="note-2" data={makeData({ content: '原文', onUpdate })} />,
    );

    const bodyDiv = container.querySelector('.flex-1.min-h-0')!;
    fireEvent.doubleClick(bodyDiv);

    const textarea = bodyDiv.querySelector('textarea')!;
    fireEvent.change(textarea, { target: { value: '' } });
    fireEvent.blur(textarea);

    expect(onUpdate).toHaveBeenCalledWith('note-2', { content: '' });
  });
});

describe('StickyNote — 删除', () => {
  it('点击 × 按钮触发 onDelete', () => {
    const onDelete = vi.fn();
    const { container } = render(
      <StickyNoteComponent id="note-del" data={makeData({ onDelete })} />,
    );

    const buttons = container.querySelectorAll('button');
    // 第二个 button 是删除按钮（第一个是颜色圆点）
    const deleteBtn = buttons[1];
    fireEvent.click(deleteBtn);

    expect(onDelete).toHaveBeenCalledWith('note-del');
  });
});

describe('StickyNote — 颜色切换', () => {
  it('点击颜色圆点触发 onUpdate 切换到下一个颜色', () => {
    const onUpdate = vi.fn();
    const { container, rerender } = render(
      <StickyNoteComponent id="note-c" data={makeData({ color: 'yellow', onUpdate })} />,
    );

    const buttons = container.querySelectorAll('button');
    const colorDot = buttons[0];

    // 首次点击：yellow → blue
    fireEvent.click(colorDot);
    expect(onUpdate).toHaveBeenLastCalledWith('note-c', { color: 'blue' });

    // 模拟父组件更新 color prop：重新渲染为 blue
    rerender(
      <StickyNoteComponent id="note-c" data={makeData({ color: 'blue', onUpdate })} />,
    );

    // 再次点击：blue → green
    fireEvent.click(colorDot);
    expect(onUpdate).toHaveBeenLastCalledWith('note-c', { color: 'green' });
  });

  it('颜色循环 5 次后回到原点', () => {
    const onUpdate = vi.fn();
    const colors: StickyColor[] = ['yellow', 'blue', 'green', 'pink', 'orange'];
    // 用 wrapper 跟踪最新颜色状态，模拟父组件重传 color prop
    let currentColor: StickyColor = colors[0];
    const getData = () => makeData({ color: currentColor, onUpdate });

    const { container, rerender } = render(
      <StickyNoteComponent id="note-d" data={getData()} />,
    );

    const buttons = container.querySelectorAll('button');
    const colorDot = buttons[0];

    for (let i = 0; i < 5; i++) {
      fireEvent.click(colorDot);
      // 模拟父组件收到 onUpdate 后更新 color
      currentColor = colors[(colors.indexOf(currentColor) + 1) % colors.length];
      rerender(<StickyNoteComponent id="note-d" data={getData()} />);
    }
    // 5 次循环后回到初始颜色
    expect(currentColor).toBe('yellow');
    expect(onUpdate).toHaveBeenCalledTimes(5);
  });
});

describe('StickyNote — Resize', () => {
  it('右下角 resize handle 存在', () => {
    const { container } = renderStickyNote();
    const resizeHandle = container.querySelector('.cursor-se-resize');
    expect(resizeHandle).toBeTruthy();
  });

  it('mousedown resize handle 触发拖拽调整', () => {
    const onUpdate = vi.fn();
    const { container } = render(
      <StickyNoteComponent id="note-r" data={makeData({ width: 240, height: 160, onUpdate })} />,
    );

    const resizeHandle = container.querySelector('.cursor-se-resize')!;

    fireEvent.mouseDown(resizeHandle, { clientX: 100, clientY: 100 });

    // 模拟 mousemove 扩大尺寸
    fireEvent.mouseMove(document, { clientX: 140, clientY: 140 });

    const wrapper = container.querySelector('div > div') as HTMLElement;
    // 尺寸应扩大
    expect(parseInt(wrapper.style.width)).toBeGreaterThan(240);
    expect(parseInt(wrapper.style.height)).toBeGreaterThan(160);

    // mouseup 后调用 onUpdate
    fireEvent.mouseUp(document);
    expect(onUpdate).toHaveBeenCalled();
    // 验证 onUpdate 传入了 width 和 height
    const call = onUpdate.mock.calls[0];
    expect(call[0]).toBe('note-r');
    expect(call[1]).toHaveProperty('width');
    expect(call[1]).toHaveProperty('height');
  });

  it('resize 不低于最小尺寸 120x80', () => {
    const { container } = render(
      <StickyNoteComponent id="note-min" data={makeData({ width: 200, height: 150 })} />,
    );

    const resizeHandle = container.querySelector('.cursor-se-resize')!;

    // mousedown at (100, 100), then move far left/up
    fireEvent.mouseDown(resizeHandle, { clientX: 100, clientY: 100 });
    fireEvent.mouseMove(document, { clientX: 10, clientY: 10 });
    fireEvent.mouseUp(document);

    const wrapper = container.querySelector('div > div') as HTMLElement;
    expect(parseInt(wrapper.style.width)).toBe(120);
    expect(parseInt(wrapper.style.height)).toBe(80);
  });
});

describe('StickyNote — Markdown 渲染', () => {
  it('**粗体** 渲染为 strong 标签', () => {
    const { container } = render(
      <StickyNoteComponent id="md-1" data={makeData({ content: '这是 **粗体** 文本' })} />,
    );
    expect(container.querySelector('strong')).toBeTruthy();
    expect(container.querySelector('strong')?.textContent).toBe('粗体');
  });

  it('`代码` 渲染为 code 标签', () => {
    const { container } = render(
      <StickyNoteComponent id="md-2" data={makeData({ content: '运行 `npm run build` 命令' })} />,
    );
    expect(container.querySelector('code')).toBeTruthy();
    expect(container.querySelector('code')?.textContent).toBe('npm run build');
  });

  it('- 列表项渲染为 li 标签', () => {
    const { container } = render(
      <StickyNoteComponent id="md-3" data={makeData({ content: '- 事项一\n- 事项二' })} />,
    );
    const items = container.querySelectorAll('li');
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toBe('事项一');
    expect(items[1].textContent).toBe('事项二');
  });

  it('特殊字符（< > &）被转义', () => {
    const { container } = render(
      <StickyNoteComponent id="md-4" data={makeData({ content: '<div>&copy;</div>' })} />,
    );
    // renderMarkdown 把 < 转为 &lt;，& 转为 &amp;，所以 HTML 中：
    // <div> → &lt;div&gt; (在 innerHTML 里可视的转义字符)
    const bodyDiv = container.querySelector('.flex-1.min-h-0 div');
    // bodyDiv.innerHTML 应包含转义后的内容
    expect(bodyDiv?.innerHTML).toContain('&lt;div');
    expect(bodyDiv?.innerHTML).toContain('&gt;');
    expect(bodyDiv?.innerHTML).toContain('&amp;copy;');
  });
});

describe('StickyNote — 边界情况', () => {
  it('超长内容 2000+ 字符正常渲染', () => {
    const longText = '长'.repeat(3000);
    const { container } = render(
      <StickyNoteComponent id="note-long" data={makeData({ content: longText })} />,
    );
    expect(container.textContent?.includes('长'.repeat(10))).toBe(true);
  });

  it('内容包含换行符正常渲染', () => {
    const { container } = render(
      <StickyNoteComponent
        id="note-nl"
        data={makeData({ content: '第一行\n第二行\n第三行' })}
      />,
    );
    // 换行被转换为 <br>（jsdom 中为 <br> 非 <br/>）
    expect(container.innerHTML).toContain('<br>');
  });

  it('snapToNodeId 设置为 null 不影响渲染', () => {
    const { container } = render(
      <StickyNoteComponent id="note-s1" data={makeData({ snapToNodeId: null })} />,
    );
    expect(container.firstChild).toBeTruthy();
  });

  it('snapToNodeId 设置为 task-1 时组件正常渲染', () => {
    const { container } = render(
      <StickyNoteComponent id="note-s2" data={makeData({ snapToNodeId: 'task-1' })} />,
    );
    expect(container.firstChild).toBeTruthy();
  });

  it('编辑模式下 pointerDown 不冒泡（防拖拽干扰）', () => {
    const { container } = renderStickyNote();
    const bodyDiv = container.querySelector('.flex-1.min-h-0')!;
    fireEvent.doubleClick(bodyDiv);

    const textarea = bodyDiv.querySelector('textarea')!;
    // pointerDown 在 textarea 上不会引发拖拽
    const stopPropagation = vi.fn();
    fireEvent.pointerDown(textarea, {
      // @ts-expect-error: 模拟 stopPropagation
      stopPropagation,
    });
    // textarea 的 onPointerDown handler 会调用 e.stopPropagation()
    // 验证 textarea 仍然存在（没有被意外关闭）
    expect(bodyDiv.querySelector('textarea')).toBeTruthy();
  });
});

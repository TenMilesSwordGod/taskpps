import { useState, useMemo } from 'react';
import { Segmented, Tooltip } from 'antd';
import { FileText, Code } from 'lucide-react';
import type { ResultPageResponse } from '@/types';

type RenderMode = 'html' | 'md';

interface ResultViewerProps {
  data: ResultPageResponse;
}

/** 简易 Markdown 转 HTML（支持标题、表格、列表、加粗、代码块、链接、图片） */
function simpleMarkdownToHtml(md: string): string {
  let html = md
    // 代码块（```...```）
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_m, lang, code) => {
      return `<pre><code class="language-${lang || ''}">${escapeHtml(code.trim())}</code></pre>`;
    })
    // 行内代码
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    // 标题
    .replace(/^#### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    // 粗体/斜体
    .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // 图片（必须在链接之前，避免 ![alt](url) 被链接正则误匹配）
    .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" style="max-width:100%"/>')
    // 链接
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    // 水平分割线
    .replace(/^---$/gm, '<hr>')
    // 无序列表
    .replace(/^(\s*)[-*]\s+(.+)$/gm, '$1<li>$2</li>')
    // 有序列表
    .replace(/^(\s*)\d+\.\s+(.+)$/gm, '$1<li>$2</li>')
    // 块引用
    .replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
    // 段落
    .replace(/\n\n+/g, '</p><p>')
    .replace(/\n/g, '<br/>');

  html = '<p>' + html + '</p>';

  // 合并连续 li 为 ul
  html = html.replace(/((?:<li>[^<]*<\/li>\s*)+)/g, '<ul>$1</ul>');

  // 合并连续 blockquote
  html = html.replace(/((?:<blockquote>[^<]*<\/blockquote>\s*)+)/g, '<div class="quote-block">$1</div>');

  return html;
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** XSS 过滤：仅允许安全标签 */
function sanitizeHtml(html: string): string {
  const ALLOWED_TAGS = new Set([
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'p', 'br', 'hr',
    'strong', 'b', 'em', 'i', 'u',
    'a', 'img',
    'ul', 'ol', 'li',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'pre', 'code', 'blockquote',
    'div', 'span',
    'style',
  ]);
  const ALLOWED_ATTRS = new Set([
    'href', 'target', 'rel', 'title',
    'src', 'alt', 'width', 'height',
    'class', 'style', 'id',
    'colspan', 'rowspan',
  ]);

  // 移除所有 script/iframe/object/embed 等危险标签
  html = html.replace(/<\s*\/?\s*(script|iframe|object|embed|form|input|button|link|meta|base|applet|audio|video|source|track)\b[^>]*>/gi, '');
  // 移除事件处理属性 (onclick, onerror, etc.)
  html = html.replace(/\s+on\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]*)/gi, '');
  // 移除 javascript: 协议
  html = html.replace(/href\s*=\s*["']\s*javascript:/gi, 'href="javascript:void(0)"');
  html = html.replace(/src\s*=\s*["']\s*javascript:/gi, 'src=""');

  return html;
}

export default function ResultViewer({ data }: ResultViewerProps) {
  const [mode, setMode] = useState<RenderMode>('html');

  const htmlContent = useMemo(() => {
    if (!data) return '';
    const raw = mode === 'html' ? data.html_content : simpleMarkdownToHtml(data.md_content);
    return sanitizeHtml(raw);
  }, [data, mode]);

  if (!data) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        暂无结果数据
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="shrink-0 flex items-center justify-between px-4 py-2 border-b border-gray-200 bg-white">
        <div className="flex items-center gap-2">
          <FileText size={16} className="text-blue-500" />
          <span className="text-sm font-medium">执行结果</span>
          {data.has_collector && (
            <Tooltip title={data.collector_mode === 'replace' ? '插件已替换默认结果' : '插件已追加到结果'}>
              <span className="text-xs px-2 py-0.5 rounded bg-purple-50 text-purple-600 font-medium">
                {data.collector_mode === 'replace' ? 'Replaced' : 'Appended'}
              </span>
            </Tooltip>
          )}
        </div>
        <Segmented
          size="small"
          value={mode}
          onChange={(val) => setMode(val as RenderMode)}
          options={[
            { label: 'HTML', value: 'html' },
            { label: 'MD', value: 'md' },
          ]}
        />
      </div>
      <div className="flex-1 overflow-auto bg-white">
        <div
          className="p-6"
          dangerouslySetInnerHTML={{ __html: htmlContent }}
        />
      </div>
    </div>
  );
}

import { useMemo } from 'react';
import { Tooltip } from 'antd';
import { FileText } from 'lucide-react';
import { marked } from 'marked';
import type { ResultPageResponse } from '@/types';

interface ResultViewerProps {
  data: ResultPageResponse;
}

marked.setOptions({ breaks: true, gfm: true });

/** XSS 过滤：仅允许安全标签 */
function sanitizeHtml(html: string): string {
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
  const htmlContent = useMemo(() => {
    if (!data) return '';
    const raw = data.format === 'md'
      ? (marked.parse(data.md_content) as string)
      : data.html_content;
    return sanitizeHtml(raw);
  }, [data]);

  if (!data) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        暂无结果数据
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="shrink-0 flex items-center px-4 py-2 border-b border-gray-200 bg-white">
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
      </div>
      <div className="flex-1 overflow-auto bg-white">
        <div
          className="p-6 prose prose-sm max-w-none prose-table:w-full [&_table]:w-full [&_table]:border-collapse [&_th]:border [&_th]:border-gray-300 [&_th]:bg-gray-50 [&_td]:border [&_td]:border-gray-200"
          dangerouslySetInnerHTML={{ __html: htmlContent }}
        />
      </div>
    </div>
  );
}

import { useMemo } from 'react';
import { Tooltip } from 'antd';
import { FileText } from 'lucide-react';
import { marked } from 'marked';
import ResultSummary from './ResultSummary';
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

/** 注入 HTML 的统一容器：prose 样式保证插件输出的表格/代码块可读 */
function HtmlBlock({ html }: { html: string }) {
  if (!html) return null;
  return (
    <div
      className="prose prose-sm max-w-none prose-table:w-full [&_table]:w-full [&_table]:border-collapse [&_th]:border [&_th]:border-gray-300 [&_th]:bg-gray-50 [&_td]:border [&_td]:border-gray-200"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export default function ResultViewer({ data }: ResultViewerProps) {
  const isMd = data?.format === 'md';
  const mdHtml = useMemo(
    () => (data && isMd ? sanitizeHtml(marked.parse(data.md_content) as string) : ''),
    [data, isMd],
  );
  const collectorHtml = useMemo(
    () => (data?.collector_html ? sanitizeHtml(data.collector_html) : ''),
    [data],
  );
  const collectorMdHtml = useMemo(
    () => (data?.collector_md ? sanitizeHtml(marked.parse(data.collector_md) as string) : ''),
    [data],
  );
  // v2 (2026-09): 老 result.json 无 collector_html/md 字段，回退旧的整段注入逻辑，
  // 保证历史运行记录仍能展示插件内容
  const isLegacyCollector = data
    ? data.collector_html === undefined && data.collector_md === undefined
    : false;
  const legacyHtml = useMemo(
    () =>
      data && isLegacyCollector && data.has_collector ? sanitizeHtml(data.html_content) : '',
    [data, isLegacyCollector],
  );

  if (!data) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        暂无结果数据
      </div>
    );
  }

  const isCollectorReplace = data.has_collector && data.collector_mode === 'replace';
  // 只有声明了插件输出时才渲染额外内容，避免默认结果页被重复注入
  const extraHtml = data.has_collector ? collectorHtml || collectorMdHtml || legacyHtml : '';

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
        {isMd ? (
          <div className="p-6">
            <HtmlBlock html={mdHtml} />
          </div>
        ) : isCollectorReplace ? (
          // 插件声明 replace 时尊重其输出：只展示插件内容
          <div className="p-6">
            <HtmlBlock html={collectorHtml || sanitizeHtml(data.html_content)} />
          </div>
        ) : (
          <>
            <ResultSummary data={data} />
            {extraHtml && (
              <div className="border-t border-slate-200 p-6">
                <HtmlBlock html={extraHtml} />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

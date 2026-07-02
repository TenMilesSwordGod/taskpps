import { useMemo } from 'react'
import { Tooltip } from 'antd'
import exampleYamlText from './examplePipeline.yaml?raw'

interface VariableTooltip {
  pattern: string
  description: string
  example: string
}

const VARIABLE_TOOLTIPS: VariableTooltip[] = [
  {
    pattern: 'env.',
    description: '环境变量引用',
    example: '${env.CI_BRANCH} → main',
  },
  {
    pattern: 'credential:',
    description: '凭证引用',
    example: '${credential:docker-registry}',
  },
  {
    pattern: 'params.',
    description: '参数引用（触发运行时用户传入）',
    example: '${params.VERSION_TAG} → v2.0.0',
  },
  {
    pattern: 'task.',
    description: '上游任务输出',
    example: '${task.compile.output}',
  },
  {
    pattern: 'artifact:',
    description: '制品路径引用',
    example: '${artifact:dist/myapp.tar.gz}',
  },
  {
    pattern: 'agent:',
    description: 'Agent 属性引用',
    example: '${agent:builder.host} → 10.98.1.100',
  },
  {
    pattern: 'PIPELINE_ID',
    description: '当前 Pipeline 运行 ID',
    example: '12345',
  },
  {
    pattern: 'JOB_ID',
    description: '当前 Job 运行 ID',
    example: '67890',
  },
  {
    pattern: 'STEP_ID',
    description: '当前 Step 运行 ID',
    example: '11111',
  },
  {
    pattern: 'WORKSPACE',
    description: '工作目录路径',
    example: '/workspace/myapp',
  },
]

function findTooltip(varExp: string): VariableTooltip | undefined {
  return VARIABLE_TOOLTIPS.find((vt) => varExp.includes(vt.pattern))
}

/** YAML 关键词着色映射 */
const YAML_KEYWORD_CLASSES: Record<string, string> = {
  'version:': 'text-purple-600 font-semibold',
  'name:': 'text-blue-600 font-semibold',
  'pipelines:': 'text-orange-600 font-semibold',
  'stages:': 'text-orange-600 font-semibold',
  'params:': 'text-teal-600 font-semibold',
  'env:': 'text-teal-600 font-semibold',
  'tasks:': 'text-indigo-600 font-semibold',
  'config:': 'text-gray-600 font-semibold',
  'depends_on:': 'text-red-500 font-semibold',
  ' - name:': 'text-cyan-600',
  'command:': 'text-gray-500',
  'commands:': 'text-gray-500',
  'invoke:': 'text-gray-500',
  'steps:': 'text-gray-500',
  'git:': 'text-gray-500',
  'nexus:': 'text-gray-500',
  'ssh:': 'text-gray-500',
  'step:': 'text-gray-500',
  'when:': 'text-amber-600',
  'timeout:': 'text-rose-600',
  'retry:': 'text-rose-600',
  'on_failure:': 'text-rose-600',
  'host:': 'text-violet-600',
  'credential:': 'text-violet-600',
  'agent:': 'text-violet-600',
  'cwd:': 'text-slate-500',
  'type:': 'text-slate-500',
  'label:': 'text-slate-500',
  'default:': 'text-slate-500',
  'options:': 'text-slate-500',
  'execution_strategy:': 'text-emerald-600',
  'max_parallel:': 'text-emerald-600',
}

/** 字符串值着色 */
const STRING_VALUE_RE = /^\s*".*"\s*$/

/** 数字值着色 */
const NUMBER_VALUE_RE = /^\s*\d+\s*$/

/** 检测是否是注释行 */
function isCommentLine(line: string): boolean {
  return /^\s*#/.test(line)
}

/** 检测行是否包含 ${...} 变量 */
function hasVariableRef(line: string): boolean {
  return /\$\{[^}]+\}/.test(line)
}

/** 获取行的 CSS 类名 */
function getLineClass(line: string): string {
  if (isCommentLine(line)) return 'text-green-500 italic'

  const trimmed = line.trimStart()

  for (const [keyword, cls] of Object.entries(YAML_KEYWORD_CLASSES)) {
    if (trimmed.startsWith(keyword)) return cls
  }

  // 处理值颜色
  if (STRING_VALUE_RE.test(trimmed)) return 'text-amber-700'
  if (NUMBER_VALUE_RE.test(trimmed)) return 'text-cyan-700'

  return 'text-gray-300'
}

/** 将一行中包含 ${...} 的变量用 Tooltip 包裹 */
function renderLine(line: string, lineIndex: number): React.ReactNode {
  if (!hasVariableRef(line)) {
    const cls = getLineClass(line)
    return <span key={lineIndex} className={cls}>{line}{'\n'}</span>
  }

  const parts: React.ReactNode[] = []
  const re = /\$\{[^}]+\}/g
  let lastIndex = 0
  let match: RegExpExecArray | null
  let varIdx = 0

  while ((match = re.exec(line)) !== null) {
    const before = line.substring(lastIndex, match.index)
    if (before) {
      parts.push(
        <span key={`${lineIndex}-t-${varIdx}`}>{before}</span>,
      )
    }

    const varExp = match[0]
    const tooltip = findTooltip(varExp)
    const title = tooltip ? (
      <div style={{ fontSize: 12, lineHeight: 1.6 }}>
        <div><strong>{varExp}</strong></div>
        <div>类型：{tooltip.description}</div>
        <div>示例：<code style={{ fontSize: 11 }}>{tooltip.example}</code></div>
      </div>
    ) : varExp

    parts.push(
      <Tooltip key={`${lineIndex}-v-${varIdx}`} title={title}>
        <span className="var-ref bg-yellow-100 text-yellow-800 px-0.5 rounded cursor-help">
          {varExp}
        </span>
      </Tooltip>,
    )

    lastIndex = re.lastIndex
    varIdx++
  }

  const after = line.substring(lastIndex)
  if (after) {
    parts.push(
      <span key={`${lineIndex}-t-${varIdx}`}>{after}</span>,
    )
  }

  parts.push('\n')

  return <span key={lineIndex}>{parts}</span>
}

export default function ExamplePipelineView() {
  const lines = useMemo(() => exampleYamlText.split('\n'), [])

  return (
    <div data-testid="example-pipeline-content" className="overflow-auto" style={{ maxHeight: 'calc(100vh - 280px)' }}>
      <pre className="text-xs font-mono leading-relaxed whitespace-pre bg-gray-900 text-gray-200 p-3 rounded m-0 select-all">
        {lines.map((line, i) => renderLine(line, i))}
      </pre>
    </div>
  )
}

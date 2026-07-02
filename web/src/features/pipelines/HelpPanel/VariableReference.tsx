import { useMemo } from 'react'
import { Table, Tooltip, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'

const { Text } = Typography

interface VariableDef {
  name: string
  type: string
  description: string
  example: string
}

const BUILTIN_VARIABLES: VariableDef[] = [
  {
    name: '${env.XXX}',
    type: '环境变量',
    description: '引用环境变量，XXX 为变量名',
    example: '${env.CI_BRANCH} → main',
  },
  {
    name: '${credential:name}',
    type: '凭证',
    description: '引用凭证，name 为凭证名称',
    example: '${credential:docker-registry}',
  },
  {
    name: '${task.<name>.output}',
    type: '任务输出',
    description: '引用上游任务输出',
    example: '${task.compile.output}',
  },
  {
    name: '${params.XXX}',
    type: '参数',
    description: '引用 pipeline 参数（触发运行时传入）',
    example: '${params.VERSION_TAG}',
  },
  {
    name: '${artifact:path}',
    type: '制品',
    description: '引用制品路径',
    example: '${artifact:dist/myapp.tar.gz}',
  },
  {
    name: '${PIPELINE_ID}',
    type: '内置变量',
    description: '当前 Pipeline 运行 ID',
    example: '12345',
  },
  {
    name: '${JOB_ID}',
    type: '内置变量',
    description: '当前 Job 运行 ID',
    example: '67890',
  },
  {
    name: '${STEP_ID}',
    type: '内置变量',
    description: '当前 Step 运行 ID',
    example: '11111',
  },
  {
    name: '${WORKSPACE}',
    type: '内置变量',
    description: '工作目录路径',
    example: '/workspace/myapp',
  },
  {
    name: '${agent:<name>.host}',
    type: 'Agent 属性',
    description: '引用 Agent 的主机地址',
    example: '${agent:builder.host} → 10.98.1.100',
  },
  {
    name: '${agent:<name>.port}',
    type: 'Agent 属性',
    description: '引用 Agent 的端口号',
    example: '${agent:builder.port} → 22',
  },
]

const columns: ColumnsType<VariableDef> = [
  {
    title: '名称',
    dataIndex: 'name',
    key: 'name',
    width: 160,
    render: (name: string) => (
      <Tooltip title={name}>
        <Text code className="text-xs">{name}</Text>
      </Tooltip>
    ),
  },
  {
    title: '类型',
    dataIndex: 'type',
    key: 'type',
    width: 80,
  },
  {
    title: '说明',
    dataIndex: 'description',
    key: 'description',
  },
  {
    title: '示例值',
    dataIndex: 'example',
    key: 'example',
    width: 200,
    render: (example: string) => (
      <Text code className="text-xs">{example}</Text>
    ),
  },
]

export default function VariableReference() {
  const dataSource = useMemo(() => BUILTIN_VARIABLES, [])

  return (
    <div data-testid="variable-reference-content">
      <div className="mb-2 text-xs text-gray-500">
        以下变量可在 Pipeline YAML 中通过 <Text code className="text-xs">{'${name}'}</Text> 语法引用：
      </div>
      <Table
        rowKey="name"
        columns={columns}
        dataSource={dataSource}
        size="small"
        pagination={false}
        scroll={{ x: 600 }}
      />
    </div>
  )
}

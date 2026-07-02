import { Tabs, Button, Tooltip } from 'antd'
import {
  MinusOutlined,
  ExpandOutlined,
  QuestionCircleOutlined,
  BarsOutlined,
} from '@ant-design/icons'
import ExamplePipelineView from './ExamplePipelineView'
import VariableReference from './VariableReference'

interface HelpPanelProps {
  minimized: boolean
  onToggleMinimized: () => void
  maximized?: boolean
  onToggleMaximized?: () => void
}

export default function HelpPanel({
  minimized,
  onToggleMinimized,
  maximized = false,
  onToggleMaximized,
}: HelpPanelProps) {
  if (minimized) {
    return (
      <div
        data-testid="help-panel-minimized"
        className="flex flex-col items-center py-3 gap-3 bg-white border-l border-gray-200 cursor-pointer"
        style={{ width: 40 }}
        onClick={onToggleMinimized}
      >
        <Tooltip title="展开 Help 面板" placement="left">
          <Button
            type="text"
            size="small"
            icon={<QuestionCircleOutlined />}
          />
        </Tooltip>
      </div>
    )
  }

  return (
    <div
      data-testid="help-panel-expanded"
      className="flex flex-col bg-white border-l border-gray-200"
      style={{ width: maximized ? '70vw' : 480 }}
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200">
        <span className="text-sm font-medium text-gray-600">
          <QuestionCircleOutlined className="mr-1" />Help
        </span>
        <div className="flex gap-1">
          {onToggleMaximized && (
            <Tooltip title={maximized ? '还原' : '最大化'}>
              <Button
                type="text"
                size="small"
                icon={<ExpandOutlined />}
                onClick={onToggleMaximized}
              />
            </Tooltip>
          )}
          <Tooltip title="收起">
            <Button
              data-testid="help-panel-minimize-btn"
              type="text"
              size="small"
              icon={<MinusOutlined />}
              onClick={onToggleMinimized}
            />
          </Tooltip>
        </div>
      </div>

      <div className="flex-1 overflow-hidden">
        <Tabs
          size="small"
          className="h-full"
          tabBarStyle={{ paddingLeft: 12, paddingRight: 12, marginBottom: 0 }}
          items={[
            {
              key: 'example',
              label: (
                <span>
                  <BarsOutlined /> 示例 Pipeline
                </span>
              ),
              children: (
                <div className="px-2 pt-2 h-full">
                  <ExamplePipelineView />
                </div>
              ),
            },
            {
              key: 'variables',
              label: (
                <span>
                  <QuestionCircleOutlined /> 变量参考
                </span>
              ),
              children: (
                <div className="px-2 pt-2">
                  <VariableReference />
                </div>
              ),
            },
          ]}
        />
      </div>
    </div>
  )
}

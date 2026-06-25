import { useMemo, useState } from 'react'
import { Drawer, Spin, Empty, Alert, Tree, Button } from 'antd'
import { Download } from 'lucide-react'
import { useArtifacts } from '@/api/runs'
import type { ArtifactItem } from '@/types'
import type { DataNode } from 'antd/es/tree'

export interface ArtifactsDrawerProps {
  runId: string
  open: boolean
  onClose: () => void
}

interface ArtifactLeafNode extends DataNode {
  item: ArtifactItem
}

function buildTree(artifacts: ArtifactItem[]): ArtifactLeafNode[] {
  const groups: Record<string, ArtifactItem[]> = {}
  for (const item of artifacts) {
    if (!groups[item.task_name]) groups[item.task_name] = []
    groups[item.task_name].push(item)
  }
  return Object.entries(groups).map(([taskName, items]) => ({
    title: taskName,
    key: taskName,
    selectable: false,
    children: items.map((item) => ({
      title: item.path,
      key: `${item.task_name}/${item.path}`,
      item,
    })),
  }))
}

function getCheckedItems(checkedKeys: string[], tree: ArtifactLeafNode[]): ArtifactItem[] {
  const keys = new Set(checkedKeys)
  const items: ArtifactItem[] = []
  for (const node of tree) {
    for (const child of node.children || []) {
      if (keys.has(child.key as string)) {
        items.push((child as ArtifactLeafNode).item)
      }
    }
  }
  return items
}

export default function ArtifactsDrawer({ runId, open, onClose }: ArtifactsDrawerProps) {
  const { data, isLoading, error } = useArtifacts(open ? runId : undefined)
  const [checkedKeys, setCheckedKeys] = useState<string[]>([])

  const tree = useMemo(() => {
    if (!data?.artifacts?.length) return []
    return buildTree(data.artifacts)
  }, [data])

  const checkedItems = useMemo(() => getCheckedItems(checkedKeys, tree), [checkedKeys, tree])

  const handleDownload = () => {
    if (checkedItems.length === 0) return
    if (checkedItems.length === 1) {
      const item = checkedItems[0]
      window.open(`/api/runs/${runId}/artifacts/${item.task_name}/${item.path}`, '_blank')
    } else {
      window.open(`/api/runs/${runId}/artifacts/zip`, '_blank')
    }
  }

  if (!open) return null

  return (
    <Drawer title="Artifacts" open={open} onClose={onClose} width={480}>
      {isLoading ? (
        <Spin spinning />
      ) : error ? (
        <Alert type="error" message="Failed to load artifacts" />
      ) : !tree.length ? (
        <Empty description="No artifacts" />
      ) : (
        <>
          <Tree
            checkable
            defaultExpandAll
            treeData={tree}
            checkedKeys={checkedKeys}
            onCheck={(keys) => setCheckedKeys(keys as string[])}
            checkStrictly
          />
          <div style={{ marginTop: 16 }}>
            <Button
              type="primary"
              icon={<Download size={14} />}
              disabled={checkedItems.length === 0}
              onClick={handleDownload}
            >
              {checkedItems.length >= 2 ? '下载 zip' : '下载'}
            </Button>
          </div>
        </>
      )}
    </Drawer>
  )
}

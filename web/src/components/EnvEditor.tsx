import { useState, useEffect, useCallback, useRef } from 'react';
import { Input, Button, Tooltip, Row, Col } from 'antd';
import { PlusOutlined, DeleteOutlined, QuestionCircleOutlined } from '@ant-design/icons';

interface EnvEntry {
  id: number;
  key: string;
  value: string;
}

interface EnvEditorProps {
  value?: Record<string, string>;
  onChange?: (value: Record<string, string>) => void;
}

let nextId = 0;
function genId() {
  nextId += 1;
  return nextId;
}

function buildEntries(obj: Record<string, string> | undefined): EnvEntry[] {
  if (!obj || Object.keys(obj).length === 0) {
    return [{ id: genId(), key: '', value: '' }];
  }
  return Object.entries(obj).map(([k, v]) => ({ id: genId(), key: k, value: v }));
}

function entriesToObj(entries: EnvEntry[]): Record<string, string> {
  const result: Record<string, string> = {};
  for (const e of entries) {
    if (e.key.trim()) {
      result[e.key.trim()] = e.value;
    }
  }
  return result;
}

export default function EnvEditor({ value, onChange }: EnvEditorProps) {
  const [entries, setEntries] = useState<EnvEntry[]>(() => buildEntries(value));
  const valueRef = useRef(value);
  const syncingRef = useRef(false);

  useEffect(() => {
    const prev = valueRef.current;
    if (JSON.stringify(value) !== JSON.stringify(prev)) {
      valueRef.current = value;
      syncingRef.current = true;
      setEntries((prevEntries) => {
        if (!value || Object.keys(value).length === 0) {
          return [{ id: genId(), key: '', value: '' }];
        }
        const prevMap = new Map(prevEntries.map((e) => [e.key, e]));
        return Object.entries(value).map(([k, v]) => {
          const existing = k ? prevMap.get(k) : undefined;
          return existing ? { ...existing, value: v } : { id: genId(), key: k, value: v };
        });
      });
    }
  }, [value]);

  useEffect(() => {
    if (syncingRef.current) {
      syncingRef.current = false;
      return;
    }
    onChange?.(entriesToObj(entries));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entries]);

  const addRow = useCallback(() => {
    setEntries((prev) => [...prev, { id: genId(), key: '', value: '' }]);
  }, []);

  const removeRow = useCallback((id: number) => {
    setEntries((prev) => {
      const next = prev.filter((e) => e.id !== id);
      return next.length === 0 ? [{ id: genId(), key: '', value: '' }] : next;
    });
  }, []);

  const updateRow = useCallback((id: number, field: 'key' | 'value', val: string) => {
    setEntries((prev) => prev.map((e) => (e.id === id ? { ...e, [field]: val } : e)));
  }, []);

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 6, gap: 4 }}>
        <span style={{ fontSize: 11, color: '#9ca3af', textTransform: 'uppercase', letterSpacing: 0.5 }}>
          环境变量
        </span>
        <Tooltip
          title={
            <div style={{ fontSize: 12, lineHeight: 1.6 }}>
              <div style={{ marginBottom: 4 }}>支持以下变量引用语法：</div>
              <div><code>{'${credential.<name>}'}</code> — 引用凭证</div>
              <div><code>{'${env.<name>}'}</code> — 引用环境变量</div>
              <div><code>{'${task.<name>.output}'}</code> — 引用上游任务输出</div>
            </div>
          }
        >
          <QuestionCircleOutlined style={{ color: '#9ca3af', fontSize: 12, cursor: 'help' }} />
        </Tooltip>
      </div>
      {entries.map((entry) => {
        const isOnlyEmpty = entries.length === 1 && !entry.key && !entry.value;
        return (
          <Row key={entry.id} gutter={8} style={{ marginBottom: 6 }}>
            <Col flex="1">
              <Input
                size="small"
                placeholder="KEY"
                value={entry.key}
                onChange={(e) => updateRow(entry.id, 'key', e.target.value)}
                style={{ fontFamily: 'monospace' }}
              />
            </Col>
            <Col flex="1">
              <Input
                size="small"
                placeholder="VALUE"
                value={entry.value}
                onChange={(e) => updateRow(entry.id, 'value', e.target.value)}
                style={{ fontFamily: 'monospace' }}
              />
            </Col>
            <Col>
              <Button
                type="text"
                size="small"
                danger
                icon={<DeleteOutlined />}
                onClick={() => removeRow(entry.id)}
                disabled={isOnlyEmpty}
              />
            </Col>
          </Row>
        );
      })}
      <Button
        type="dashed"
        size="small"
        icon={<PlusOutlined />}
        onClick={addRow}
        block
        style={{ marginTop: 2 }}
      >
        添加
      </Button>
    </div>
  );
}

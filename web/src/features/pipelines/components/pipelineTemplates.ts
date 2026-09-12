/**
 * v3 (2026-09): 新建流水线的初始模板。
 * 设计决策：模板由前端生成而非后端 —— 它只是编辑器初始内容的选择，
 * 后端只负责写入文件并校验，保持 API 简洁。
 */
export type PipelineTemplateId = 'blank' | 'example';

/** 从文件名生成合法的流水线 name（去掉 .yaml/.yml 后缀） */
export function pipelineNameFromFile(fileName: string): string {
  return fileName.replace(/\.ya?ml$/i, '');
}

/** 根据模板生成初始 YAML 内容 */
export function buildPipelineContent(template: PipelineTemplateId, name: string): string {
  if (template === 'example') {
    return [
      `name: ${name}`,
      '',
      'tasks:',
      '  - name: hello',
      '    command: echo "Hello from taskpps"',
      '',
    ].join('\n');
  }
  return [`name: ${name}`, '', 'tasks: []', ''].join('\n');
}

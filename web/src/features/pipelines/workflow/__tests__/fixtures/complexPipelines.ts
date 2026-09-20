import type { PipelineDetail, TaskYAML, SubPipeline } from '@/types';

/**
 * 复杂 pipeline 场景库（压力测试/回归用）
 *
 * 目的：最大限度暴露渲染（布局越界/重叠/崩坏）与 UI/UX 问题。
 * 每个场景都是"结构合法但不平凡"的真实数据形态，覆盖：
 *   依赖形态（链/菱形/并行/环/孤儿）、容器（空/多/跨容器链）、
 *   when 条件、post 密集、超长文本、特殊字符、顶层 tasks、大图规模。
 *
 * 注意：fixtures 只描述输入数据，不对预期结果做断言假设（断言在各测试文件中）。
 */

/** 构造任务，默认 env/retry/depends_on 完备，避免字段缺失干扰场景本身 */
function task(name: string, overrides: Partial<TaskYAML> = {}): TaskYAML {
  return { name, env: {}, retry: 0, depends_on: [], ...overrides };
}

/** 构造子流水线 */
function sub(name: string, tasks: TaskYAML[], overrides: Partial<SubPipeline> = {}): SubPipeline {
  return { name, depends_on: [], tasks, ...overrides };
}

export interface ComplexScenario {
  id: string;
  title: string;
  /** 该场景主要想暴露的风险点 */
  risk: string;
  pipeline: PipelineDetail;
}

// ─────────────────────────────────────────────────────────────
// 1. 菱形依赖：a → b, a → c, b → d, c → d
// ─────────────────────────────────────────────────────────────
const diamond: PipelineDetail = {
  name: 'scenario-diamond',
  pipelines: [
    sub('build', [
      task('a'),
      task('b', { depends_on: ['a'] }),
      task('c', { depends_on: ['a'] }),
      task('d', { depends_on: ['b', 'c'] }),
    ]),
  ],
};

// ─────────────────────────────────────────────────────────────
// 2. 并行扇出：8 个互不依赖任务（parallel 策略）
// ─────────────────────────────────────────────────────────────
const parallelFanout: PipelineDetail = {
  name: 'scenario-parallel-fanout',
  options: { env: {}, retry: 0, on_failure: 'stop', execution_strategy: 'parallel', max_concurrent_tasks: 4 },
  pipelines: [
    sub('fanout', Array.from({ length: 8 }, (_, i) => task(`worker-${i + 1}`)), {
      config: { env: {}, retry: 0, on_failure: 'stop', execution_strategy: 'parallel', max_concurrent_tasks: 4 },
    }),
  ],
};

// ─────────────────────────────────────────────────────────────
// 3. 跨容器链：prepare → build → deploy，各自带 post
// ─────────────────────────────────────────────────────────────
const crossChainWithPost: PipelineDetail = {
  name: 'scenario-cross-chain',
  pipelines: [
    sub(
      'prepare',
      [task('checkout'), task('deps', { depends_on: ['checkout'] })],
      { post: { always: [task('cleanup-tmp')] } },
    ),
    sub(
      'build',
      [task('compile'), task('package', { depends_on: ['compile'] })],
      { depends_on: ['prepare'], post: { on_fail: [task('notify-fail')], on_success: [task('notify-ok')] } },
    ),
    sub(
      'deploy',
      [task('push'), task('verify', { depends_on: ['push'] })],
      { depends_on: ['build'] },
    ),
  ],
};

// ─────────────────────────────────────────────────────────────
// 4. 条件密集：多个 when 任务（含长表达式与相互依赖）
// ─────────────────────────────────────────────────────────────
const conditionHeavy: PipelineDetail = {
  name: 'scenario-conditions',
  pipelines: [
    sub('main', [
      task('setup'),
      task('smoke', { depends_on: ['setup'], when: '${params.RUN_SMOKE} == "true"' }),
      task('perf', { depends_on: ['setup'], when: '${params.RUN_PERF} == "true" && ${env.NIGHTLY} != "0"' }),
      task('publish', {
        depends_on: ['smoke'],
        when: '${params.DEPLOY_ENV} == "production" || ${params.DEPLOY_ENV} == "canary"',
      }),
      task('notify', { depends_on: ['perf'] }),
    ]),
  ],
};

// ─────────────────────────────────────────────────────────────
// 5. post 密集：单个 sub 带 6 个 post 任务（三种 hook）
// ─────────────────────────────────────────────────────────────
const postHeavy: PipelineDetail = {
  name: 'scenario-post-heavy',
  pipelines: [
    sub('deploy', [task('apply')], {
      post: {
        on_fail: [task('rollback'), task('alert-pager'), task('snapshot-logs')],
        on_success: [task('tag-release'), task('update-changelog')],
        always: [task('cleanup-workspace')],
      },
    }),
  ],
};

// ─────────────────────────────────────────────────────────────
// 6. 深链：20 个任务依次依赖
// ─────────────────────────────────────────────────────────────
const deepChain: PipelineDetail = {
  name: 'scenario-deep-chain',
  pipelines: [
    sub(
      'pipeline',
      Array.from({ length: 20 }, (_, i) =>
        task(`step-${String(i + 1).padStart(2, '0')}`, i > 0 ? { depends_on: [`step-${String(i).padStart(2, '0')}`] } : {}),
      ),
    ),
  ],
};

// ─────────────────────────────────────────────────────────────
// 7. 大图：3 个 sub、60 个任务（性能与滚动/缩放压力）
// ─────────────────────────────────────────────────────────────
const manyTasks: PipelineDetail = {
  name: 'scenario-many-tasks',
  pipelines: [
    sub('stage-a', Array.from({ length: 20 }, (_, i) => task(`a-${i + 1}`, i > 0 ? { depends_on: [`a-${i}`] } : {}))),
    sub(
      'stage-b',
      Array.from({ length: 20 }, (_, i) => task(`b-${i + 1}`, i > 0 ? { depends_on: [`b-${i}`] } : {})),
      { depends_on: ['stage-a'] },
    ),
    sub(
      'stage-c',
      Array.from({ length: 20 }, (_, i) => task(`c-${i + 1}`, i > 0 ? { depends_on: [`c-${i}`] } : {})),
      { depends_on: ['stage-b'], post: { always: [task('cleanup')] } },
    ),
  ],
};

// ─────────────────────────────────────────────────────────────
// 8. 完全空：无 pipelines 无 tasks
// ─────────────────────────────────────────────────────────────
const emptyPipeline: PipelineDetail = {
  name: 'scenario-empty',
  pipelines: [],
  tasks: [],
};

// ─────────────────────────────────────────────────────────────
// 9. 空子流水线：一个空 sub + 一个正常 sub
// ─────────────────────────────────────────────────────────────
const emptySubpipeline: PipelineDetail = {
  name: 'scenario-empty-sub',
  pipelines: [sub('empty-one', []), sub('normal', [task('run')], { depends_on: ['empty-one'] })],
};

// ─────────────────────────────────────────────────────────────
// 10. 超长文本：任务名 120 字符 + 长 when + 中文名
// ─────────────────────────────────────────────────────────────
const LONG_NAME = `very-long-task-name-${'x'.repeat(90)}-end`;
const longNames: PipelineDetail = {
  name: 'scenario-long-names-流水线名称也非常长用于测试标题截断行为',
  pipelines: [
    sub('超长的子流水线名称用于测试容器标题截断与布局稳定性', [
      task(LONG_NAME),
      task('中文任务名称用于验证等宽字体下的渲染宽度是否稳定', { depends_on: [LONG_NAME] }),
      task('long-when', {
        depends_on: ['中文任务名称用于验证等宽字体下的渲染宽度是否稳定'],
        when: `\${params.FEATURE_A} == "enabled" && \${params.FEATURE_B} == "enabled" && \${env.REGION} == "cn-north-1"`,
      }),
    ]),
  ],
};

// ─────────────────────────────────────────────────────────────
// 11. 特殊字符：引号/反斜杠/模板符号/HTML 尖括号
// ─────────────────────────────────────────────────────────────
const specialChars: PipelineDetail = {
  name: 'scenario-special-chars',
  pipelines: [
    sub('special', [
      task('quote-"double"'),
      task("single-'quote'", { depends_on: ['quote-"double"'] }),
      task('back\\slash', { depends_on: ["single-'quote'"] }),
      task('<tag> & "amp"', { depends_on: ['back\\slash'] }),
      task('${template}-var', { depends_on: ['<tag> & "amp"'], when: '${env.X} == "a\\"b"' }),
    ]),
  ],
};

// ─────────────────────────────────────────────────────────────
// 12. 孤儿依赖：depends_on 引用不存在的任务
// ─────────────────────────────────────────────────────────────
const orphanDeps: PipelineDetail = {
  name: 'scenario-orphan-deps',
  pipelines: [
    sub('main', [
      task('first'),
      task('second', { depends_on: ['does-not-exist'] }),
      task('third', { depends_on: ['first', 'also-missing'] }),
    ]),
  ],
};

// ─────────────────────────────────────────────────────────────
// 13. 环形依赖：a → b → c → a（无效数据，验证不崩溃/不死循环）
// ─────────────────────────────────────────────────────────────
const cyclicDeps: PipelineDetail = {
  name: 'scenario-cyclic',
  pipelines: [
    sub('loop', [task('a', { depends_on: ['c'] }), task('b', { depends_on: ['a'] }), task('c', { depends_on: ['b'] })]),
  ],
};

// ─────────────────────────────────────────────────────────────
// 14. 顶层 tasks：编辑器不支持（nodesToYaml 会报错），验证渲染降级行为
// ─────────────────────────────────────────────────────────────
const topLevelTasks: PipelineDetail = {
  name: 'scenario-top-level-tasks',
  tasks: [task('init'), task('cleanup', { depends_on: ['init'] })],
  pipelines: [],
};

// ─────────────────────────────────────────────────────────────
// 15. 跨 sub 同名任务：不同容器中的同名任务（合法，验证 ID 不冲突）
// ─────────────────────────────────────────────────────────────
const sameNameAcrossSubs: PipelineDetail = {
  name: 'scenario-same-names',
  pipelines: [
    sub('alpha', [task('build'), task('test', { depends_on: ['build'] })]),
    sub('beta', [task('build'), task('test', { depends_on: ['build'] })], { depends_on: ['alpha'] }),
  ],
};

// ─────────────────────────────────────────────────────────────
// 16. 同容器重名任务：无效数据（节点 ID 冲突），验证容错
// ─────────────────────────────────────────────────────────────
const duplicateTaskNames: PipelineDetail = {
  name: 'scenario-duplicate-names',
  pipelines: [sub('main', [task('same'), task('same'), task('same')])],
};

// ─────────────────────────────────────────────────────────────
// 17. 边边界：重复依赖 / 自依赖 / 重复跨容器依赖 / 容器自依赖
// ─────────────────────────────────────────────────────────────
const edgeEdgeCases: PipelineDetail = {
  name: 'scenario-edge-cases',
  pipelines: [
    sub('s1', [
      task('a'),
      task('b', { depends_on: ['a', 'a'] }), // 重复同容器依赖
      task('c', { depends_on: ['c'] }), // 自依赖（非法，应跳过自环边）
    ]),
    sub('s2', [task('d')], { depends_on: ['s1', 's1'] }), // 重复跨容器依赖
    sub('s3', [task('e')], { depends_on: ['s3'] }), // 容器自依赖（非法）
  ],
};

export const COMPLEX_SCENARIOS: ComplexScenario[] = [
  { id: 'diamond', title: '菱形依赖', risk: '同层多父依赖导致的交叉/重叠', pipeline: diamond },
  { id: 'parallel-fanout', title: '并行扇出 8 任务', risk: '同 rank 大量节点水平溢出', pipeline: parallelFanout },
  { id: 'cross-chain', title: '跨容器链 + post', risk: '容器层顺序与 post 容器位置', pipeline: crossChainWithPost },
  { id: 'conditions', title: '条件密集', risk: 'when 标签溢出与依赖方向', pipeline: conditionHeavy },
  { id: 'post-heavy', title: 'post 密集 6 子任务', risk: 'post 容器包裹与纵向堆叠', pipeline: postHeavy },
  { id: 'deep-chain', title: '20 级任务深链', risk: '长链高度与容器撑开', pipeline: deepChain },
  { id: 'many-tasks', title: '60 任务大图', risk: '渲染性能与整体尺寸', pipeline: manyTasks },
  { id: 'empty', title: '完全空 pipeline', risk: '空数据不崩、尺寸退化', pipeline: emptyPipeline },
  { id: 'empty-sub', title: '空子流水线', risk: '空容器尺寸与后续容器衔接', pipeline: emptySubpipeline },
  { id: 'long-names', title: '超长中英文名称', risk: '文本截断/节点撑宽/越界', pipeline: longNames },
  { id: 'special-chars', title: '特殊字符名称', risk: '渲染转义与文本测量', pipeline: specialChars },
  { id: 'orphan-deps', title: '孤儿依赖', risk: '悬空边与布局鲁棒性', pipeline: orphanDeps },
  { id: 'cyclic', title: '环形依赖', risk: 'dagre 死循环/崩溃', pipeline: cyclicDeps },
  { id: 'top-level-tasks', title: '顶层 tasks', risk: '编辑器不支持时的降级展示', pipeline: topLevelTasks },
  { id: 'same-names', title: '跨容器同名任务', risk: '节点 ID 冲突', pipeline: sameNameAcrossSubs },
  { id: 'duplicate-names', title: '同容器重名任务', risk: '重复 ID 导致 React/图渲染异常', pipeline: duplicateTaskNames },
  { id: 'edge-cases', title: '重复/自依赖边界', risk: '重复边 ID、自环边', pipeline: edgeEdgeCases },
];

package cmd

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/spf13/cobra"
)

var initCmd = &cobra.Command{
	Use:   "init",
	Short: "初始化项目目录结构",
	Long: `在当前目录创建 taskpps 项目的默认目录结构和示例配置文件。

创建的目录:
  pipelines/    流水线定义文件
  tasks/        Invoke 任务定义文件  
  agents/       Agent 主机配置文件
  credentials/  凭据配置文件
  plugins/      插件目录
  .taskpps/     项目配置文件`,
	RunE: func(cmd *cobra.Command, args []string) error {
		cwd, err := os.Getwd()
		if err != nil {
			return fmt.Errorf("获取当前目录失败: %w", err)
		}
		absCwd, err := filepath.Abs(cwd)
		if err != nil {
			return fmt.Errorf("获取绝对路径失败: %w", err)
		}

		dirs := []string{
			"pipelines",
			"tasks",
			"agents",
			"credentials",
			"plugins",
			".taskpps",
		}
		for _, d := range dirs {
			path := filepath.Join(".", d)
			if info, err := os.Stat(path); err == nil && info.IsDir() {
				fmt.Printf("  skip    %s/ (已存在, 不覆盖)\n", d)
				continue
			}
			if err := os.MkdirAll(path, 0755); err != nil {
				return fmt.Errorf("创建 %s 失败: %w", d, err)
			}
			fmt.Printf("  created %s/\n", d)
		}

		taskppsYAML := fmt.Sprintf(`# taskpps 项目配置文件
locale: zh
workdir: %s

server:
  host: 127.0.0.1
  port: 26521

executor:
  default_timeout: 3600
  max_workers: 10
  shell: /bin/bash
  tasks_dir: tasks

env:
  GLOBAL_VAR: value

plugins:
  paths: ["plugins"]

triggers: []
`, absCwd)
		if err := writeFileIfNotExists(".taskpps/taskpps.yaml", taskppsYAML, "  "); err != nil {
			return err
		}

		pipelineYAML := `# 示例流水线 — 使用子流水线格式 (config + pipelines)
# 旧格式 (options + tasks) 仍然兼容, 会自动包装为单子流水线
name: example

config:
  env:
    APP_ENV: development
  timeout: 600
  retry: 1
  on_failure: fail
  execution_strategy: sequential

pipelines:
  - name: build
    tasks:
      - name: compile
        command: echo "编译中..."
        timeout: 120

      - name: test
        command: echo "运行测试中..."
        depends_on: [compile]
        when: ${env.APP_ENV} != "production"

  - name: deploy
    depends_on: [build]
    config:
      host: local-agent
      credential: default-cred
    tasks:
      - name: restart
        commands:
          - echo "停止服务..."
          - sleep 2
          - echo "启动服务..."
        timeout: 60

      - name: health-check
        command: echo "健康检查通过"
        depends_on: [restart]
        when: ${env.APP_ENV} == "staging"
`
		if err := writeFileIfNotExists("pipelines/example.yaml", pipelineYAML, "  "); err != nil {
			return err
		}

		agentYAML := `# Agent 配置文件 — 通过 id 字段引用
# 引用语法: ${agent:<id>.<field>}
# 流水线中通过 host: <agent-id> 指定目标主机

agents:
  - id: local-agent
    name: "本地开发环境"
    description: "本地测试用 Agent"
    type: ssh-username-password
    host: 127.0.0.1
    port: 22
    username: admin
    credential_id: default-cred
    max_parallel: 3

  - id: staging-server
    name: "预发环境服务器"
    description: "预发环境测试服务器"
    type: ssh-key
    host: 192.168.1.100
    port: 22
    username: deploy
    credential_id: staging-cred
    max_parallel: 5
`
		if err := writeFileIfNotExists("agents/local.yaml", agentYAML, "  "); err != nil {
			return err
		}

		credYAML := `# 凭据配置文件 — 通过 id 字段引用
# 引用语法: ${credential:<id>.<field>}
# 支持类型: ssh-username-password, ssh-key, token, git-token, git-ssh-key,
#          git-username-password, nexus-username-password, nexus-token

credentials:
  - id: default-cred
    name: "默认 SSH 凭据 (密码认证)"
    description: "测试/开发环境 SSH 凭据"
    type: ssh-username-password
    username: admin
    password: changeme

  - id: staging-cred
    name: "预发环境 SSH 凭据"
    description: "预发环境 SSH 密钥认证"
    type: ssh-key
    username: deploy
    key_path: ~/.ssh/staging_deploy_key
`
		if err := writeFileIfNotExists("credentials/default.yaml", credYAML, "  "); err != nil {
			return err
		}

		initPyContent := `# Invoke 任务模块
# 在此目录下创建 .py 文件定义 invoke 任务
`
		if err := writeFileIfNotExists("tasks/__init__.py", initPyContent, "  "); err != nil {
			return err
		}

		exampleTasksContent := `"""Invoke 任务定义示例

这些函数可以在流水线的 invoke 任务中引用, 例如:
  - name: migrate
    invoke:
      task: example_tasks.migrate_db
      kwargs:
        target_version: latest
"""

from invoke import task


@task
def migrate_db(c, target_version="latest"):
    """执行数据库迁移"""
    print(f"正在迁移数据库到版本: {target_version}")
    c.run(f"python manage.py migrate --version {target_version}")


@task
def health_check(c, url="http://localhost:8000"):
    """健康检查"""
    print(f"正在检查服务健康状态: {url}")
    result = c.run(f"curl -sf {url}/health", warn=True)
    if result.ok:
        print("健康检查通过")
    else:
        print("健康检查失败")
        raise SystemExit(1)
`
		if err := writeFileIfNotExists("tasks/example_tasks.py", exampleTasksContent, "  "); err != nil {
			return err
		}

		fmt.Println("\n项目初始化完成!")
		fmt.Println("\n下一步:")
		fmt.Println("  1. 编辑 credentials/default.yaml 填入实际凭据")
		fmt.Println("  2. 编辑 agents/local.yaml 配置目标主机")
		fmt.Println("  3. 编辑 pipelines/example.yaml 或创建新流水线")
		fmt.Println("  4. 运行: taskpps start-server 启动服务端")
		fmt.Println("  5. 运行: taskpps run example 执行流水线")
		return nil
	},
}

func writeFileIfNotExists(relPath, content, indent string) error {
	path := filepath.Join(".", relPath)
	if _, err := os.Stat(path); err == nil {
		fmt.Printf("%sskip    %s (已存在, 不覆盖)\n", indent, relPath)
		return nil
	}
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		return fmt.Errorf("写入 %s 失败: %w", relPath, err)
	}
	fmt.Printf("%screated %s\n", indent, relPath)
	return nil
}

func init() {
	RootCmd.AddCommand(initCmd)
}

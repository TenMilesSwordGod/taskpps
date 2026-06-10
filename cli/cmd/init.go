package cmd

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"
	"github.com/taskpps/ppsctl/client"
	"github.com/taskpps/ppsctl/config"
)

var registerCurrentFolder bool

var initCmd = &cobra.Command{
	Use:   "init",
	Short: "初始化项目目录结构",
	Long: `在当前目录创建 taskpps 项目的默认目录结构和配置文件。

创建的目录:
  pipelines/    流水线定义文件
  tasks/        Invoke 任务定义文件
  agents/       Agent 主机配置文件
  credentials/  凭据配置文件
  plugins/      插件目录
  .taskpps/     项目配置文件

使用 --register-current-folder 可在初始化后通过 API 将项目注册到 server。`,
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

		// 不再写入 workdir: <abs_path>，项目路径由 DB 注册管理
		taskppsYAML := `# taskpps 项目配置文件
locale: zh

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
`
		if err := writeFileIfNotExists(".taskpps/taskpps.yaml", taskppsYAML, "  "); err != nil {
			return err
		}

		initPyContent := `# Invoke 任务模块
# 在此目录下创建 .py 文件定义 invoke 任务
`
		if err := writeFileIfNotExists("tasks/__init__.py", initPyContent, "  "); err != nil {
			return err
		}

		fmt.Println("\n项目初始化完成!")
		fmt.Println("\n下一步:")
		fmt.Println("  1. 在 agents/ 目录创建 agent 配置文件")
		fmt.Println("  2. 在 credentials/ 目录创建凭据配置文件")
		fmt.Println("  3. 在 pipelines/ 目录创建流水线定义文件")
		fmt.Println("  4. 运行: taskpps start-server 启动服务端")
		fmt.Println("  5. 运行: ppsctl run <pipeline> 执行流水线")

		if registerCurrentFolder {
			fmt.Println("\n正在注册项目到 server...")

			// 解析 api_key: flag --api-key > env PPSCTL_API_KEY
			if apiKeyFlag := cmd.Flag("api-key"); apiKeyFlag != nil && apiKeyFlag.Value.String() != "" {
				config.ApiKeyOverride = apiKeyFlag.Value.String()
			} else if envKey := os.Getenv("PPSCTL_API_KEY"); envKey != "" {
				config.ApiKeyOverride = envKey
			}

			cfg, err := config.Load(cfgFile, projectFlag)
			if err != nil {
				return fmt.Errorf("加载配置失败(无法连接 server): %w", err)
			}
			c := client.New(cfg)
			project, err := c.RegisterProject(absCwd, filepath.Base(absCwd))
			if err != nil {
				errMsg := err.Error()
				if strings.Contains(errMsg, "401") {
					return fmt.Errorf("注册项目失败: %w\n\n提示: 服务端要求 API Key 认证，请使用 -k 参数或设置 PPSCTL_API_KEY 环境变量\n  例如: ppsctl init --register-current-folder -k <your-api-key>", err)
				}
				if strings.Contains(errMsg, "500") {
					return fmt.Errorf("注册项目失败: %w\n\n提示: 服务端内部错误，请检查服务端日志（.taskpps/server.log 或 taskpps start-server 输出）", err)
				}
				return fmt.Errorf("注册项目失败: %w", err)
			}
			fmt.Printf("  项目已注册: id=%s workdir=%s\n", project.ID, project.Workdir)
		} else {
			fmt.Println("\n提示: 使用 --register-current-folder 可将项目注册到 server")
		}

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
	initCmd.Flags().BoolVar(&registerCurrentFolder, "register-current-folder", false, "初始化后将当前项目注册到 server")
	RootCmd.AddCommand(initCmd)
}

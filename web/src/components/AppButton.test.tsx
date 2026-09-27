import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { Play } from "lucide-react"
import AppButton from "./AppButton"

/** 取按钮根元素（AntD 渲染为原生 <button class="ant-btn ...">） */
function getBtn(container: HTMLElement): HTMLButtonElement {
  const btn = container.querySelector("button.ant-btn")
  if (!btn) throw new Error("未渲染出 antd 按钮")
  return btn as HTMLButtonElement
}

describe("<AppButton />", () => {
  it("默认渲染为 small 尺寸（项目统一控制件尺寸）", () => {
    const { container } = render(<AppButton>刷新数据</AppButton>)
    expect(getBtn(container)).toHaveClass("ant-btn-sm")
    expect(screen.getByText("刷新数据")).toBeInTheDocument()
  })

  it("默认是次级按钮（无 type，不上主色）", () => {
    const { container } = render(<AppButton>取消</AppButton>)
    const btn = getBtn(container)
    expect(btn).not.toHaveClass("ant-btn-primary")
    expect(btn).not.toHaveClass("ant-btn-dangerous")
  })

  it("variant=primary 映射为 AntD 主按钮", () => {
    const { container } = render(<AppButton variant="primary">触发运行</AppButton>)
    expect(getBtn(container)).toHaveClass("ant-btn-primary")
  })

  it("variant=danger 映射为红色描边的破坏性按钮", () => {
    const { container } = render(<AppButton variant="danger">删除历史</AppButton>)
    expect(getBtn(container)).toHaveClass("ant-btn-dangerous")
  })

  it.each([
    ["text", "ant-btn-text"],
    ["link", "ant-btn-link"],
    ["dashed", "ant-btn-dashed"],
  ] as const)("variant=%s 映射为 %s", (variant, cls) => {
    const { container } = render(<AppButton variant={variant}>x</AppButton>)
    expect(getBtn(container)).toHaveClass(cls)
  })

  it("未指定 variant 时仍透传 AntD 原生 type/danger（向后兼容）", () => {
    const { container } = render(
      <AppButton type="link" danger>
        x
      </AppButton>,
    )
    const btn = getBtn(container)
    expect(btn).toHaveClass("ant-btn-link")
    expect(btn).toHaveClass("ant-btn-dangerous")
  })

  it("显式 size 覆盖默认 small", () => {
    const { container } = render(<AppButton size="middle">x</AppButton>)
    expect(getBtn(container)).not.toHaveClass("ant-btn-sm")
  })

  it("已实例化的图标节点原样透传，不篡改其尺寸", () => {
    const { container } = render(
      <AppButton icon={<Play data-testid="ic" size={20} />}>x</AppButton>,
    )
    const svg = container.querySelector('svg[data-testid="ic"]')
    expect(svg).not.toBeNull()
    expect(svg).toHaveAttribute("width", "20")
  })

  it("传入 lucide 组件时按设计规范统一渲染 14px", () => {
    const { container } = render(<AppButton icon={Play}>x</AppButton>)
    const svg = container.querySelector("svg")
    expect(svg).toHaveAttribute("width", "14")
    expect(svg).toHaveAttribute("height", "14")
  })

  it("iconSize 可覆盖图标尺寸", () => {
    const { container } = render(
      <AppButton icon={Play} iconSize={18}>
        x
      </AppButton>,
    )
    expect(container.querySelector("svg")).toHaveAttribute("width", "18")
  })

  it("iconClassName 可给组件式图标加动画类（刷新转圈）", () => {
    const { container } = render(
      <AppButton icon={Play} iconClassName="animate-spin">
        x
      </AppButton>,
    )
    expect(container.querySelector("svg")).toHaveClass("animate-spin")
  })

  it("透传 onClick/disabled/htmlType 等原生能力", () => {
    const onClick = vi.fn()
    const { container } = render(
      <AppButton onClick={onClick} disabled htmlType="submit" data-testid="b">
        提交
      </AppButton>,
    )
    const btn = getBtn(container)
    expect(btn).toBeDisabled()
    expect(btn).toHaveAttribute("type", "submit")
    fireEvent.click(btn)
    expect(onClick).not.toHaveBeenCalled()
  })
})

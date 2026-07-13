import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import EnvEditor from '../EnvEditor'

function getKeyInputs() {
  return screen.getAllByPlaceholderText('KEY') as HTMLInputElement[]
}
function getValueInputs() {
  return screen.getAllByPlaceholderText('VALUE') as HTMLInputElement[]
}

describe('EnvEditor', () => {
  it('渲染初始空行', () => {
    render(<EnvEditor />)
    expect(getKeyInputs()).toHaveLength(1)
    expect(getValueInputs()).toHaveLength(1)
  })

  it('值连续输入不丢失', () => {
    const onChange = vi.fn()
    render(<EnvEditor onChange={onChange} />)

    const keyInput = getKeyInputs()[0]
    const valueInput = getValueInputs()[0]

    fireEvent.change(keyInput, { target: { value: 'M' } })
    fireEvent.change(keyInput, { target: { value: 'MY' } })
    fireEvent.change(keyInput, { target: { value: 'MY_KEY' } })

    expect(keyInput.value).toBe('MY_KEY')

    fireEvent.change(valueInput, { target: { value: 'v' } })
    fireEvent.change(valueInput, { target: { value: 'va' } })
    fireEvent.change(valueInput, { target: { value: 'val' } })
    fireEvent.change(valueInput, { target: { value: 'value' } })

    expect(valueInput.value).toBe('value')
  })

  it('受控模式连续输入不丢失', () => {
    const onChange = vi.fn()
    const { rerender } = render(<EnvEditor value={{}} onChange={onChange} />)

    const keyInput = getKeyInputs()[0]
    const valueInput = getValueInputs()[0]

    fireEvent.change(keyInput, { target: { value: 'K' } })
    fireEvent.change(keyInput, { target: { value: 'KE' } })
    fireEvent.change(keyInput, { target: { value: 'KEY' } })

    fireEvent.change(valueInput, { target: { value: '1' } })
    fireEvent.change(valueInput, { target: { value: '12' } })
    fireEvent.change(valueInput, { target: { value: '123' } })

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1]
    expect(lastCall[0]).toEqual({ KEY: '123' })
  })

  it('添加/删除行后输入正常', () => {
    const onChange = vi.fn()
    render(<EnvEditor onChange={onChange} />)

    fireEvent.change(getKeyInputs()[0], { target: { value: 'A' } })

    const addBtn = screen.getByText('添加')
    fireEvent.click(addBtn)
    expect(getKeyInputs()).toHaveLength(2)

    fireEvent.change(getKeyInputs()[1], { target: { value: 'B' } })
    expect(getKeyInputs()[1].value).toBe('B')

    const deleteBtns = screen.getAllByRole('button', { hidden: true })
    const deleteBtn = deleteBtns.find(
      (b) => b.querySelector('span.anticon-delete') !== null
    )!
    fireEvent.click(deleteBtn)
    expect(getKeyInputs()).toHaveLength(1)
  })
})

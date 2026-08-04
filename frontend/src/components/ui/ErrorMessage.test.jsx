import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ErrorMessage } from './ErrorMessage'

describe('ErrorMessage', () => {
  it('renders the message', () => {
    render(<ErrorMessage message="Access code is wrong" />)
    expect(screen.getByText('Access code is wrong')).toBeInTheDocument()
  })

  it('exposes the message to assistive tech as an alert', () => {
    render(<ErrorMessage message="Printer unreachable" />)
    expect(screen.getByRole('alert')).toHaveTextContent('Printer unreachable')
  })

  // The whole point of the null guard: callers pass error state straight in.
  it.each([
    ['undefined', undefined],
    ['null', null],
    ['empty string', ''],
  ])('renders nothing when the message is %s', (_label, value) => {
    const { container } = render(<ErrorMessage message={value} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('applies layout classes from className', () => {
    render(<ErrorMessage message="boom" className="mx-6 mt-4" />)
    const el = screen.getByRole('alert')
    expect(el).toHaveClass('mx-6', 'mt-4')
  })

  it('keeps its own colour classes when className is supplied', () => {
    render(<ErrorMessage message="boom" className="mx-6" />)
    expect(screen.getByRole('alert')).toHaveClass('text-red-700')
  })
})

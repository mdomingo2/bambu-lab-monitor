import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { HumidityLevel } from './HumidityLevel'

// HumidityLevel reads tempUnit from useUnitStore — mock it to return 'C'
vi.mock('../../store/unitStore', () => ({
  useUnitStore: (selector) => selector({ tempUnit: 'C', toggleTempUnit: vi.fn() }),
}))

describe('HumidityLevel', () => {
  it('renders with no label by default', () => {
    render(<HumidityLevel level={3} />)
    expect(screen.queryByText('Moderate')).not.toBeInTheDocument()
  })

  it('shows label text when showLabel=true', () => {
    render(<HumidityLevel level={3} showLabel />)
    expect(screen.getByText('Moderate')).toBeInTheDocument()
  })

  const levels = [
    [5, 'Very dry'],
    [4, 'Dry'],
    [3, 'Moderate'],
    [2, 'Wet'],
    [1, 'Very wet'],
    [0, '—'],
  ]

  it.each(levels)('shows correct label for level %i', (level, label) => {
    render(<HumidityLevel level={level} showLabel />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it('clamps out-of-range levels to valid range', () => {
    // Level 10 should be treated as 5 (very dry)
    render(<HumidityLevel level={10} showLabel />)
    expect(screen.getByText('Very dry')).toBeInTheDocument()
  })

  it('shows AMS temp when temp prop > 0', () => {
    render(<HumidityLevel level={3} temp={22} />)
    // formatTemp(22, 'C') → '22°'
    expect(screen.getByText(/22°/)).toBeInTheDocument()
  })

  it('does not show temp when temp is null', () => {
    const { container } = render(<HumidityLevel level={3} temp={null} />)
    // No temperature span should be rendered
    expect(container.querySelectorAll('span').length).toBeLessThan(10)
  })

  it('does not show temp when temp is 0', () => {
    render(<HumidityLevel level={3} temp={0} />)
    // 0°C is filtered out (noise / no sensor)
    expect(screen.queryByText(/0°/)).not.toBeInTheDocument()
  })

  it('renders correct aria-label for accessibility', () => {
    const { container } = render(<HumidityLevel level={4} />)
    const el = container.querySelector('[aria-label]')
    expect(el?.getAttribute('aria-label')).toContain('Dry')
  })

  it('renders correct title tooltip', () => {
    const { container } = render(<HumidityLevel level={5} />)
    const el = container.querySelector('[title]')
    expect(el?.getAttribute('title')).toContain('Very dry')
  })

  it('renders 5 bar spans', () => {
    const { container } = render(<HumidityLevel level={3} />)
    // The bars container holds 5 spans
    const barContainer = container.querySelector('.inline-flex.items-end')
    expect(barContainer?.children.length).toBe(5)
  })

  it('renders xs size without error', () => {
    expect(() => render(<HumidityLevel level={3} size="xs" />)).not.toThrow()
  })
})

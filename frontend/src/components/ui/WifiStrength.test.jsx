import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { WifiStrength } from './WifiStrength'

describe('WifiStrength', () => {
  const getLabel = (container) =>
    container.querySelector('[aria-label]').getAttribute('aria-label')

  it('shows 4 bars for excellent signal (-45 dBm)', () => {
    const { container } = render(<WifiStrength value="-45dBm" />)
    expect(getLabel(container)).toContain('4 of 4 bars')
  })

  it('shows 4 bars at the -50 boundary', () => {
    const { container } = render(<WifiStrength value="-50dBm" />)
    expect(getLabel(container)).toContain('4 of 4 bars')
  })

  it('shows 3 bars for good signal (-55 dBm)', () => {
    const { container } = render(<WifiStrength value="-55dBm" />)
    expect(getLabel(container)).toContain('3 of 4 bars')
  })

  it('shows 2 bars for fair signal (-65 dBm)', () => {
    const { container } = render(<WifiStrength value="-65dBm" />)
    expect(getLabel(container)).toContain('2 of 4 bars')
  })

  it('shows 1 bar for poor signal (-75 dBm)', () => {
    const { container } = render(<WifiStrength value="-75dBm" />)
    expect(getLabel(container)).toContain('1 of 4 bars')
  })

  it('shows 0 bars for very poor signal (-85 dBm)', () => {
    const { container } = render(<WifiStrength value="-85dBm" />)
    expect(getLabel(container)).toContain('0 of 4 bars')
  })

  it('handles string without dBm suffix', () => {
    const { container } = render(<WifiStrength value="-60" />)
    expect(getLabel(container)).toContain('3 of 4 bars')
  })

  it('shows no signal data title for null value', () => {
    const { container } = render(<WifiStrength value={null} />)
    expect(container.querySelector('[title]').getAttribute('title')).toBe('No signal data')
  })

  it('shows no signal data title for empty string', () => {
    const { container } = render(<WifiStrength value="" />)
    expect(container.querySelector('[title]').getAttribute('title')).toBe('No signal data')
  })

  it('shows actual dBm in title for valid signal', () => {
    const { container } = render(<WifiStrength value="-72dBm" />)
    expect(container.querySelector('[title]').getAttribute('title')).toBe('-72 dBm')
  })

  it('renders 4 bar spans', () => {
    const { container } = render(<WifiStrength value="-55dBm" />)
    // The outer span contains 4 bar spans
    const bars = container.querySelectorAll('span > span')
    expect(bars.length).toBe(4)
  })
})

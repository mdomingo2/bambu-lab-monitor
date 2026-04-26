import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusBadge } from './StatusBadge'

describe('StatusBadge', () => {
  const states = [
    ['RUNNING',  'Printing'],
    ['PAUSE',    'Paused'],
    ['FINISH',   'Finished'],
    ['FAILED',   'Failed'],
    ['IDLE',     'Idle'],
    ['OFFLINE',  'Offline'],
    ['PREPARE',  'Preparing'],
    ['SLICING',  'Slicing'],
  ]

  it.each(states)('renders correct label for %s state', (state, expectedLabel) => {
    render(<StatusBadge state={state} />)
    expect(screen.getByText(expectedLabel)).toBeInTheDocument()
  })

  it('renders unknown state as-is when no mapping exists', () => {
    render(<StatusBadge state="CUSTOM_STATE" />)
    expect(screen.getByText('CUSTOM_STATE')).toBeInTheDocument()
  })
})

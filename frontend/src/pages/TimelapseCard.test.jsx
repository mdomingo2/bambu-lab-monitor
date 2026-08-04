import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Thermometer } from 'lucide-react'
import { TimelapseCard, StatBlock } from './PrinterDetail'

/**
 * Behavioural cover for the two presentational pieces of PrinterDetail.jsx
 * ahead of extracting them. TimelapseCard is the one with real logic: URL
 * building, the Bambu filename prefix strip, and the poster fallback that
 * keeps the grid intact when ffmpeg could not produce a thumbnail.
 */

const PID = 'abc-123'

describe('TimelapseCard', () => {
  describe('links', () => {
    it('points the card at the download endpoint', () => {
      render(<TimelapseCard printerId={PID} filename="video_1.mp4" />)
      expect(screen.getByRole('link')).toHaveAttribute(
        'href', `/api/printers/${PID}/timelapses/video_1.mp4`
      )
    })

    it('requests the poster from the thumb endpoint', () => {
      render(<TimelapseCard printerId={PID} filename="video_1.mp4" />)
      expect(screen.getByRole('img')).toHaveAttribute(
        'src', `/api/printers/${PID}/timelapses/video_1.mp4/thumb`
      )
    })

    it('percent-encodes a filename with spaces or slashes', () => {
      render(<TimelapseCard printerId={PID} filename="my video 1.mp4" />)
      expect(screen.getByRole('link')).toHaveAttribute(
        'href', `/api/printers/${PID}/timelapses/my%20video%201.mp4`
      )
    })

    it('opens in a new tab without leaking the referrer', () => {
      render(<TimelapseCard printerId={PID} filename="video_1.mp4" />)
      const link = screen.getByRole('link')
      expect(link).toHaveAttribute('target', '_blank')
      expect(link).toHaveAttribute('rel', 'noreferrer')
    })
  })

  describe('label', () => {
    it('strips the Bambu timestamp prefix and the extension', () => {
      render(<TimelapseCard printerId={PID} filename="20240401_benchy.mp4" />)
      expect(screen.getByText('benchy')).toBeInTheDocument()
    })

    it('leaves a filename without a timestamp prefix alone', () => {
      render(<TimelapseCard printerId={PID} filename="benchy.mp4" />)
      expect(screen.getByText('benchy')).toBeInTheDocument()
    })

    it('only strips an 8-digit prefix, not any leading digits', () => {
      render(<TimelapseCard printerId={PID} filename="123_benchy.mp4" />)
      expect(screen.getByText('123_benchy')).toBeInTheDocument()
    })

    it('falls back to the raw filename when stripping leaves nothing', () => {
      render(<TimelapseCard printerId={PID} filename="20240401_.mp4" />)
      expect(screen.getByText('20240401_.mp4')).toBeInTheDocument()
    })
  })

  describe('poster fallback', () => {
    it('shows the poster image by default', () => {
      render(<TimelapseCard printerId={PID} filename="video_1.mp4" />)
      expect(screen.getByRole('img')).toBeInTheDocument()
    })

    it('drops the broken image when the thumbnail 404s', () => {
      render(<TimelapseCard printerId={PID} filename="video_1.mp4" />)
      fireEvent.error(screen.getByRole('img'))
      // Placeholder icon replaces it; no broken <img> is left behind.
      expect(screen.queryByRole('img')).not.toBeInTheDocument()
    })

    it('keeps the filename readable after the poster fails', () => {
      render(<TimelapseCard printerId={PID} filename="20240401_benchy.mp4" />)
      fireEvent.error(screen.getByRole('img'))
      expect(screen.getByText('benchy')).toBeInTheDocument()
    })
  })
})

describe('StatBlock', () => {
  it('renders its label and value', () => {
    render(<StatBlock icon={Thermometer} label="Nozzle" value="220°C" />)
    expect(screen.getByText('Nozzle')).toBeInTheDocument()
    expect(screen.getByText('220°C')).toBeInTheDocument()
  })

  it('renders the sub-label when given one', () => {
    render(<StatBlock icon={Thermometer} label="Nozzle" value="220°C" sub="target 220°C" />)
    expect(screen.getByText('target 220°C')).toBeInTheDocument()
  })

  it('omits the sub-label when there is none', () => {
    const { container } = render(<StatBlock icon={Thermometer} label="Nozzle" value="220°C" />)
    expect(container.querySelectorAll('span')).toHaveLength(1)
  })

  it('highlights the value when warning', () => {
    render(<StatBlock icon={Thermometer} label="Nozzle" value="300°C" warn />)
    expect(screen.getByText('300°C')).toHaveClass('text-red-500')
  })

  it('does not highlight the value normally', () => {
    render(<StatBlock icon={Thermometer} label="Nozzle" value="220°C" />)
    expect(screen.getByText('220°C')).not.toHaveClass('text-red-500')
  })
})

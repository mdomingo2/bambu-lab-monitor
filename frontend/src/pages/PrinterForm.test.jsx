import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PrinterForm } from './Setup'

/**
 * Behavioural cover for PrinterForm ahead of pulling it out of Setup.jsx.
 * These assert what the form *does* — validation, the model→LAN-Mode link,
 * serial normalisation — so the extraction has something to fail against.
 */

const TYPES = [
  { name: 'A1',  lan_mode_default: false, timelapse_support: false, camera_capable: false },
  { name: 'P1S', lan_mode_default: false, timelapse_support: false, camera_capable: true },
  { name: 'H2D', lan_mode_default: true,  timelapse_support: true,  camera_capable: true },
]

function setup(props = {}) {
  const onSave = vi.fn()
  const onCancel = vi.fn()
  render(
    <PrinterForm printerTypes={TYPES} onSave={onSave} onCancel={onCancel} {...props} />
  )
  return { onSave, onCancel, user: userEvent.setup() }
}

const field = (placeholder) => screen.getByPlaceholderText(placeholder)
const saveBtn = () => screen.getByRole('button', { name: /save printer/i })

async function fillRequired(user) {
  await user.type(field('e.g. P1S Left'), 'Left P1S')
  await user.type(field('192.168.1.100'), '192.168.1.50')
  await user.type(field('01S00C123456789'), 'abc123')
  await user.type(field('8-digit code from printer screen'), '12345678')
}

describe('PrinterForm', () => {
  describe('model options', () => {
    it('offers every printer type it is given', () => {
      setup()
      const options = screen.getAllByRole('option').map((o) => o.textContent)
      expect(options).toEqual(['A1', 'P1S', 'H2D'])
    })

    it('defaults to the first type when adding a new printer', () => {
      setup()
      expect(screen.getByRole('combobox')).toHaveValue('A1')
    })

    it('keeps the existing model when editing', () => {
      setup({ initial: { name: 'X', model: 'H2D', ip: '1.1.1.1', serial: 'S', access_code: 'C', lan_mode: true } })
      expect(screen.getByRole('combobox')).toHaveValue('H2D')
    })
  })

  describe('validation', () => {
    it('disables save until every required field is filled', async () => {
      const { user } = setup()
      expect(saveBtn()).toBeDisabled()
      await fillRequired(user)
      expect(saveBtn()).toBeEnabled()
    })

    it.each([
      ['e.g. P1S Left'],
      ['192.168.1.100'],
      ['01S00C123456789'],
      ['8-digit code from printer screen'],
    ])('stays disabled while %s is blank', async (placeholder) => {
      const { user } = setup()
      await fillRequired(user)
      await user.clear(field(placeholder))
      expect(saveBtn()).toBeDisabled()
    })

    it('treats whitespace-only input as blank', async () => {
      const { user } = setup()
      await fillRequired(user)
      await user.clear(field('e.g. P1S Left'))
      await user.type(field('e.g. P1S Left'), '   ')
      expect(saveBtn()).toBeDisabled()
    })
  })

  describe('serial number', () => {
    it('upper-cases as you type', async () => {
      const { user } = setup()
      await user.type(field('01S00C123456789'), 'ab12cd')
      expect(field('01S00C123456789')).toHaveValue('AB12CD')
    })
  })

  describe('LAN Mode follows the selected model', () => {
    it('turns on for a type that defaults it on', async () => {
      const { user } = setup()
      await user.selectOptions(screen.getByRole('combobox'), 'H2D')
      expect(screen.getByRole('checkbox')).toBeChecked()
    })

    it('turns off for a type that defaults it off', async () => {
      const { user } = setup()
      await user.selectOptions(screen.getByRole('combobox'), 'H2D')
      await user.selectOptions(screen.getByRole('combobox'), 'P1S')
      expect(screen.getByRole('checkbox')).not.toBeChecked()
    })

    it('disables the toggle for a model with no camera', async () => {
      const { user } = setup()
      await user.selectOptions(screen.getByRole('combobox'), 'A1')
      expect(screen.getByRole('checkbox')).toBeDisabled()
    })

    it('explains why the camera is unavailable on such a model', async () => {
      const { user } = setup()
      await user.selectOptions(screen.getByRole('combobox'), 'A1')
      expect(screen.getByText(/cameras are cloud-only/i)).toBeInTheDocument()
    })

    it('is user-toggleable on a camera-capable model', async () => {
      const { user } = setup()
      await user.selectOptions(screen.getByRole('combobox'), 'P1S')
      await user.click(screen.getByRole('checkbox'))
      expect(screen.getByRole('checkbox')).toBeChecked()
    })
  })

  describe('submitting', () => {
    it('hands the completed form to onSave', async () => {
      const { user, onSave } = setup()
      await fillRequired(user)
      await user.click(saveBtn())
      expect(onSave).toHaveBeenCalledTimes(1)
      expect(onSave.mock.calls[0][0]).toMatchObject({
        name: 'Left P1S',
        ip: '192.168.1.50',
        serial: 'ABC123',
        access_code: '12345678',
      })
    })

    it('calls onCancel when cancelled', async () => {
      const { user, onCancel } = setup()
      await user.click(screen.getByRole('button', { name: /cancel/i }))
      expect(onCancel).toHaveBeenCalledTimes(1)
    })
  })

  describe('saving state', () => {
    it('shows progress and blocks both buttons', () => {
      setup({
        initial: { name: 'X', model: 'P1S', ip: '1.1.1.1', serial: 'S', access_code: 'C', lan_mode: true },
        saving: true,
      })
      expect(screen.getByRole('button', { name: /saving/i })).toBeDisabled()
      expect(screen.getByRole('button', { name: /cancel/i })).toBeDisabled()
    })
  })

  describe('errors', () => {
    it('surfaces a save failure', () => {
      setup({ error: 'Serial already registered' })
      expect(screen.getByRole('alert')).toHaveTextContent('Serial already registered')
    })

    it('shows nothing when there is no error', () => {
      setup()
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    })
  })
})

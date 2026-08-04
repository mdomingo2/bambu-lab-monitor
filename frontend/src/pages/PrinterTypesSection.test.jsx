import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PrinterTypesSection } from './Setup'

/**
 * Behavioural cover for PrinterTypesSection ahead of pulling it out of
 * Setup.jsx. The component talks to /api/printer-types through the module's
 * local apiRequest helper, which is a thin wrapper over fetch — so stubbing
 * fetch exercises the real request-building and error-unwrapping code.
 */

const TYPES = [
  { name: 'A1',  lan_mode_default: false, timelapse_support: false, camera_capable: false },
  { name: 'H2D', lan_mode_default: true,  timelapse_support: true,  camera_capable: true },
]

function okResponse(body = {}, status = 200) {
  return {
    ok: true,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  }
}

function errorResponse(status, detail) {
  return {
    ok: false,
    status,
    statusText: 'Error',
    json: async () => ({ detail }),
    text: async () => detail,
  }
}

function setup(types = TYPES) {
  const onRefresh = vi.fn()
  render(<PrinterTypesSection types={types} onRefresh={onRefresh} />)
  return { onRefresh, user: userEvent.setup() }
}

const openAddDialog = async (user) =>
  user.click(screen.getByRole('button', { name: /add type/i }))

/** Buttons inside the modal, so the section header's button never collides. */
const inDialog = () => within(screen.getByRole('dialog'))

beforeEach(() => {
  global.fetch = vi.fn(() => Promise.resolve(okResponse()))
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('PrinterTypesSection', () => {
  describe('listing', () => {
    it('shows every configured type', () => {
      setup()
      expect(screen.getByText('A1')).toBeInTheDocument()
      expect(screen.getByText('H2D')).toBeInTheDocument()
    })

    it('badges only the capabilities a type actually has', () => {
      setup([TYPES[1]])   // H2D: all three
      expect(screen.getByText('Timelapse')).toBeInTheDocument()
      expect(screen.getByText('Camera')).toBeInTheDocument()
      expect(screen.getByText('LAN default')).toBeInTheDocument()
    })

    it('omits badges for capabilities a type lacks', () => {
      setup([TYPES[0]])   // A1: none
      expect(screen.queryByText('Timelapse')).not.toBeInTheDocument()
      expect(screen.queryByText('Camera')).not.toBeInTheDocument()
      expect(screen.queryByText('LAN default')).not.toBeInTheDocument()
    })

    it('renders nothing but the header when there are no types', () => {
      setup([])
      expect(screen.getByText(/printer types/i)).toBeInTheDocument()
      expect(screen.queryByTitle(/^Delete /)).not.toBeInTheDocument()
    })
  })

  describe('adding a type', () => {
    it('upper-cases the model name as you type', async () => {
      const { user } = setup()
      await openAddDialog(user)
      const input = screen.getByPlaceholderText('e.g. X1C')
      await user.type(input, 'x1c')
      expect(input).toHaveValue('X1C')
    })

    it('will not submit an empty name', async () => {
      const { user } = setup()
      await openAddDialog(user)
      expect(inDialog().getByRole('button', { name: /^add type$/i })).toBeDisabled()
    })

    it('caps the name at 20 characters', async () => {
      const { user } = setup()
      await openAddDialog(user)
      expect(screen.getByPlaceholderText('e.g. X1C')).toHaveAttribute('maxLength', '20')
    })

    it('POSTs the trimmed name and selected capabilities', async () => {
      const { user } = setup()
      await openAddDialog(user)
      await user.type(screen.getByPlaceholderText('e.g. X1C'), 'X1C')
      await user.click(inDialog().getByRole('button', { name: /^add type$/i }))

      await waitFor(() => expect(global.fetch).toHaveBeenCalled())
      const [url, opts] = global.fetch.mock.calls[0]
      expect(url).toBe('/api/printer-types')
      expect(opts.method).toBe('POST')
      expect(JSON.parse(opts.body)).toMatchObject({ name: 'X1C' })
    })

    it('refreshes the list after a successful add', async () => {
      const { user, onRefresh } = setup()
      await openAddDialog(user)
      await user.type(screen.getByPlaceholderText('e.g. X1C'), 'X1C')
      await user.click(inDialog().getByRole('button', { name: /^add type$/i }))
      await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1))
    })

    it('shows the server error and does not refresh when the name is taken', async () => {
      global.fetch = vi.fn(() =>
        Promise.resolve(errorResponse(400, 'Printer type already exists'))
      )
      const { user, onRefresh } = setup()
      await openAddDialog(user)
      await user.type(screen.getByPlaceholderText('e.g. X1C'), 'A1')
      await user.click(inDialog().getByRole('button', { name: /^add type$/i }))

      // The dialog stays open on failure and repeats the error next to the
      // form, so scope to it — the section behind also shows one.
      await waitFor(() =>
        expect(inDialog().getByRole('alert')).toHaveTextContent(/already exists/i)
      )
      expect(onRefresh).not.toHaveBeenCalled()
    })

    it('disables LAN-Mode-by-default when the type has no camera', async () => {
      const { user } = setup()
      await openAddDialog(user)
      const [cameraCapable, lanDefault] = screen.getAllByRole('checkbox')
      expect(lanDefault).toBeEnabled()
      await user.click(cameraCapable)          // turn camera off
      expect(lanDefault).toBeDisabled()
    })
  })

  describe('deleting a type', () => {
    it('asks for confirmation before deleting', async () => {
      const { user } = setup()
      await user.click(screen.getByTitle('Delete H2D'))
      expect(screen.getByText(/cannot be undone/i)).toBeInTheDocument()
      expect(global.fetch).not.toHaveBeenCalled()
    })

    it('DELETEs the type once confirmed, then refreshes', async () => {
      const { user, onRefresh } = setup()
      await user.click(screen.getByTitle('Delete H2D'))
      await user.click(inDialog().getByRole('button', { name: /delete type/i }))

      await waitFor(() => expect(global.fetch).toHaveBeenCalled())
      const [url, opts] = global.fetch.mock.calls[0]
      expect(url).toBe('/api/printer-types/H2D')
      expect(opts.method).toBe('DELETE')
      await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1))
    })

    it('reports the server refusing to delete a type still in use', async () => {
      global.fetch = vi.fn(() =>
        Promise.resolve(errorResponse(400, "Cannot delete 'H2D': it is used by one or more printers."))
      )
      const { user, onRefresh } = setup()
      await user.click(screen.getByTitle('Delete H2D'))
      await user.click(inDialog().getByRole('button', { name: /delete type/i }))

      await waitFor(() =>
        expect(screen.getByRole('alert')).toHaveTextContent(/used by one or more printers/i)
      )
      expect(onRefresh).not.toHaveBeenCalled()
    })

    it('does not delete when the confirmation is dismissed', async () => {
      const { user } = setup()
      await user.click(screen.getByTitle('Delete H2D'))
      await user.click(inDialog().getByRole('button', { name: /^cancel$/i }))
      expect(global.fetch).not.toHaveBeenCalled()
    })

    it('percent-encodes a name that needs it', async () => {
      const { user } = setup([{ name: 'X 1/C', lan_mode_default: true, timelapse_support: false, camera_capable: true }])
      await user.click(screen.getByTitle('Delete X 1/C'))
      await user.click(inDialog().getByRole('button', { name: /delete type/i }))
      await waitFor(() => expect(global.fetch).toHaveBeenCalled())
      expect(global.fetch.mock.calls[0][0]).toBe('/api/printer-types/X%201%2FC')
    })
  })
})

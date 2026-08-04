import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { UsersSection, RoleBadge } from './Setup'

/**
 * Behavioural cover for UsersSection ahead of pulling it out of Setup.jsx.
 *
 * The important behaviour here is the self-vs-others split: you change your
 * own password by proving the current one, and you can neither reset nor
 * delete yourself. Those rules are the reason this component is more than a
 * list, and they are what an extraction could quietly break.
 */

const USERS = [
  { username: 'justin', role: 'admin' },
  { username: 'mike',   role: 'viewer' },
]

const jsonResponse = (body) => ({
  ok: true,
  status: 200,
  json: async () => body,
  text: async () => JSON.stringify(body),
})

const errorResponse = (detail) => ({
  ok: false,
  status: 400,
  statusText: 'Error',
  json: async () => ({ detail }),
  text: async () => detail,
})

/** fetch stub: GET /api/users returns the list, everything else succeeds. */
function stubFetch({ users = USERS, failWith = null } = {}) {
  return vi.fn((url, opts) => {
    if (!opts || opts.method === undefined) return Promise.resolve(jsonResponse(users))
    if (failWith) return Promise.resolve(errorResponse(failWith))
    return Promise.resolve(jsonResponse({}))
  })
}

async function setup({ currentUsername = 'justin', ...opts } = {}) {
  global.fetch = stubFetch(opts)
  render(<UsersSection currentUsername={currentUsername} />)
  await waitFor(() => expect(screen.queryByText('Loading…')).not.toBeInTheDocument())
  return { user: userEvent.setup() }
}

const inDialog = () => within(screen.getByRole('dialog'))

beforeEach(() => { vi.useRealTimers() })
afterEach(() => { vi.restoreAllMocks() })

describe('UsersSection', () => {
  describe('loading', () => {
    it('shows a loading state until the users arrive', () => {
      global.fetch = vi.fn(() => new Promise(() => {}))   // never resolves
      render(<UsersSection currentUsername="justin" />)
      expect(screen.getByText('Loading…')).toBeInTheDocument()
    })

    it('lists every user once loaded', async () => {
      await setup()
      expect(screen.getByText('justin')).toBeInTheDocument()
      expect(screen.getByText('mike')).toBeInTheDocument()
    })

    it('survives the list failing to load', async () => {
      global.fetch = vi.fn(() => Promise.resolve(errorResponse('boom')))
      render(<UsersSection currentUsername="justin" />)
      await waitFor(() => expect(screen.queryByText('Loading…')).not.toBeInTheDocument())
      expect(screen.getByText(/users/i)).toBeInTheDocument()
    })
  })

  describe('your own account', () => {
    it('is marked as you', async () => {
      await setup({ currentUsername: 'justin' })
      expect(screen.getByText('(you)')).toBeInTheDocument()
    })

    it('cannot be deleted', async () => {
      await setup({ currentUsername: 'justin' })
      expect(screen.queryByTitle('Delete justin')).not.toBeInTheDocument()
      expect(screen.getByTitle('Delete mike')).toBeInTheDocument()
    })

    it('offers a change-my-password action rather than an admin reset', async () => {
      await setup({ currentUsername: 'justin' })
      expect(screen.getByTitle('Change my password')).toBeInTheDocument()
      expect(screen.queryByTitle("Reset justin's password")).not.toBeInTheDocument()
    })
  })

  describe('other accounts', () => {
    it('can be password-reset and deleted', async () => {
      await setup({ currentUsername: 'justin' })
      expect(screen.getByTitle("Reset mike's password")).toBeInTheDocument()
      expect(screen.getByTitle('Delete mike')).toBeInTheDocument()
    })
  })

  describe('adding a user', () => {
    const open = async (user) => user.click(screen.getByRole('button', { name: /add user/i }))

    it('requires a password of at least 8 characters', async () => {
      const { user } = await setup()
      await open(user)
      await user.type(screen.getByPlaceholderText('e.g. justin'), 'newbie')
      await user.type(screen.getByPlaceholderText('8+ characters'), 'short')
      expect(inDialog().getByRole('button', { name: /create user/i })).toBeDisabled()

      await user.type(screen.getByPlaceholderText('8+ characters'), 'enough')
      expect(inDialog().getByRole('button', { name: /create user/i })).toBeEnabled()
    })

    it('requires a username', async () => {
      const { user } = await setup()
      await open(user)
      await user.type(screen.getByPlaceholderText('8+ characters'), 'longenoughpw')
      expect(inDialog().getByRole('button', { name: /create user/i })).toBeDisabled()
    })

    it('POSTs the new user and reloads the list', async () => {
      const { user } = await setup()
      await open(user)
      await user.type(screen.getByPlaceholderText('e.g. justin'), 'newbie')
      await user.type(screen.getByPlaceholderText('8+ characters'), 'longenoughpw')
      await user.click(inDialog().getByRole('button', { name: /create user/i }))

      await waitFor(() => {
        const post = global.fetch.mock.calls.find(([, o]) => o?.method === 'POST')
        expect(post).toBeTruthy()
        expect(post[0]).toBe('/api/users')
        expect(JSON.parse(post[1].body)).toMatchObject({ username: 'newbie', role: 'admin' })
      })
    })

    it('reports a duplicate username', async () => {
      const { user } = await setup({ failWith: 'Username already exists' })
      await open(user)
      await user.type(screen.getByPlaceholderText('e.g. justin'), 'mike')
      await user.type(screen.getByPlaceholderText('8+ characters'), 'longenoughpw')
      await user.click(inDialog().getByRole('button', { name: /create user/i }))
      await waitFor(() =>
        expect(inDialog().getByRole('alert')).toHaveTextContent(/already exists/i)
      )
    })
  })

  describe('deleting a user', () => {
    it('confirms first, then DELETEs and reloads', async () => {
      const { user } = await setup()
      await user.click(screen.getByTitle('Delete mike'))
      await user.click(inDialog().getByRole('button', { name: /delete user/i }))

      await waitFor(() => {
        const del = global.fetch.mock.calls.find(([, o]) => o?.method === 'DELETE')
        expect(del).toBeTruthy()
        expect(del[0]).toBe('/api/users/mike')
      })
    })

    it('does not delete when dismissed', async () => {
      const { user } = await setup()
      await user.click(screen.getByTitle('Delete mike'))
      await user.click(inDialog().getByRole('button', { name: /^cancel$/i }))
      expect(global.fetch.mock.calls.some(([, o]) => o?.method === 'DELETE')).toBe(false)
    })
  })

  describe('admin password reset', () => {
    it('requires 8+ characters', async () => {
      const { user } = await setup()
      await user.click(screen.getByTitle("Reset mike's password"))
      await user.type(screen.getByPlaceholderText('8+ characters'), 'short')
      expect(inDialog().getByRole('button', { name: /set password/i })).toBeDisabled()
    })

    it('PATCHes the new password for that user', async () => {
      const { user } = await setup()
      await user.click(screen.getByTitle("Reset mike's password"))
      await user.type(screen.getByPlaceholderText('8+ characters'), 'longenoughpw')
      await user.click(inDialog().getByRole('button', { name: /set password/i }))

      await waitFor(() => {
        const patch = global.fetch.mock.calls.find(([, o]) => o?.method === 'PATCH')
        expect(patch).toBeTruthy()
        expect(patch[0]).toBe('/api/users/mike/password')
        expect(JSON.parse(patch[1].body)).toEqual({ new_password: 'longenoughpw' })
      })
    })
  })

  describe('changing your own password', () => {
    const openOwn = async (user) => user.click(screen.getByTitle('Change my password'))

    it('will not submit unless the confirmation matches', async () => {
      const { user } = await setup()
      await openOwn(user)
      const dlg = inDialog()
      await user.type(dlg.getByPlaceholderText('8+ characters'), 'longenoughpw')
      await user.type(dlg.getByPlaceholderText('Repeat new password'), 'different123')
      expect(dlg.getByRole('button', { name: /update password/i })).toBeDisabled()
      expect(screen.getByText(/passwords don't match/i)).toBeInTheDocument()
    })

    it('still requires the current password even when the new pair matches', async () => {
      const { user } = await setup()
      await openOwn(user)
      const dlg = inDialog()
      await user.type(dlg.getByPlaceholderText('8+ characters'), 'longenoughpw')
      await user.type(dlg.getByPlaceholderText('Repeat new password'), 'longenoughpw')
      expect(dlg.getByRole('button', { name: /update password/i })).toBeDisabled()
    })

    it('sends only the current and new password, never the confirmation', async () => {
      const { user } = await setup()
      await openOwn(user)
      const dlg = inDialog()
      const [current] = dlg.getAllByDisplayValue('')
      await user.type(current, 'oldpassword')
      await user.type(dlg.getByPlaceholderText('8+ characters'), 'longenoughpw')
      await user.type(dlg.getByPlaceholderText('Repeat new password'), 'longenoughpw')
      await user.click(dlg.getByRole('button', { name: /update password/i }))

      await waitFor(() => {
        const post = global.fetch.mock.calls.find(
          ([u, o]) => o?.method === 'POST' && u === '/api/auth/change-password'
        )
        expect(post).toBeTruthy()
        expect(JSON.parse(post[1].body)).toEqual({
          current_password: 'oldpassword',
          new_password: 'longenoughpw',
        })
      })
    })
  })
})

describe('RoleBadge', () => {
  it('labels an admin', () => {
    render(<RoleBadge role="admin" />)
    expect(screen.getByText('Admin')).toBeInTheDocument()
  })

  it('labels a non-admin', () => {
    render(<RoleBadge role="viewer" />)
    expect(screen.getByText(/viewer/i)).toBeInTheDocument()
  })
})

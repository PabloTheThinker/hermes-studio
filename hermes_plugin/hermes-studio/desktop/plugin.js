/**
 * hermes-studio — Studio timeline as an in-Desktop section page.
 *
 * STAMP: studio-editor-v7-inpage-20261110
 *
 * Standalone desktop plugin (no .hermes-package.json marker):
 * loads enabled by default from desktop-plugins/hermes-studio/.
 *
 * Sidebar "Studio" + route /studio open INSIDE Hermes Desktop
 * (same pattern as other section plugins). The timeline is an iframe
 * to the desk embed URL; sandbox keeps scripts so the NLE runs.
 */
import {
  Button,
  EmptyState,
  GlyphSpinner,
  PALETTE_AREA,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  atom,
  host,
  useValue
} from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'

const PLUGIN_ID = 'hermes-studio'
const STAMP = 'studio-editor-v7-inpage-20261110'
const CMD = 'python3 ~/.hermes/scripts/hermes-studio-desktop-data.py --frame'

const $src = atom('')
const $loading = atom(false)
const $error = atom('')
const $stamp = atom(STAMP)

async function loadFrame() {
  if ($loading.get()) return
  $loading.set(true)
  $error.set('')
  try {
    const res = await host.request('shell.exec', { command: CMD }, 45_000)
    if (!res || res.code !== 0) {
      throw new Error((res && res.stderr) || 'studio frame failed')
    }
    const data = JSON.parse(res.stdout || '{}')
    if (!data.ok || typeof data.frame !== 'string' || data.frame.indexOf('https://') !== 0) {
      throw new Error(data.error || 'no studio frame')
    }
    const root = data.frame.endsWith('/') ? data.frame : data.frame + '/'
    $src.set(root + '#/edit')
  } catch (err) {
    $error.set(String(err && err.message ? err.message : err))
  } finally {
    $loading.set(false)
  }
}

function StudioPage() {
  const src = useValue($src)
  const loading = useValue($loading)
  const error = useValue($error)
  const stamp = useValue($stamp)

  if (!src) {
    return jsxs('div', {
      style: {
        height: '100%',
        minHeight: '100%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '16px',
        padding: '24px',
        boxSizing: 'border-box',
        background: 'var(--ui-bg-primary, #0b0b0c)',
        color: 'var(--ui-text-primary, #f2efe8)'
      },
      children: [
        jsx('div', {
          style: {
            fontSize: '13px',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: '#DEAB42'
          },
          children: 'Hermes Studio · in Desktop'
        }),
        jsx('div', {
          style: { fontSize: '22px', fontWeight: 600 },
          children: 'Timeline editor'
        }),
        jsx('div', {
          style: { fontSize: '12px', opacity: 0.55, fontFamily: 'ui-monospace, monospace' },
          children: stamp
        }),
        loading
          ? jsxs('div', {
              style: { display: 'flex', alignItems: 'center', gap: '10px', marginTop: '8px' },
              children: [
                jsx(GlyphSpinner, {}),
                jsx('span', { children: 'Opening desk frame…' })
              ]
            })
          : null,
        error
          ? jsxs('div', {
              style: { maxWidth: '420px', textAlign: 'center' },
              children: [
                jsx(EmptyState, {
                  title: 'Timeline did not open',
                  description: error
                }),
                jsx(Button, {
                  size: 'sm',
                  onClick: function () {
                    loadFrame()
                  },
                  children: 'Try again'
                })
              ]
            })
          : null,
        !loading && !error
          ? jsx(Button, {
              size: 'sm',
              onClick: function () {
                loadFrame()
              },
              children: 'Open timeline'
            })
          : null
      ]
    })
  }

  return jsxs('div', {
    style: {
      height: '100%',
      minHeight: '100%',
      display: 'flex',
      flexDirection: 'column',
      background: 'var(--ui-bg-primary, #0b0b0c)'
    },
    children: [
      jsxs('div', {
        style: {
          flex: '0 0 auto',
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          padding: '6px 12px',
          borderBottom: '1px solid var(--ui-border, #222)',
          fontSize: '12px',
          color: 'var(--ui-text-secondary, #aaa)'
        },
        children: [
          jsx('span', {
            style: { color: '#DEAB42', fontWeight: 600 },
            children: 'Studio'
          }),
          jsx('span', { children: '· timeline inside Desktop' }),
          jsx('span', {
            style: { marginLeft: 'auto', opacity: 0.5, fontFamily: 'ui-monospace, monospace' },
            children: stamp
          }),
          jsx(Button, {
            size: 'sm',
            onClick: function () {
              $src.set('')
              loadFrame()
            },
            children: 'Reload frame'
          })
        ]
      }),
      jsx('iframe', {
        title: 'Hermes Studio',
        src: src,
        allow: 'fullscreen; clipboard-read; clipboard-write',
        sandbox:
          'allow-scripts allow-same-origin allow-forms allow-downloads allow-popups allow-modals allow-pointer-lock',
        style: {
          flex: '1 1 auto',
          width: '100%',
          height: '100%',
          minHeight: 0,
          border: 0,
          margin: 0,
          background: 'transparent',
          display: 'block'
        }
      })
    ]
  })
}

export default {
  id: PLUGIN_ID,
  name: 'Studio',
  register(ctx) {
    try {
      if (host.logs) host.logs('info', '[' + PLUGIN_ID + '] register ' + STAMP)
    } catch (_) {}
    loadFrame()
    ctx.register({
      id: 'page',
      area: ROUTES_AREA,
      data: { path: '/studio' },
      render: function () {
        return jsx(StudioPage, {})
      }
    })
    ctx.register({
      id: 'nav',
      area: SIDEBAR_NAV_AREA,
      order: 40,
      data: {
        path: '/studio',
        label: 'Studio',
        codicon: 'device-camera-video'
      }
    })
    ctx.register({
      id: 'cmd-open',
      area: PALETTE_AREA,
      data: {
        id: 'studio.open',
        label: 'Studio: Timeline editor',
        keywords: ['studio', 'timeline', 'edit', 'open', 'nle'],
        run: function () {
          host.navigate('/studio')
        }
      }
    })
    ctx.register({
      id: 'cmd-open-alias',
      area: PALETTE_AREA,
      data: {
        id: 'studio.open-alias',
        label: 'Studio: Open',
        keywords: ['studio', 'open'],
        run: function () {
          host.navigate('/studio')
        }
      }
    })
  }
}

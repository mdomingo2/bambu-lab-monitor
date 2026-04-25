import { useEffect, useRef, useState } from 'react'
import { X, Loader2, VideoOff } from 'lucide-react'

// go2rtc WebSocket signaling protocol:
//   client → server: {type: "webrtc/offer",     value: "<sdp>"}
//   server → client: {type: "webrtc/answer",    value: "<sdp>"}
//   both directions: {type: "webrtc/candidate", value: "<candidate>"}

export function CameraModal({ printer, onClose }) {
  const videoRef = useRef(null)
  const [state, setState] = useState('connecting') // connecting | live | error
  const [errorMsg, setErrorMsg] = useState('')

  useEffect(() => {
    let pc = null
    let ws = null
    let dead = false

    const connect = async () => {
      pc = new RTCPeerConnection({
        iceServers: [
          { urls: ['stun:stun.l.google.com:19302', 'stun:stun1.l.google.com:19302'] },
        ],
      })

      // We only receive — add recvonly transceivers
      pc.addTransceiver('video', { direction: 'recvonly' })
      pc.addTransceiver('audio', { direction: 'recvonly' })

      pc.ontrack = (e) => {
        console.log('[camera] got track', e.track.kind)
        if (videoRef.current && e.streams[0]) {
          videoRef.current.srcObject = e.streams[0]
          setState('live')
        }
      }

      // Forward our ICE candidates to go2rtc
      pc.onicecandidate = (e) => {
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            type: 'webrtc/candidate',
            value: e.candidate ? e.candidate.candidate : '',
          }))
        }
      }

      pc.onconnectionstatechange = () => {
        console.log('[camera] pc state', pc.connectionState)
        if (pc.connectionState === 'failed' && !dead) {
          dead = true
          setErrorMsg('WebRTC connection failed')
          setState('error')
        }
      }

      const streamName = `bambu_${printer.id}`
      const wsProto = location.protocol === 'https:' ? 'wss' : 'ws'
      const wsUrl = `${wsProto}://${location.host}/go2rtc/api/ws?src=${encodeURIComponent(streamName)}`
      console.log('[camera] connecting to', wsUrl)
      ws = new WebSocket(wsUrl)

      ws.onopen = async () => {
        console.log('[camera] ws open — creating offer')
        const offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        // go2rtc expects {type: "webrtc/offer", value: "<sdp>"}
        ws.send(JSON.stringify({ type: 'webrtc/offer', value: offer.sdp }))
        console.log('[camera] offer sent')
      }

      ws.onmessage = async (ev) => {
        let msg
        try { msg = JSON.parse(ev.data) } catch { return }
        console.log('[camera] msg:', msg.type)

        if (msg.type === 'webrtc/answer') {
          await pc.setRemoteDescription({ type: 'answer', sdp: msg.value })
          console.log('[camera] remote description set')
        } else if (msg.type === 'webrtc/candidate' && msg.value) {
          try {
            await pc.addIceCandidate({ candidate: msg.value, sdpMid: '0' })
          } catch (err) {
            console.warn('[camera] addIceCandidate failed', err)
          }
        } else if (msg.type === 'error') {
          console.error('[camera] server error:', msg.value)
          const raw = msg.value || 'Stream unavailable'
          // Friendly hint for the most common failure
          const friendly = raw.includes('connection refused')
            ? 'LAN Mode not enabled on printer (port 322 refused)'
            : raw.includes('dial tcp')
            ? 'Cannot reach printer on local network'
            : raw
          setErrorMsg(friendly)
          setState('error')
        }
      }

      ws.onerror = (e) => {
        console.error('[camera] ws error', e)
        if (!dead) { dead = true; setErrorMsg('WebSocket error'); setState('error') }
      }

      ws.onclose = (e) => {
        console.log('[camera] ws closed', e.code, e.reason)
        // go2rtc closes WebSocket normally (1000) after signaling completes — that's fine
        if (e.code !== 1000 && !dead) {
          dead = true
          setErrorMsg(`WebSocket closed (${e.code})`)
          setState('error')
        }
      }
    }

    connect().catch((err) => {
      console.error('[camera] connect error', err)
      setErrorMsg(err.message)
      setState('error')
    })

    return () => {
      dead = true
      try { ws?.close(1000) } catch (_) {}
      try { pc?.close() } catch (_) {}
    }
  }, [printer.id])

  // Close on Escape
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-3xl mx-4 rounded-2xl overflow-hidden bg-zinc-950 shadow-2xl ring-1 ring-white/10"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 bg-zinc-900/80">
          <span className="text-white font-medium text-sm tracking-wide">
            {printer.name}
            <span className="ml-2 text-xs font-normal text-zinc-400">Live Camera</span>
          </span>
          <div className="flex items-center gap-3">
            {state === 'live' && (
              <span className="flex items-center gap-1.5 text-xs text-emerald-400">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                LIVE
              </span>
            )}
            <button
              onClick={onClose}
              className="text-zinc-400 hover:text-white transition-colors"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Video */}
        <div className="relative bg-black aspect-video flex items-center justify-center">
          {state === 'connecting' && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-zinc-400">
              <Loader2 size={28} className="animate-spin" />
              <span className="text-sm">Connecting to camera…</span>
            </div>
          )}
          {state === 'error' && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-zinc-500">
              <VideoOff size={28} />
              <span className="text-sm">Camera unavailable</span>
              {errorMsg && <span className="text-xs text-zinc-600">{errorMsg}</span>}
            </div>
          )}
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className={`w-full h-full object-contain transition-opacity duration-300 ${state === 'live' ? 'opacity-100' : 'opacity-0'}`}
          />
        </div>
      </div>
    </div>
  )
}

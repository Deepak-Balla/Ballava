// 📷 Add kitchen items from a photo: take one with the camera, or pick one from the gallery.
// On phones the phone's own camera opens. On a computer with a webcam, a live camera view opens in the app.
// The photo goes to Python (kitchen/api.py -> ai_scan), the AI names what it sees, and the items are added
// to the kitchen straight away, with Undo.
import React, { useEffect, useRef, useState } from 'react';
import { api, shrinkImage } from './lib.js';

const canLiveCamera = () => typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && window.isSecureContext
  && !window.matchMedia?.('(pointer: coarse)').matches; // phones: their own camera app is better

function LiveCamera({ onShot, onClose, notify }) {
  const video = useRef(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let stream;
    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment', width: { ideal: 1280 } }, audio: false })
      .then(s => { stream = s; if (video.current) { video.current.srcObject = s; setReady(true); } })
      .catch(() => { notify('The camera is not available. Choose a photo instead.'); onClose(); });
    return () => stream && stream.getTracks().forEach(t => t.stop());
  }, []);
  const snap = () => {
    const v = video.current;
    const scale = Math.min(1, 1024 / Math.max(v.videoWidth, v.videoHeight));
    const c = document.createElement('canvas');
    c.width = Math.round(v.videoWidth * scale); c.height = Math.round(v.videoHeight * scale);
    c.getContext('2d').drawImage(v, 0, 0, c.width, c.height);
    onShot(c.toDataURL('image/jpeg', 0.85).split(',')[1]);
  };
  return (
    <div className="sheet camera-sheet" role="dialog" aria-label="Take a photo">
      <div className="sheet-inner camera">
        <video ref={video} autoPlay playsInline muted aria-label="Camera view" />
        <p className="muted small">Point at your fridge, shelf or vegetable basket, with good light.</p>
        <div className="row">
          <button className="btn primary big" onClick={snap} disabled={!ready}>📸 Take photo</button>
          <button className="btn ghost" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

/**
 * The 📷 button. Props:
 *   onScanned({ found, unknown, added })  called after the items are added to the kitchen
 *   addToPantry(ids) -> ids actually added
 */
export default function PhotoScan({ addToPantry, notify, onScanned, onStart, compact = false, label = '📷 Photo' }) {
  const [open, setOpen] = useState(false);
  const [live, setLive] = useState(false);
  const [busy, setBusy] = useState(false);
  const camInput = useRef(null);
  const fileInput = useRef(null);

  async function scan(image) {
    setOpen(false); setLive(false); setBusy(true);
    onStart?.();
    try {
      const data = await api('ai/scan', { image, mediaType: 'image/jpeg' });
      const added = addToPantry(data.found);
      onScanned({ ...data, added });
    } catch (err) {
      onScanned({ error: err.message, found: [], unknown: [], added: [] });
    }
    setBusy(false);
  }
  async function onFile(e) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    try { scan(await shrinkImage(file)); } catch (err) { notify(err.message); }
  }

  return (
    <span className={'photo-scan' + (compact ? ' compact' : '')}>
      <button type="button" className={compact ? 'icon-btn photo-btn' : 'btn ghost photo-btn'} disabled={busy} onClick={() => setOpen(o => !o)}
        aria-label="Add items from a photo" aria-expanded={open} title="Add items from a photo">
        {busy ? '⏳' : compact ? '📷' : label}
      </button>
      {open && (
        <div className="photo-menu" role="menu">
          <button role="menuitem" onClick={() => (canLiveCamera() ? setLive(true) : camInput.current.click())}>📸 Take a photo</button>
          <button role="menuitem" onClick={() => fileInput.current.click()}>🖼️ Choose a photo</button>
          <span className="muted small">AI spots the items and adds them to your kitchen.</span>
        </div>
      )}
      <input ref={camInput} type="file" accept="image/*" capture="environment" onChange={onFile} hidden aria-label="Take a photo with the camera" />
      <input ref={fileInput} type="file" accept="image/*" onChange={onFile} hidden aria-label="Choose a photo of your kitchen" />
      {live && <LiveCamera onShot={scan} onClose={() => setLive(false)} notify={notify} />}
    </span>
  );
}

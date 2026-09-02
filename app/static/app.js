const languages = ['German', 'Auto', 'English', 'Chinese', 'Japanese', 'Korean', 'French', 'Russian', 'Portuguese', 'Spanish', 'Italian'];
const emotions = ['neutral', 'calm', 'warm', 'confident', 'gentle', 'happy', 'cheerful', 'excited', 'serious', 'dramatic', 'sad', 'angry', 'frustrated', 'fearful', 'nervous', 'surprised', 'whispering'];
const values = { '.language-select': languages, '.emotion-select': emotions, '.pace-select': ['slow', 'medium', 'medium_fast', 'fast'], '.energy-select': ['low', 'medium', 'high'], '.pitch-select': ['low', 'medium', 'high'] };
let voices = [];
let selectedVoice = null;

function populateSelects() {
  for (const [selector, options] of Object.entries(values)) {
    document.querySelectorAll(selector).forEach(select => {
      const selected = select.value || options[0];
      select.innerHTML = options.map(value => `<option value="${value}">${value.replace('_', ' ')}</option>`).join('');
      select.value = selected;
    });
  }
}

function toast(message, error = false) {
  const element = document.querySelector('#toast');
  element.textContent = message;
  element.style.background = error ? '#9e3434' : '';
  element.classList.add('show');
  window.setTimeout(() => element.classList.remove('show'), 3500);
}

async function readError(response) {
  try { const body = await response.json(); return body.detail?.message || body.detail || 'Unbekannter Fehler'; }
  catch { return `Anfrage fehlgeschlagen (${response.status})`; }
}

function selectedVoiceRecord() { return voices.find(voice => voice.name === selectedVoice); }

function audioTimestamp(item) {
  return item.created_at ? new Date(item.created_at).toLocaleString('de-DE') : 'Früher erzeugt';
}

async function loadVoices() {
  const response = await fetch('/voices');
  if (!response.ok) return toast(await readError(response), true);
  voices = await response.json();
  if (!voices.some(voice => voice.name === selectedVoice)) selectedVoice = voices[0]?.name || null;
  renderVoices();
  await loadAudio();
}

function renderVoices() {
  const list = document.querySelector('#voice-list');
  const voice = selectedVoiceRecord();
  document.querySelector('#selected-voice-name').textContent = voice?.name || 'Stimme links auswählen';
  document.querySelector('#selected-avatar').textContent = voice ? voice.name.slice(0, 2).toUpperCase() : '--';
  document.querySelector('#edit-selected').disabled = !voice;
  list.innerHTML = voices.length ? voices.map(item => `<article class="voice-card ${item.name === selectedVoice ? 'selected' : ''}"><button class="voice-select" data-select="${item.name}"><span class="avatar">${item.name.slice(0, 2).toUpperCase()}</span><span><strong>${item.name}</strong><span>${item.language} · ${item.type === 'clone' ? 'Clone' : 'Design'}</span></span></button><button class="icon-button voice-edit" data-edit="${item.name}" title="${item.name} bearbeiten"><i data-lucide="square-pen"></i></button></article>`).join('') : '<p class="empty-list">Noch keine Stimmen.</p>';
  list.querySelectorAll('[data-select]').forEach(button => button.addEventListener('click', async () => { selectedVoice = button.dataset.select; renderVoices(); await loadAudio(); }));
  list.querySelectorAll('[data-edit]').forEach(button => button.addEventListener('click', () => openEditor(button.dataset.edit)));
  lucide.createIcons();
}

function renderAudio(items) {
  const target = document.querySelector('#audio-results');
  const empty = document.querySelector('#result-empty');
  const heading = document.querySelector('#audio-heading');
  heading.textContent = selectedVoice ? `Audios: ${selectedVoice}` : 'Audios der aktiven Stimme';
  if (!selectedVoice) { target.innerHTML = ''; empty.style.display = 'grid'; empty.querySelector('p').textContent = 'Wähle eine Stimme, um ihre erzeugten Audios zu sehen.'; return; }
  if (!items.length) { target.innerHTML = ''; empty.style.display = 'grid'; empty.querySelector('p').textContent = 'Für diese Stimme wurden noch keine Audios erzeugt.'; return; }
  empty.style.display = 'none';
  target.innerHTML = items.map(item => `<article class="audio-card"><i class="audio-icon" data-lucide="audio-lines"></i><div><strong>${item.text}</strong><p>${audioTimestamp(item)} · WAV</p></div><audio controls src="${item.audio_url}"></audio><button class="icon-button" data-delete-audio="${item.generation_id}" title="Audio löschen"><i data-lucide="trash-2"></i></button></article>`).join('');
  target.querySelectorAll('[data-delete-audio]').forEach(button => button.addEventListener('click', () => deleteAudio(button.dataset.deleteAudio)));
  lucide.createIcons();
}

async function loadAudio() {
  if (!selectedVoice) return renderAudio([]);
  const response = await fetch(`/voices/${encodeURIComponent(selectedVoice)}/audio`);
  if (!response.ok) return toast(await readError(response), true);
  renderAudio(await response.json());
}

async function deleteAudio(generationId) {
  if (!selectedVoice || !confirm('Dieses erzeugte Audio wirklich löschen?')) return;
  const response = await fetch(`/voices/${encodeURIComponent(selectedVoice)}/audio/${generationId}`, { method: 'DELETE' });
  if (!response.ok) return toast(await readError(response), true);
  await loadAudio();
  toast('Audio gelöscht.');
}

function switchTab(name) {
  document.querySelectorAll('.tab').forEach(tab => tab.classList.toggle('active', tab.dataset.tab === name));
  document.querySelectorAll('.panel').forEach(panel => panel.classList.toggle('active', panel.id === `${name}-panel`));
}

function setBusy(form, busy, text) {
  const button = form.querySelector('[type=submit]');
  button.disabled = busy;
  if (busy) { button.dataset.label = button.innerHTML; button.innerHTML = `<i data-lucide="loader-circle"></i> ${text}`; lucide.createIcons(); }
  else button.innerHTML = button.dataset.label;
}

async function submitAudio(form) {
  if (!selectedVoice) return toast('Bitte zuerst eine Stimme in der Bibliothek auswählen.', true);
  setBusy(form, true, 'GPU generiert ...');
  try {
    const data = new FormData(form);
    data.set('voice_name', selectedVoice);
    const response = await fetch('/generate', { method: 'POST', body: data });
    if (!response.ok) throw new Error(await readError(response));
    const generationId = response.headers.get('X-Generation-ID');
    await loadAudio();
    const audio = document.querySelector(`[src="/audio/${generationId}"]`);
    if (audio) audio.play();
    toast('Audio ist bereit.');
  } catch (error) { toast(error.message, true); }
  finally { setBusy(form, false); }
}

function openEditor(name) {
  const voice = voices.find(item => item.name === name);
  if (!voice) return;
  const dialog = document.querySelector('#voice-dialog');
  document.querySelector('#edit-name').textContent = voice.name;
  const form = document.querySelector('#edit-form');
  form.description.value = voice.description || '';
  form.tags.value = (voice.tags || []).join(', ');
  form.language.value = voice.language || 'German';
  form.dataset.voice = voice.name;
  dialog.showModal();
}

function setup() {
  populateSelects();
  lucide.createIcons();
  document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => switchTab(button.dataset.tab)));
  document.querySelector('#refresh-voices').addEventListener('click', loadVoices);
  document.querySelector('#refresh-audio').addEventListener('click', loadAudio);
  document.querySelector('#edit-selected').addEventListener('click', () => openEditor(selectedVoice));
  document.querySelector('#intensity').addEventListener('input', event => document.querySelector('#intensity-value').textContent = event.target.value);
  document.querySelector('#generate-form').addEventListener('submit', event => { event.preventDefault(); submitAudio(event.currentTarget); });
  document.querySelector('#clone-form').addEventListener('submit', async event => {
    event.preventDefault(); const form = event.currentTarget; setBusy(form, true, 'Clone wird erstellt ...');
    try { const response = await fetch('/voices', { method: 'POST', body: new FormData(form) }); if (!response.ok) throw new Error(await readError(response)); selectedVoice = form.name.value; form.reset(); await loadVoices(); toast('Stimme wurde gespeichert.'); switchTab('generate'); }
    catch (error) { toast(error.message, true); } finally { setBusy(form, false); }
  });
  document.querySelector('#design-form').addEventListener('submit', async event => {
    event.preventDefault(); const form = event.currentTarget; setBusy(form, true, 'Stimme wird entworfen ...');
    try { const response = await fetch('/voices/design', { method: 'POST', body: new FormData(form) }); if (!response.ok) throw new Error(await readError(response)); selectedVoice = form.name.value; form.reset(); await loadVoices(); toast('Charakterstimme wurde gespeichert.'); switchTab('generate'); }
    catch (error) { toast(error.message, true); } finally { setBusy(form, false); }
  });
  document.querySelector('#edit-form').addEventListener('submit', async event => {
    event.preventDefault(); const form = event.currentTarget;
    try { const response = await fetch(`/voices/${encodeURIComponent(form.dataset.voice)}`, { method: 'PATCH', body: new FormData(form) }); if (!response.ok) throw new Error(await readError(response)); document.querySelector('#voice-dialog').close(); await loadVoices(); toast('Stimme aktualisiert.'); }
    catch (error) { toast(error.message, true); }
  });
  document.querySelector('#voice-dialog').insertAdjacentHTML('beforeend', '<button class="delete-voice" type="button" title="Stimme löschen"><i data-lucide="trash-2"></i> Stimme löschen</button>');
  document.querySelector('.delete-voice').addEventListener('click', async () => { const form = document.querySelector('#edit-form'); if (!confirm(`Stimme "${form.dataset.voice}" wirklich löschen?`)) return; const response = await fetch(`/voices/${encodeURIComponent(form.dataset.voice)}`, { method: 'DELETE' }); if (!response.ok) return toast(await readError(response), true); document.querySelector('#voice-dialog').close(); selectedVoice = null; await loadVoices(); toast('Stimme gelöscht.'); });
}

document.addEventListener('DOMContentLoaded', async () => { setup(); try { const response = await fetch('/health'); if (!response.ok) throw new Error(); document.querySelector('#service-status').classList.add('online'); document.querySelector('#service-status').lastChild.textContent = ' GPU bereit'; } catch { toast('Dienst ist nicht erreichbar.', true); } await loadVoices(); });

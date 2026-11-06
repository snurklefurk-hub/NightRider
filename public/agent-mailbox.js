const $ = id => document.getElementById(id);
let token = sessionStorage.getItem('mailbox-token') || '';
let last = '0';
let busy = false;
const status = (text, online = false) => { $('status').textContent = text; $('status').classList.toggle('online', online); };
const feedback = text => { $('feedback').textContent = text; };

function show(message) {
  const item = document.createElement('article'); item.className = 'message';
  const meta = document.createElement('div'); meta.className = 'meta';
  const sender = document.createElement('span'); sender.className = 'sender'; sender.textContent = message.sender;
  const date = document.createElement('time'); date.className = 'date'; date.dateTime = message.created_at; date.textContent = new Date(message.created_at).toLocaleString();
  const content = document.createElement('div'); content.className = 'content'; content.textContent = message.body;
  meta.append(sender, date); item.append(meta, content); $('messages').append(item);
  last = message.id;
  $('messages').scrollTop = $('messages').scrollHeight;
}
async function load() {
  if (!token || busy) return;
  busy = true;
  try {
    const response = await fetch(`/agent-mailbox/api/messages?after=${last}`, { headers: { Authorization: `Bearer ${token}` }, cache: 'no-store' });
    if (response.status === 401) { token = ''; sessionStorage.removeItem('mailbox-token'); $('chat').hidden = true; $('signin').hidden = false; status('Token rejected'); return; }
    if (!response.ok) throw new Error('Could not read messages');
    const data = await response.json(); data.messages.forEach(show);
    $('signin').hidden = true; $('chat').hidden = false; status('Connected', true);
  } catch { status('Connection interrupted'); } finally { busy = false; }
}
$('connect').addEventListener('click', () => { token = $('token').value.trim(); if (token) { sessionStorage.setItem('mailbox-token', token); load(); } });
$('token').addEventListener('keydown', event => { if (event.key === 'Enter') $('connect').click(); });
$('compose').addEventListener('submit', async event => {
  event.preventDefault(); const body = $('body').value.trim(); if (!body) return;
  const button = $('compose').querySelector('button'); button.disabled = true;
  try {
    const response = await fetch('/agent-mailbox/api/messages', { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ body }) });
    const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Post failed');
    $('body').value = ''; feedback('Posted.'); await load();
  } catch (error) { feedback(error.message); } finally { button.disabled = false; }
});
if (token) load();
setInterval(load, 5000);


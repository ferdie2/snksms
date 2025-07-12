import requests, time, os, re

TOKEN = os.environ.get("TOKEN")  # Ambil token dari Railway ENV
URL = f'https://api.telegram.org/bot{TOKEN}'
FILE_URL = f'https://api.telegram.org/file/bot{TOKEN}'
DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)

offset = 0
user_state = {}

COMMANDS = [
    {"command": "reset", "description": "Reset all your data"},
    {"command": "status", "description": "Show current file & mode"}
]
requests.post(f"{URL}/setMyCommands", json={"commands": COMMANDS})

def get_updates():
    global offset
    resp = requests.get(f'{URL}/getUpdates?timeout=100&offset={offset+1}')
    return resp.json().get('result', [])

def send_message(chat_id, text, reply_markup=None):
    data = {'chat_id': chat_id, 'text': text}
    if reply_markup:
        data['reply_markup'] = reply_markup
    requests.post(f'{URL}/sendMessage', json=data)

def send_code(chat_id, text):
    code = f"```c\n{text}\n```"
    requests.post(f"{URL}/sendMessage", data={
        "chat_id": chat_id,
        "text": code,
        "parse_mode": "Markdown"
    })

def download_file(file_id, save_path):
    r = requests.get(f'{URL}/getFile?file_id={file_id}').json()
    file_path = r['result']['file_path']
    file_url = f"{FILE_URL}/{file_path}"
    file_data = requests.get(file_url).content
    with open(save_path, 'wb') as f:
        f.write(file_data)

def extract_matches(lines, keywords, exact=False):
    result = []
    for kw in keywords:
        matches = []
        for i, line in enumerate(lines):
            match = re.search(rf'\b{re.escape(kw)}\b', line, re.I) if exact else kw.lower() in line.lower()
            if match:
                if i > 0 and re.search(r'(RVA|Offset|VA|0x)', lines[i-1]):
                    matches.append(lines[i-1])
                matches.append(line)
                if i + 1 < len(lines) and "{" in lines[i+1]:
                    matches.append(lines[i+1])
        if matches:
            result.append(f"\n🔑 {kw}")
            for j, line in enumerate(matches):
                prefix = "🧬 " if re.search(r'(RVA|Offset|VA|0x)', line) else "> "
                result.append(f"{prefix}{line.strip()}")
                if (j + 1) % 2 == 0:
                    result.append("")
    return "\n".join(result)

def handle_document(chat_id, file_id, filename):
    save_path = f"{DATA_DIR}/{chat_id}_{filename}"
    download_file(file_id, save_path)
    user_state[chat_id] = {
        'file': save_path,
        'mode': None,
        'keywords': []
    }
    btn = {
        "keyboard": [[{"text": "📍 Manual"}], [{"text": "⚙️ Config"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }
    send_message(chat_id, "📦 File received. Choose search mode:", reply_markup=btn)

def handle_message(chat_id, text):
    state = user_state.get(chat_id)

    if text.startswith("/reset"):
        files = [f for f in os.listdir(DATA_DIR) if f.startswith(str(chat_id))]
        for f in files:
            os.remove(os.path.join(DATA_DIR, f))
        user_state.pop(chat_id, None)
        send_message(chat_id, "🔄 Your data has been reset.")

    elif text.startswith("/status"):
        if state and 'file' in state:
            msg = f"📄 File: {os.path.basename(state['file'])}\n🔍 Mode: {state.get('mode', 'Not selected')}"
        else:
            msg = "ℹ️ No file uploaded yet."
        send_message(chat_id, msg)

    elif text == "📍 Manual":
        if not state or 'file' not in state or not os.path.exists(state['file']):
            send_message(chat_id, "❗ Please upload a .cs file first.")
            return
        user_state[chat_id]['mode'] = 'manual'
        user_state[chat_id]['keywords'] = []
        send_message(chat_id, "✅ Manual mode. Send keywords one by one. Use /done when finished.")

    elif text == "⚙️ Config":
        if not state or 'file' not in state or not os.path.exists(state['file']):
            send_message(chat_id, "❗ Please upload a .cs file first.")
            return
        user_state[chat_id]['mode'] = 'config'
        config_path = f"{DATA_DIR}/{chat_id}_config.txt"
        open(config_path, 'w').write("get_gold\nget_level")
        with open(config_path, 'rb') as f:
            requests.post(f"{URL}/sendDocument", data={"chat_id": chat_id}, files={"document": f})
        send_message(chat_id, "🛠️ Edit & re-name to config.txt & re-upload")

    elif text == "/done" and state and state.get('mode') == 'manual':
        lines = open(state['file'], encoding='utf-8', errors='ignore').readlines()
        result = extract_matches(lines, state['keywords'], exact=False)
        send_code(chat_id, result or "❌ Nothing found.")

    elif state and state.get('mode') == 'manual':
        user_state[chat_id]['keywords'].append(text.strip())
        send_message(chat_id, f"➕ Keyword added: `{text.strip()}`")

    elif state and 'file' in state:
        send_message(chat_id, "📄 Using previously uploaded file. Choose a mode.")

    else:
        send_message(chat_id, "❗ Please upload a .cs file first.")

def handle_config_upload(chat_id, file_id):
    config_path = f"{DATA_DIR}/{chat_id}_config.txt"
    download_file(file_id, file_path=config_path)
    keywords = [x.strip() for x in open(config_path, encoding='utf-8').readlines() if x.strip()]
    cs_path = user_state[chat_id]['file']
    lines = open(cs_path, encoding='utf-8', errors='ignore').readlines()
    result = extract_matches(lines, keywords, exact=True)
    send_code(chat_id, result or "❌ Nothing found.")

print("🤖 Bot running...")
while True:
    updates = get_updates()
    for u in updates:
        offset = u['update_id']
        msg = u.get('message', {})
        chat_id = msg.get('chat', {}).get('id')

        if 'document' in msg:
            fname = msg['document']['file_name']
            fid = msg['document']['file_id']
            if fname.endswith(".cs"):
                handle_document(chat_id, fid, fname)
            elif fname == "config.txt":
                handle_config_upload(chat_id, fid)

        elif 'text' in msg:
            text = msg['text']
            if text.strip() == '.' and 'reply_to_message' in msg:
                replied = msg['reply_to_message']
                if 'text' in replied:
                    save_path = f"{DATA_DIR}/{chat_id}_saved_result.txt"
                    with open(save_path, 'w', encoding='utf-8') as f:
                        f.write(replied['text'])
                    with open(save_path, 'rb') as f:
                        requests.post(f"{URL}/sendDocument", data={"chat_id": chat_id}, files={"document": f})
                    send_message(chat_id, "✅ Result saved & sent to you.")
                else:
                    send_message(chat_id, "⚠️ No text found in the replied message.")
            else:
                handle_message(chat_id, text)

    time.sleep(1)
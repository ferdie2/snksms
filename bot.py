import os
import requests
import time
from yt_dlp import YoutubeDL

BOT_TOKEN = "8115892574:AAHhCuq04Hcy0OoaXqkDmuqOQtf5UBZkl9w"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"
offset = None
state = {}

def send_message(chat_id, text):
    resp = requests.post(API_URL + "sendMessage", data={"chat_id": chat_id, "text": text})
    return resp.json().get("result", {}).get("message_id")

def send_video_or_document(chat_id, file_path):
    size = os.path.getsize(file_path)
    with open(file_path, "rb") as f:
        if file_path.endswith(".mp4") and size < 50 * 1024 * 1024:
            requests.post(API_URL + "sendVideo", data={"chat_id": chat_id}, files={"video": f})
        else:
            requests.post(API_URL + "sendDocument", data={"chat_id": chat_id}, files={"document": f})

def edit_message(chat_id, message_id, new_text):
    requests.post(API_URL + "editMessageText", data={
        "chat_id": chat_id,
        "message_id": message_id,
        "text": new_text
    })

def get_updates():
    global offset
    response = requests.get(API_URL + "getUpdates", params={"offset": offset, "timeout": 100})
    return response.json().get("result", [])

def get_available_resolutions(url):
    ydl_opts = {"quiet": True, "skip_download": True}
    resolutions = {}
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        for f in info.get("formats", []):
            if f.get("vcodec") != "none" and f.get("height") and f.get("ext") == "mp4":
                label = f"{f['height']}p"
                resolutions[label] = f["format_id"]
    return dict(sorted(resolutions.items(), key=lambda x: int(x[0][:-1])))

def download_with_aria2(url, chat_id=None, message_id=None, output_format="mp4", mp3_bitrate="192", format_id=None):
    outtmpl = "%(title).80s.%(ext)s"
    progress = {"percent": 0}

    def hook(d):
        if d['status'] == 'downloading':
            p = d.get('_percent_str', '').strip()
            if p.endswith('%'):
                try:
                    percent = int(float(p.strip('%')))
                    if percent != progress["percent"]:
                        progress["percent"] = percent
                        bar = f"[{'█'*int(percent/10)}{' '*(10-int(percent/10))}] {percent}%"
                        if chat_id and message_id:
                            edit_message(chat_id, message_id, f"📥 Sedang mengunduh...\n{bar}")
                except: pass

    ydl_opts = {
        "outtmpl": outtmpl,
        "quiet": True,
        "external_downloader": "aria2c",
        "external_downloader_args": ["-x", "16", "-k", "1M"],
        "progress_hooks": [hook],
        "noplaylist": True,
        "merge_output_format": "mp4"
    }

    if output_format == "mp3":
        ydl_opts["format"] = "bestaudio"
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": mp3_bitrate,
        }]
    else:
        if format_id and "+bestaudio" not in format_id:
            ydl_opts["format"] = f"{format_id}+bestaudio[ext=m4a]/best"
        else:
            ydl_opts["format"] = format_id or "best"

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if output_format == "mp3":
            filename = os.path.splitext(filename)[0] + ".mp3"
    return filename

def main():
    global offset
    print("🤖 Bot aktif...")

    while True:
        updates = get_updates()
        for update in updates:
            offset = update["update_id"] + 1

            if "message" in update:
                msg = update["message"]
                chat_id = msg["chat"]["id"]
                text = msg.get("text", "").strip()
                step = state.get(chat_id, {}).get("step")

                if text == "/start":
                    send_message(chat_id,
                        "👋 Welcome to *TSS Downloader Bot*\n"
                        "🔹 Download YouTube & TikTok dengan pilihan resolusi & format.\n"
                        "🚀 Booster Aria2c + progress bar realtime.\n"
                        "📣 Feedback: @YourUsernameHere\n\n"
                        "▶️ Commands:\n"
                        "/yt - YouTube\n"
                        "/tt - TikTok"
                    )
                    state[chat_id] = {}

                elif text == "/tt":
                    state[chat_id] = {"step": "awaiting_tiktok_url"}
                    send_message(chat_id, "📹 Kirim link TikTok:")

                elif step == "awaiting_tiktok_url":
                    if "tiktok.com" not in text:
                        send_message(chat_id, "❌ Link TikTok tidak valid.")
                        continue
                    msg_id = send_message(chat_id, "📥 Mengunduh TikTok...")
                    try:
                        filepath = download_with_aria2(text, chat_id, msg_id)
                        send_video_or_document(chat_id, filepath)
                        os.remove(filepath)
                    except Exception as e:
                        send_message(chat_id, f"❌ Error: {e}")
                    state[chat_id] = {}

                elif text == "/yt":
                    state[chat_id] = {"step": "awaiting_youtube_url"}
                    send_message(chat_id, "🔗 Kirim link YouTube:")

                elif step == "awaiting_youtube_url":
                    state[chat_id]["url"] = text
                    state[chat_id]["step"] = "awaiting_format_choice"
                    requests.post(API_URL + "sendMessage", json={
                        "chat_id": chat_id,
                        "text": "🎬 Pilih format download:",
                        "reply_markup": {
                            "inline_keyboard": [
                                [{"text": "🎥 MP4 (Video)", "callback_data": "format_mp4"}],
                                [{"text": "🎧 MP3 (Audio Only)", "callback_data": "format_mp3"}]
                            ]
                        }
                    })

            elif "callback_query" in update:
                cb = update["callback_query"]
                data = cb["data"]
                chat_id = cb["message"]["chat"]["id"]
                msg_id = cb["message"]["message_id"]
                url = state.get(chat_id, {}).get("url")

                if data == "format_mp3":
                    send_message(chat_id, "🎧 Mengunduh MP3...")
                    try:
                        filepath = download_with_aria2(url, chat_id, msg_id, output_format="mp3")
                        send_video_or_document(chat_id, filepath)
                        os.remove(filepath)
                    except Exception as e:
                        send_message(chat_id, f"❌ Error: {e}")
                    state[chat_id] = {}

                elif data == "format_mp4":
                    try:
                        resolutions = get_available_resolutions(url)
                        if not resolutions:
                            send_message(chat_id, "❌ Tidak ada resolusi ditemukan.")
                            state[chat_id] = {}
                            continue
                        state[chat_id]["resolutions"] = resolutions

                        buttons = []
                        temp = []
                        for label, fmt_id in resolutions.items():
                            temp.append({"text": label, "callback_data": f"res_{fmt_id}"})
                            if len(temp) == 3:
                                buttons.append(temp)
                                temp = []
                        if temp:
                            buttons.append(temp)

                        requests.post(API_URL + "sendMessage", json={
                            "chat_id": chat_id,
                            "text": "📺 Pilih resolusi:",
                            "reply_markup": {
                                "inline_keyboard": buttons
                            }
                        })

                    except Exception as e:
                        send_message(chat_id, f"❌ Error ambil resolusi: {e}")
                        state[chat_id] = {}

                elif data.startswith("res_"):
                    format_id = data[4:]
                    send_message(chat_id, "⬇️ Mengunduh resolusi yang dipilih...")
                    try:
                        filepath = download_with_aria2(state[chat_id]["url"], chat_id, msg_id, format_id=format_id)
                        send_video_or_document(chat_id, filepath)
                        os.remove(filepath)
                    except Exception as e:
                        send_message(chat_id, f"❌ Error: {e}")
                    state[chat_id] = {}

        time.sleep(1)

if __name__ == "__main__":
    main()

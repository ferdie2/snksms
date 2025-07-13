import os
import requests
from flask import Flask, request
from yt_dlp import YoutubeDL

BOT_TOKEN = os.environ.get("BOT_TOKEN")
APP_URL = os.environ.get("APP_URL")  # e.g. https://tss-bot.up.railway.app
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"
app = Flask(__name__)
state = {}

def send_message(chat_id, text):
    requests.post(API_URL + "sendMessage", data={"chat_id": chat_id, "text": text})

def send_video(chat_id, file_path):
    with open(file_path, "rb") as f:
        size = os.path.getsize(file_path)
        if file_path.endswith(".mp4") and size < 50 * 1024 * 1024:
            requests.post(API_URL + "sendVideo", data={"chat_id": chat_id}, files={"video": f})
        else:
            requests.post(API_URL + "sendDocument", data={"chat_id": chat_id}, files={"document": f})

def get_resolutions(url):
    ydl_opts = {"quiet": True, "skip_download": True}
    resolutions = {}
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        for f in info.get("formats", []):
            if f.get("vcodec") != "none" and f.get("height") and f.get("ext") == "mp4":
                label = f"{f['height']}p"
                resolutions[label] = f["format_id"]
    return dict(sorted(resolutions.items(), key=lambda x: int(x[0][:-1])))

def download_video(url, output_format="mp4", format_id=None):
    ydl_opts = {
        "outtmpl": "%(title).80s.%(ext)s",
        "quiet": True,
        "merge_output_format": "mp4",
    }

    if output_format == "mp3":
        ydl_opts["format"] = "bestaudio"
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192"
        }]
    else:
        ydl_opts["format"] = f"{format_id}+bestaudio/best" if format_id else "best"

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        file_path = ydl.prepare_filename(info)
        if output_format == "mp3":
            file_path = os.path.splitext(file_path)[0] + ".mp3"
    return file_path

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = request.get_json()

    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        step = state.get(chat_id, {}).get("step")

        if text == "/start":
            send_message(chat_id,
                "👋 Selamat datang di *TSS Downloader Bot*\n"
                "🔹 Download YouTube & TikTok dengan pilihan resolusi & format.\n"
                "📣 Feedback: @YourUsernameHere\n\n"
                "▶️ /yt - YouTube\n"
                "▶️ /tt - TikTok"
            )
            state[chat_id] = {}

        elif text == "/tt":
            state[chat_id] = {"step": "tt"}
            send_message(chat_id, "📹 Kirim link TikTok:")

        elif text == "/yt":
            state[chat_id] = {"step": "yt"}
            send_message(chat_id, "🔗 Kirim link YouTube:")

        elif step == "tt" and "tiktok.com" in text:
            send_message(chat_id, "📥 Mengunduh TikTok...")
            try:
                path = download_video(text)
                send_video(chat_id, path)
                os.remove(path)
            except Exception as e:
                send_message(chat_id, f"❌ Error: {e}")
            state[chat_id] = {}

        elif step == "yt" and "youtube.com" in text:
            state[chat_id] = {"step": "yt_res", "url": text}
            resolutions = get_resolutions(text)
            buttons = []
            row = []
            for i, (label, fid) in enumerate(resolutions.items()):
                row.append({"text": label, "callback_data": f"ytres_{fid}"})
                if len(row) == 3:
                    buttons.append(row)
                    row = []
            if row:
                buttons.append(row)
            buttons.append([{"text": "🎧 MP3 (Audio Only)", "callback_data": "ytmp3"}])
            requests.post(API_URL + "sendMessage", json={
                "chat_id": chat_id,
                "text": "📺 Pilih resolusi video atau MP3:",
                "reply_markup": {"inline_keyboard": buttons}
            })

    elif "callback_query" in update:
        cb = update["callback_query"]
        data = cb["data"]
        chat_id = cb["message"]["chat"]["id"]
        url = state.get(chat_id, {}).get("url")

        if data == "ytmp3":
            send_message(chat_id, "🎧 Mengunduh MP3...")
            try:
                path = download_video(url, output_format="mp3")
                send_video(chat_id, path)
                os.remove(path)
            except Exception as e:
                send_message(chat_id, f"❌ Error: {e}")
            state[chat_id] = {}

        elif data.startswith("ytres_"):
            fmt = data.split("_")[1]
            send_message(chat_id, "📥 Mengunduh Video...")
            try:
                path = download_video(url, format_id=fmt)
                send_video(chat_id, path)
                os.remove(path)
            except Exception as e:
                send_message(chat_id, f"❌ Error: {e}")
            state[chat_id] = {}

    return {"ok": True}

@app.route("/", methods=["GET"])
def home():
    return "TSS BOT ACTIVE"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

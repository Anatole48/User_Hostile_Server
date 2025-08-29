from flask import Flask, request, jsonify
import logging
import yt_dlp
import sys
import json
import psutil
import os
import whisper
from deep_translator import GoogleTranslator
import subprocess
from pathlib import Path
import shutil
import time
import threading
import ffmpeg
import re
import unicodedata
import numpy as np

lock = threading.Lock()

whisper_model_ram_GB_need = {
    "tiny": 1,
    "base": 1,
    "small": 1.5,
    "medium": 5,
    "large": 10,
    "turbo": 6
}

PORT = 2000

download_status = {}

whisper_size_model = "small"
whisper_model = whisper.load_model(whisper_size_model)

def make_hook(url, download_status):
    def my_hook(d):
        default_filename = d['filename'].replace("\\", "/").split("/")[-1]
        filename_list = default_filename.split(".")
        filename = ""
        if "format_id" in d.get("info_dict", {}) and filename_list[-2]=='f'+d['info_dict']['format_id'] :
            del(filename_list[-2])
        del(filename_list[-1])
        for i in range(len(filename_list)-1):
            filename += filename_list[i] + "."
        filename += filename_list[len(filename_list)-1]

        if d['status'] == 'downloading':
            download_status[url] = {
                "filename": filename,
                "percent": d['_percent_str'],
                "remaining_time": d['_eta_str']
            }
    return my_hook


def download_video(url, title, download_status, download_path):
    ydl_opts = {
        'noprogress': True,
        "quiet": True,
        'progress_hooks': [make_hook(url, download_status)],
        'no_color': True,
	    'format_sort': ['res:1080', 'ext:mkv'],
	    'outtmpl': download_path + title + '.%(ext)s',
        'merge_output_format': 'mkv',
        'ignoreerrors': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def download_music(url, title, download_status, download_path):
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a',
        }],
        'noprogress': True,
        "quiet": True,
        'progress_hooks': [make_hook(url, download_status)],
        'no_color': True,
	    'outtmpl': download_path + title + '.%(ext)s',
        'ignoreerrors': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def string_normalisation(title):
    # Normalise les caractères (ex : accents)
    title = unicodedata.normalize("NFKD", title)
    title = title.encode("ascii", "ignore").decode("ascii")  # Supprime les caractères non-ASCII

    # Remplace les séparateurs typiques et caractères problématiques
    title = re.sub(r"[\/:*?\"<>|]", " ", title)  # Caractères interdits sous Windows
    title = re.sub(r"\s+", " ", title).strip()   # Supprime les espaces multiples
    title = re.sub(r"[^\w\s\-\.]", "", title)    # Garde lettres, chiffres, tirets, points
    return title


def start_timer(url, filename, duration, download_status):
    start_time = time.time()
    running = True
    download_status[url] = {
        "filename": filename,
        "status": "Subtitle Generation"
    }

    def show_elapsed_time(download_status, duration):
        while running:
            progression_percentage = round((((time.time() - start_time) / duration) * 100), 1)
            if progression_percentage < 100:

                download_status[url]["percent"] = str(progression_percentage)+"%"
            else:
                download_status[url]["percent"] = "100%"
            time.sleep(1)

    timer_thread = threading.Thread(target=show_elapsed_time, args=(download_status, duration))
    timer_thread.daemon = True
    timer_thread.start()

    def stop():
        nonlocal running  # Permet de modifier la variable `running` définie dans la fonction parente
        running = False
    
    return stop


def get_media_duration(video_file):
    probe = ffmpeg.probe(video_file)
    video_duration = float(probe['format']['duration'])
    return video_duration


def get_media_language(whisper_model, input_file, video_duration):
    # Taille d'un segment de 30 secondes (en échantillons)
    chunk_size = 30 * whisper.audio.SAMPLE_RATE  

    # Calculer le point de départ : milieu de la vidéo - 15s
    start_time = max(0, (video_duration/2 - 15))
    start_sample = int(start_time * whisper.audio.SAMPLE_RATE)
    end_sample = start_sample + chunk_size

    # Extraire la portion
    audio = whisper.load_audio(input_file)
    chunk = audio[start_sample:end_sample]

    # Charger l'audio et prendre 60 secondes
    audio = whisper.pad_or_trim(chunk, length=chunk_size)

    # Calculer spectrogramme
    mel = whisper.log_mel_spectrogram(audio).to(whisper_model.device)

    # Détection de langue
    _, probs = whisper_model.detect_language(mel)
    language = max(probs, key=probs.get)
    return(language)


# Convertir temps au format hh:mm:ss,ms
def timestamp_to_srt_time_format_conversion(timestamp):
    hour = int(timestamp // 3600)
    minute = int((timestamp % 3600) // 60)
    second = int(timestamp % 60)
    millisecond = int((timestamp - int(timestamp)) * 1000)
    return f"{hour:02}:{minute:02}:{second:02},{millisecond:03}"


# Sauvegarder en format SRT
def subtitle_generation(whisper_model, download_status, url, video_title, input_file):
    with lock:
        subtitle_generation_duration_filename = os.path.dirname(os.path.abspath(__file__)) + "/subtitle_generation_duration.txt"
        video_duration = get_media_duration(input_file)
        lines = []
        if os.path.exists(subtitle_generation_duration_filename):
            with open(subtitle_generation_duration_filename, "r", encoding="utf-8") as subtitle_generation_duration_file:
                lines = subtitle_generation_duration_file.readlines()

            subtitle_generation_stats = []
            for line in lines:
                striped_line = line[:-1].split(" ")
                video_duration_history = float(striped_line[1])
                subtitle_generation_duration_history = float(striped_line[2])
                subtitle_generation_stats += [(video_duration_history, subtitle_generation_duration_history)]

            if len(lines)>=2 :
                x = np.array([point[0] for point in subtitle_generation_stats])
                y = np.array([point[1] for point in subtitle_generation_stats])
                a, b = np.polyfit(x, y, 1)
                estimated_generation_time = video_duration*a + b
            else:
                estimated_generation_time = video_duration*subtitle_generation_duration_history/video_duration_history
        else:
            estimated_generation_time = 1000

        stop_timer = start_timer(url, video_title, estimated_generation_time, download_status)
        date = time.strftime("%Y-%m-%d")
        fonction_begin_timestamp = time.time()

        language = get_media_language(whisper_model, input_file, video_duration)
        transcript = whisper_model.transcribe(
            input_file,
            task="transcribe",         # Pour transcription (et non traduction)
            language=language,
            fp16=False                 # À desactiver si pas de GPU compatible
        )
        
        output_file = input_file[:-4] + "_" + language + ".srt"
        with open(output_file, "w", encoding="utf-8") as subtitle_file:
            for segment in transcript["segments"]:
                start = segment["start"]
                end = segment["end"]
                text = segment["text"]

                subtitle_file.write(f"{segment['id'] + 1}\n")
                subtitle_file.write(f"{timestamp_to_srt_time_format_conversion(start)} --> {timestamp_to_srt_time_format_conversion(end)}\n")
                subtitle_file.write(f"{text.strip()}\n\n")

        stop_timer()
        fonction_end_timestamp = time.time()
        
        max_lines = 1000
        if len(lines) >= max_lines:
            lines = lines[len(lines) - max_lines + 1:]
        
        reel_generation_time = fonction_end_timestamp - fonction_begin_timestamp
        lines += [f"{date} {video_duration} {reel_generation_time} {(reel_generation_time - estimated_generation_time)/estimated_generation_time*100}\n"] 

        with open(subtitle_generation_duration_filename, "w", encoding="utf-8") as subtitle_generation_duration_file:
            subtitle_generation_duration_file.writelines(lines)
        return(language, output_file)


def translate_subtitles(download_status, url, title, input_subtitle_language, input_file, output_file):
    if input_subtitle_language != 'fr':
        with open(input_file, "r", encoding="utf-8") as subtitle_original_file:
            subtitle_original_file_length = len(subtitle_original_file.readlines())

        with open(input_file, "r", encoding="utf-8") as input_subtitle_file:
            lines = input_subtitle_file.readlines()

        translated_lines = []
        for i in range(len(lines)):
            line = lines[i]
            download_status[url] = {
                "filename": title,
                "percent": str(round(i/subtitle_original_file_length*100, 1)) + "%",
                "status": "Subtitle Translation"
            }
            if line.strip().isdigit() or "-->" in line or line.strip() == "":
                translated_lines.append(line)
            else:
                try:
                    translated = GoogleTranslator(source=input_subtitle_language, target='fr').translate(line)
                except:
                    translated = line
                if translated == None:
                    translated_lines.append("\n")
                else:
                    translated_lines.append(translated + "\n")

        with open(output_file, "w", encoding="utf-8") as output_subtitle_file:
            output_subtitle_file.writelines(translated_lines)


def all_subtitle_generation(whisper_model, download_status, url, title, video_path):
    (origin_language, origin_language_subtitle_file) = subtitle_generation(whisper_model, download_status, url, title, video_path)
    french_subtitle_file = origin_language_subtitle_file[:-6] + "_fr.srt"
    translate_subtitles(download_status, url, title, origin_language, origin_language_subtitle_file, french_subtitle_file)


def merge_video_and_subtitles(video_path, subtitle_files_list, output_path):
    command = [
        "ffmpeg",
        "-i", video_path
    ]

    for k in range(len(subtitle_files_list)):
        command += ["-i", subtitle_files_list[k]]

    command += [
        "-map", "0:v",
        "-map", "0:a"
    ]

    for i in range(len(subtitle_files_list)):
        command += ["-map", str(i+1) + ":0"]

    command += [
        "-c", "copy",
        "-c:s", "srt"
    ]

    for j in range(len(subtitle_files_list)):
        command += ["-metadata:s:s:" + str(j), "title=" + subtitle_files_list[j][-6:-4]]
    
    command += [
        "-disposition:s:1", "default",
        output_path
    ]

    try:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors de l'exécution de ffmpeg : {e}")


def download_setup(whisper_model, whisper_size_model, download_status, url, title, download_type, download_path, subtitle_generation):
    download_path = download_path.replace("\\", "/")
    if download_path[-1] != "/":
        download_path += "/"

    shell_name = psutil.Process().parent().name()
    if shell_name == "powershell.exe":
        if download_path[0:7] == "/mnt/c/":
            download_path = "C:/" + download_path[7:]
    elif shell_name == "bash" or shell_name == "tmux: server":
        if download_path[0:3] == "C:/":
            download_path = "/mnt/c/" + download_path[3:]

    if download_type == "video":
        if not os.path.isfile(download_path + title + ".mkv"):
            if subtitle_generation:
                normalize_title = string_normalisation(title)
                subtile_build_directory = download_path + normalize_title + "/"
                os.makedirs(subtile_build_directory , exist_ok=True)
                download_video(url, title, download_status, subtile_build_directory)
                downloaded_file = subtile_build_directory + os.listdir(subtile_build_directory)[0]
            
                all_subtitle_generation(whisper_model, download_status, url, title, downloaded_file)
                output_video_path = download_path + title + ".mkv"
                subtitle_files_list = [str(path) for path in Path(subtile_build_directory).glob("*.srt")]
                merge_video_and_subtitles(downloaded_file, subtitle_files_list, output_video_path)
                shutil.rmtree(subtile_build_directory, ignore_errors=True)
            else:
                download_video(url, title, download_status, download_path)
        else:
            download_status[url] = {
                "filename": title,
                "status": "Already Downloaded"
            }
            time.sleep(2)

    elif download_type == "music":
        if not os.path.isfile(download_path + title + ".m4a"):
            download_music(url, title, download_status, download_path)
        else:
            download_status[url] = {
                "filename": title,
                "status": "Already Downloaded"
            }
            time.sleep(2)

    download_status[url] = {
        "filename": title,
        "status": "END"
    }


app = Flask(__name__)

logging_level = logging.WARNING
server_folder_path = os.path.dirname(os.path.abspath(__file__))
logging_path_file = server_folder_path + "/server.log"
if os.path.exists(logging_path_file):
    with open(logging_path_file, 'a', encoding='utf-8') as logfile:
        logfile.write("\n\n\n")

# Configurer le logger Flask/Werkzeug pour écrire les logs dans un fichier
logging.basicConfig(
    filename=logging_path_file,        # fichier de log
    filemode='a',
    level=logging_level,         # niveau minimum (DEBUG, INFO, WARNING, ERROR)
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# Configurer le logger pour continuer a afficher les logs dans la console
console = logging.StreamHandler()
console.setLevel(logging_level)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
console.setFormatter(formatter)
logging.getLogger().addHandler(console)


@app.before_request
def filter_non_http_requests():
    # Recupere le protocol de la requete
    request_protocol = request.environ.get("SERVER_PROTOCOL")
    
    # Ne traite pas les requetes non http
    if request_protocol not in ("HTTP/1.1", "HTTP/2"):
        return "", 204  # 204 = "No Content" → pas d'erreur


@app.route("/", methods=["POST"])
def server_request_treatment():
    client_request = request.get_json()
    purpose = client_request.get("purpose")

    if purpose == "check_download_status_initialization":
        return jsonify(download_status)
    elif purpose == "check_download_status":
        url = client_request["video_url"]
        return jsonify(download_status[url])
    elif purpose == "clear_downloaded_video_data":
        url = client_request["video_url"]
        del download_status[url]
        return("Download Data Cleared")
    else:
        url = client_request["url"]
        title = client_request["title"]
        download_type = client_request["download_type"]
        download_path = client_request["download_path"]
        subtitle_generation = client_request["subtitle_generation"]

        if url not in download_status:
            download_status[url] = {"filename": title, "status": "Initialisation..."}
            thread = threading.Thread(target=download_setup, args=(whisper_model, whisper_size_model, download_status, url, title, download_type, download_path, subtitle_generation))
            thread.start()
            return ("Download Launched")
        else:
            return("This file is already downloading")

print('Serveur en écoute. Port : ' + str(PORT), flush=True)
app.run(host="0.0.0.0", port=PORT, threaded=True)
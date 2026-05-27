from flask import Flask, request, jsonify
from flask_cors import CORS
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
import datetime
import time
import threading
import multiprocessing
import ffmpeg
import re
import unicodedata
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

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
cancel_download_dict = {}

whisper_size_model = "small"
whisper_model = whisper.load_model(whisper_size_model)

def make_hook(url, download_status, cancel_download):
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

        if cancel_download.is_set():
            raise yt_dlp.utils.DownloadCancelled("Download cancelled by user")

        if d['status'] == 'downloading':
            download_status[url] = {
                "filename": filename,
                "percent": d['_percent_str'],
                "remaining_time": d['_eta_str']
            }
    return my_hook


def download_video(url, title, download_status, download_path, cancel_download):
    if not cancel_download.is_set():
        download_file_path =  download_path + title + '.%(ext)s'
        ydl_opts = {
            'noprogress': True,
            "quiet": True,
            'progress_hooks': [make_hook(url, download_status, cancel_download)],
            'no_color': True,
            'format_sort': ['res:1080', 'ext:mkv'],
            'outtmpl': download_file_path,
            'merge_output_format': 'mkv'
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except yt_dlp.utils.DownloadCancelled as ERROR:
            for file in os.listdir(download_path):
                if file.startswith(title) and file.endswith(".part"):
                    os.remove(os.path.join(download_path, file))


def download_music(url, title, download_status, download_path, cancel_download):
    if not cancel_download.is_set():
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
            }],
            'noprogress': True,
            "quiet": True,
            'progress_hooks': [make_hook(url, download_status, cancel_download)],
            'no_color': True,
            'outtmpl': download_path + title + '.%(ext)s',
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except yt_dlp.utils.DownloadError as ERROR:
            for file in os.listdir(download_path):
                if file.startswith(title) and file.endswith(".part"):
                    os.remove(os.path.join(download_path, file))


def string_normalisation(title):
    # Normalise les caractères (ex : accents)
    title = unicodedata.normalize("NFKD", title)
    title = title.encode("ascii", "ignore").decode("ascii")  # Supprime les caractères non-ASCII

    # Remplace les séparateurs typiques et caractères problématiques
    title = re.sub(r"[\/:*?\"<>|]", " ", title)  # Caractères interdits sous Windows
    title = re.sub(r"\s+", " ", title).strip()   # Supprime les espaces multiples
    title = re.sub(r"[^\w\s\-\.]", "", title)    # Garde lettres, chiffres, tirets, points
    return title


def hardware_stats_graph_generation(subtitle_generation_hardware_stats_file_path):
    figure_title = subtitle_generation_hardware_stats_file_path.split("/")[-1][:-4]
    data = pd.read_csv(subtitle_generation_hardware_stats_file_path, sep=" ")
    x = data.iloc[:, -1]
    columns = data.columns.tolist()

    plt.figure(figure_title)
    plt.xlabel("Subtitle generation duration (s)")
    plt.ylabel("Hardware usage (%)")

    cores_mean_usage_list = []
    cores_number = len(columns)-2
    for i in range(len(data.iloc[:, 1])):
        cores_mean_usage = 0
        for j in range(cores_number):
            cores_mean_usage += data.iloc[i, j]
        cores_mean_usage = cores_mean_usage/cores_number
        cores_mean_usage_list += [cores_mean_usage]
    plt.plot(x, cores_mean_usage_list, label="Cores_mean_usage")
    plt.plot(x, data.iloc[:, -2], label="Memory_usage")
    plt.title(figure_title)
    plt.legend()
    plt.savefig(subtitle_generation_hardware_stats_file_path + ".png")


def start_timer(url, filename, duration, download_status, subtitle_generation_progress_queue):
    start_time = time.time()
    running = True
    download_status[url] = {
        "filename": filename,
        "status": "Native Subtitle Generation"
    }

    subtitle_generation_hardware_stats_file_lines = ""
    subtitle_generation_hardware_stats_folder = "subtitle_generation_hardware_stats"
    os.makedirs(subtitle_generation_hardware_stats_folder, exist_ok=True)
    os.chmod(subtitle_generation_hardware_stats_folder, 0o755)
    subtitle_generation_hardware_stats_file_path = subtitle_generation_hardware_stats_folder + "/" + str(round(duration)) + " - " + filename + " - Hardware usage" 
    cores_number = psutil.cpu_count()
    for i in range(cores_number):
        subtitle_generation_hardware_stats_file_lines += "Core_" + str(i+1) + "_usage_percent "
    subtitle_generation_hardware_stats_file_lines += "Memory_usage_percent Subtitle_generation_duration\n"
    def show_elapsed_time(download_status, duration, queue, subtitle_generation_hardware_stats_file_path, subtitle_generation_hardware_stats_file_lines):
        while running:
            progression_percentage = round((((time.time() - start_time) / duration) * 100), 1)
            if progression_percentage < 100:

                download_status[url]["percent"] = str(progression_percentage)+"%"
            else:
                download_status[url]["percent"] = "100%"
            subtitle_generation_progress_queue.put(download_status[url])

            cores_usage_list = psutil.cpu_percent(interval=1, percpu=True)
            mem_usage = psutil.virtual_memory().percent
            for core_usage in cores_usage_list:
                subtitle_generation_hardware_stats_file_lines += str(core_usage) + " "
            subtitle_generation_hardware_stats_file_lines += str(mem_usage) + " " + str(time.time() - start_time) + "\n"
            with open(subtitle_generation_hardware_stats_file_path, "w", encoding="utf-8") as subtitle_generation_hardware_stats_file:
                subtitle_generation_hardware_stats_file.writelines(subtitle_generation_hardware_stats_file_lines)
            time.sleep(1)

    timer_thread = threading.Thread(target=show_elapsed_time, args=(download_status, duration, subtitle_generation_progress_queue, subtitle_generation_hardware_stats_file_path, subtitle_generation_hardware_stats_file_lines))
    timer_thread.daemon = True
    timer_thread.start()

    def stop():
        nonlocal running  # Permet de modifier la variable `running` définie dans la fonction parente
        running = False
    
    return (subtitle_generation_hardware_stats_file_path, stop)


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
def subtitle_generation(download_type, whisper_model, download_status, url, video_title, input_file, subtitle_generation_progress_queue, native_language_queue, cancel_download):
    if download_type == "video":
        subtitle_generation_duration_name = "video_subtitle_generation_duration.txt"
    elif download_type== "music":
        subtitle_generation_duration_name = "music_subtitle_generation_duration.txt"

    subtitle_generation_duration_filename = os.path.dirname(os.path.abspath(__file__)) + "/" + subtitle_generation_duration_name
    video_duration = get_media_duration(input_file)
    lines = []
    header = "date reel_generation_time estimated_generation_time"
    if os.path.exists(subtitle_generation_duration_filename):
        with open(subtitle_generation_duration_filename, "r", encoding="utf-8") as subtitle_generation_duration_file:
            lines = subtitle_generation_duration_file.readlines()

        subtitle_generation_stats = []
        for line in lines[1:]:
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
        lines += [header + "\n"]
        estimated_generation_time = 1000

    (subtitle_generation_hardware_stats_file_path, stop_timer) = start_timer(url, video_title, estimated_generation_time, download_status, subtitle_generation_progress_queue)
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
        lines = [header + "\n"] + lines[len(lines) - max_lines + 2:]
    
    reel_generation_time = fonction_end_timestamp - fonction_begin_timestamp
    lines += [f"{date} {video_duration} {reel_generation_time} {estimated_generation_time}\n"] 

    with open(subtitle_generation_duration_filename, "w", encoding="utf-8") as subtitle_generation_duration_file:
        subtitle_generation_duration_file.writelines(lines)

    native_language_queue.put((language, output_file))

    hardware_stats_graph_generation(subtitle_generation_hardware_stats_file_path)


def translate_subtitles(download_status, url, title, input_subtitle_language, input_file, translate_language_label, translate_language_code, output_file, cancel_download):
    with open(input_file, "r", encoding="utf-8") as input_subtitle_file:
        lines = input_subtitle_file.readlines()
        subtitle_original_file_length = len(lines)

    translated_lines = []
    for i in range(len(lines)):
        if (not cancel_download.is_set()):
            line = lines[i]
            download_status[url] = {
                "filename": title,
                "percent": str(round(i/subtitle_original_file_length*100, 1)) + "%",
                "status": "Subtitle Translation to " + translate_language_label
            }
            if line.strip().isdigit() or "-->" in line or line.strip() == "":
                translated_lines.append(line)
            else:
                try:
                    translated = GoogleTranslator(source=input_subtitle_language, target=translate_language_code).translate(line)
                except:
                    translated = line
                if translated == None:
                    translated_lines.append("\n")
                else:
                    translated_lines.append(translated + "\n")

    if (not cancel_download.is_set()):
        with open(output_file, "w", encoding="utf-8") as output_subtitle_file:
            output_subtitle_file.writelines(translated_lines)
            

def all_subtitle_generation(download_type, whisper_model, download_status, url, title, video_path, subtitle_languages_list, cancel_download):
    if ("Native" in subtitle_languages_list) and (not cancel_download.is_set()):
        del subtitle_languages_list["Native"]
        with lock:
            subtitle_generation_progress_queue = multiprocessing.Queue()
            native_language_queue = multiprocessing.Queue()
            Subtitle_Generation_Process = multiprocessing.Process(target=subtitle_generation, args=(download_type, whisper_model, download_status, url, title, video_path, subtitle_generation_progress_queue, native_language_queue, cancel_download))
            Subtitle_Generation_Process.start()
            cancel_download_dict[url].update({"Multiprocess_Data": {"Subtitle_Generation_Process": Subtitle_Generation_Process, "subtitle_generation_progress_queue": subtitle_generation_progress_queue, "native_language_queue": native_language_queue}})
            Subtitle_Generation_Process.join()
            if ("Multiprocess_Data" in cancel_download_dict[url]):
                (native_language, native_language_subtitle_file) = native_language_queue.get()
                del cancel_download_dict[url]["Multiprocess_Data"]
                subtitle_generation_progress_queue.close()
                native_language_queue.close()
            else:
                native_language = None
                native_language_subtitle_file = None
        for translate_language_label, translate_language_code in subtitle_languages_list.items():
            if (translate_language_code != native_language) and (not cancel_download.is_set()):
                translate_subtitle_file = native_language_subtitle_file[:-7] + "_" + translate_language_code + ".srt"
                translate_subtitles(download_status, url, title, native_language, native_language_subtitle_file, translate_language_label, translate_language_code, translate_subtitle_file, cancel_download)


def merge_media_file_and_subtitles(video_path, subtitle_files_list, download_type, output_path):
    if (video_path[-3:] == "mkv") or (video_path[-3:] == "m4a"):
        command = ["ffmpeg"]

        map_index = 0

        if download_type == "music":
            command += ["-f", "lavfi", "-i", "color=black:s=1280x720"]
            map_index += 1
        
        command += ["-i", video_path]

        for k in range(len(subtitle_files_list)):
            command += ["-i", subtitle_files_list[k]]

        command += ["-map", "0:v"]
        command += ["-map", str(map_index) + ":a"]

        for i in range(len(subtitle_files_list)):
            map_index += 1
            command += ["-map", str(map_index) + ":0"]

        if download_type == "music":
            command += ["-c:v", "libx264", "-tune", "stillimage", "-shortest"]
        elif download_type == "video":
            command += ["-c:v", "copy"]

        command += [
            "-c:a", "copy",
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


def download_media_file_with_subtitles(whisper_model, download_status, url, title, download_type, download_path, subtitle_generation, subtitle_languages_list, cancel_download):
    download_media_function_choice={
        "download_video": download_video,
        "download_music": download_music
    }
    
    if download_type == "video":
        download_media_function_name = "download_video"
        media_file_extension = "mkv"
    elif download_type == "music":
        download_media_function_name = "download_music"
        media_file_extension = "m4a"

    if not cancel_download.is_set():
        if not os.path.isfile(download_path + title + "." + media_file_extension):
            if subtitle_generation and (subtitle_languages_list != {}):
                normalize_title = string_normalisation(title)
                subtile_build_directory = download_path + normalize_title + "/"
                os.makedirs(subtile_build_directory , exist_ok=True)
                download_media_function_choice[download_media_function_name](url, title, download_status, subtile_build_directory, cancel_download)
                
                downloaded_file = "None"
                listdir = os.listdir(subtile_build_directory)
                if (len(listdir)):
                    downloaded_file = subtile_build_directory + listdir[0]

                all_subtitle_generation(download_type, whisper_model, download_status, url, title, downloaded_file, subtitle_languages_list, cancel_download)
                output_video_path = download_path + title + ".mkv"
                subtitle_files_list = [str(path) for path in Path(subtile_build_directory).glob("*.srt")]
                merge_media_file_and_subtitles(downloaded_file, subtitle_files_list, download_type, output_video_path)
                shutil.rmtree(subtile_build_directory, ignore_errors=True)
            else:
                download_media_function_choice[download_media_function_name](url, title, download_status, download_path, cancel_download)
        else:
            download_status[url] = {
                "filename": title,
                "status": "Already Downloaded"
            }
            time.sleep(2)


def download_setup(whisper_model, whisper_size_model, download_status, url, title, download_type, download_path, subtitle_generation, subtitle_languages_list, cancel_download):
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

    download_media_file_with_subtitles(whisper_model, download_status, url, title, download_type, download_path, subtitle_generation, subtitle_languages_list, cancel_download)

    download_status[url] = {
        "filename": title,
        "status": "END"
    }


class StreamTee:
    last_message_timestamp = 0

    def __init__(self, *streams):
        self.streams = streams  # Stock toutes les sorties souhaitees

    def write(self, message):
        if message.strip() and message.strip()[-23:-18] != "12482":
            message_timestamp = time.time()
            if message_timestamp - StreamTee.last_message_timestamp > 1:
                date = str(datetime.date.today())
                hour = datetime.datetime.fromtimestamp(message_timestamp)
                formated_hour = hour.strftime("%H:%M:%S") + "," + str(hour.microsecond)[0:3]
                message = "\n" + date + " " + formated_hour + " " + message
                StreamTee.last_message_timestamp = message_timestamp
            
        for stream in  self.streams:  # Ecrit le message dans toutes les sorties
            if isinstance(stream, str):
                with open(stream, "a", encoding="utf-8") as logfile:

                    logfile.write(message)
            else:
                stream.write(message)
                stream.flush()

    def flush(self):
        for stream in self.streams:
            if not isinstance(stream, str):
                stream.flush()

server_folder_path = os.path.dirname(os.path.abspath(__file__))
logging_path_file = server_folder_path + "/server.log"

# Les messages renvoyer par le scripts sont inscris dans la console et le fichier log
sys.stdout = StreamTee(sys.__stdout__, logging_path_file)
sys.stderr = StreamTee(sys.__stderr__, logging_path_file)


app = Flask(__name__)
CORS(app)

logging_level = logging.WARNING
if os.path.exists(logging_path_file):
    with open(logging_path_file, 'a', encoding='utf-8') as logfile:
        logfile.write("\n\n\n")

# Configurer le logger Werkzeug pour afficher les messages du serveur dans la console
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.setLevel(logging_level)
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
werkzeug_logger.addHandler(console_handler)



@app.route("/", methods=["POST"])
def server_request_treatment():
    client_request = request.get_json()
    purpose = client_request.get("purpose")

    if purpose == "check_download_status_initialization":
        return jsonify(download_status)
    elif purpose == "check_download_status":
        url = client_request["video_url"]
        if ("Multiprocess_Data" in cancel_download_dict[url]):
            subtitle_response_queue = cancel_download_dict[url]["Multiprocess_Data"]["subtitle_generation_progress_queue"].get()
            if (isinstance(subtitle_response_queue, dict)):
                download_status[url] = subtitle_response_queue
        return jsonify(download_status[url])
    elif purpose == "clear_downloaded_video_data":
        url = client_request["video_url"]
        del download_status[url]
        del cancel_download_dict[url]
        return("Download Data Cleared")
    elif purpose == "cancel_download":
        url = client_request["video_url"]
        cancel_download_dict[url]["cancel_download"].set()
        if ("Multiprocess_Data" in cancel_download_dict[url]):
            Multiprocess = cancel_download_dict[url]["Multiprocess_Data"]
            del cancel_download_dict[url]["Multiprocess_Data"]
            Multiprocess["subtitle_generation_progress_queue"].close()
            Multiprocess["native_language_queue"].close()
            Multiprocess["Subtitle_Generation_Process"].terminate()
        return("Download File Canceled")
    else:
        url = client_request["url"]
        title = client_request["title"]
        download_type = client_request["download_type"]
        download_path = client_request["download_path"]
        subtitle_generation = client_request["subtitle_generation"]
        subtitle_languages_list = client_request["subtitle_languages_list"]

        if url not in download_status:
            download_status[url] = {"filename": title, "status": "Initialisation..."}
            cancel_download = threading.Event()
            cancel_download_dict[url] = {"cancel_download" : cancel_download}
            thread = threading.Thread(target=download_setup, args=(whisper_model, whisper_size_model, download_status, url, title, download_type, download_path, subtitle_generation, subtitle_languages_list, cancel_download))
            thread.start()
            return ("Download Launched")
        else:
            return("This file is already downloading")


print('Serveur en écoute. Port : ' + str(PORT), flush=True)
app.run(host="0.0.0.0", port=PORT, threaded=True)

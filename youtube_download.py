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

    download_status = {
        "filename": filename
    }
    if d['status'] == 'downloading':
        download_status["percent"] = d['_percent_str']
        download_status["remaining_time"] = d['_eta_str']

        download_status = json.dumps(download_status)
        print(download_status, flush=True)


def download_video(url, title, download_path):
    ydl_opts = {
        'noprogress': True,
        'progress_hooks': [my_hook],
	    'format_sort': ['res:1080', 'ext:mkv'],
	    'outtmpl': download_path + title + '.%(ext)s',
        'merge_output_format': 'mkv',
        'ignoreerrors': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def download_music(url, title, download_path):
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a',
        }],
        'noprogress': True,
        'progress_hooks': [my_hook],
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


def start_timer(filename, duration):
    start_time = time.time()
    running = True
    download_status = {
        "filename": filename,
        "status": "Subtitle Generation"
    }

    def show_elapsed_time(download_status, duration):
        while running:
            progression_percentage = round((((time.time() - start_time) / duration) * 100), 1)
            if progression_percentage < 100:

                download_status["percent"] = str(progression_percentage)+"%"
                print(json.dumps(download_status), flush=True)
            else:
                download_status["percent"] = "100%"
                print(json.dumps(download_status), flush=True)
            time.sleep(1)

    timer_thread = threading.Thread(target=show_elapsed_time, args=(download_status, duration))
    timer_thread.daemon = True
    timer_thread.start()

    def stop():
        nonlocal running  # Permet de modifier la variable `running` définie dans la fonction parente
        running = False
    
    return stop


def get_video_duration(video_file):
    probe = ffmpeg.probe(video_file)
    video_duration = float(probe['format']['duration'])
    return video_duration


# Convertir temps au format hh:mm:ss,ms
def timestamp_to_srt_time_format_conversion(timestamp):
    hour = int(timestamp // 3600)
    minute = int((timestamp % 3600) // 60)
    second = int(timestamp % 60)
    millisecond = int((timestamp - int(timestamp)) * 1000)
    return f"{hour:02}:{minute:02}:{second:02},{millisecond:03}"


# Sauvegarder en format SRT
def subtitle_generation(video_title, input_file):
    subtitle_generation_duration_filename = os.path.dirname(os.path.abspath(__file__)) + "/subtitle_generation_duration.txt"
    video_duration = get_video_duration(input_file)
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

    stop_timer = start_timer(video_title, estimated_generation_time)
    date = time.strftime("%Y-%m-%d")
    fonction_begin_timestamp = time.time()

    transcript = whisper_model.transcribe(
        input_file,
        task="transcribe",         # Pour transcription (et non traduction)
        fp16=False                 # À desactiver si pas de GPU compatible
    )
    language = transcript.get("language", "unknown")
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


def translate_subtitles(title, input_subtitle_language, input_file, output_file):
    download_status = {
        "filename": title,
        "status": "Subtitle Translation"
    }

    if input_subtitle_language != 'fr':
        with open(input_file, "r", encoding="utf-8") as subtitle_original_file:
            subtitle_original_file_length = len(subtitle_original_file.readlines())

        with open(input_file, "r", encoding="utf-8") as input_subtitle_file:
            lines = input_subtitle_file.readlines()

        translated_lines = []
        for i in range(len(lines)):
            line = lines[i]
            download_status["percent"] = str(round(i/subtitle_original_file_length*100, 1)) + "%"
            print(json.dumps(download_status), flush=True)
            if line.strip().isdigit() or "-->" in line or line.strip() == "":
                translated_lines.append(line)
            else:
                translated = GoogleTranslator(source=input_subtitle_language, target='fr').translate(line)
                translated_lines.append(translated + "\n")

        with open(output_file, "w", encoding="utf-8") as output_subtitle_file:
            output_subtitle_file.writelines(translated_lines)


def all_subtitle_generation(url, title, video_path):
    (origin_language, origin_language_subtitle_file) = subtitle_generation(title, video_path)
    french_subtitle_file = origin_language_subtitle_file[:-6] + "_fr.srt"
    translate_subtitles(title, origin_language, origin_language_subtitle_file, french_subtitle_file)


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


if __name__ == "__main__":
    #GENERATION DE SOUS TITRES 
    whisper_model = whisper.load_model("tiny")

    url = sys.argv[1]
    title = sys.argv[2]
    download_type = sys.argv[3]
    download_path = sys.argv[4].replace("\\", "/")
    if download_path[-1] != "/":
        download_path += "/"

    parent = psutil.Process().parent().parent()
    shell_name = parent.name().lower()
    if shell_name == "powershell.exe":
        if download_path[0:7] == "/mnt/c/":
            download_path = "C:/" + download_path[7:]
    elif shell_name == "bash" or shell_name == "tmux: server":
        if download_path[0:3] == "C:/":
            download_path = "/mnt/c/" + download_path[3:]


    if download_type == "video":
        normalize_title = string_normalisation(title)
        subtile_build_directory = download_path + normalize_title + "/"
        os.makedirs(subtile_build_directory , exist_ok=True)
        download_video(url, title, subtile_build_directory)
        downloaded_file = subtile_build_directory + os.listdir(subtile_build_directory)[0]
        all_subtitle_generation(url, title, downloaded_file)
        output_video_path = download_path + title + ".mkv"
        subtitle_files_list = [str(path) for path in Path(subtile_build_directory).glob("*.srt")]
        merge_video_and_subtitles(downloaded_file, subtitle_files_list, output_video_path)
        shutil.rmtree(subtile_build_directory, ignore_errors=True)

    elif download_type == "music":
        download_music(url, title, download_path)
 
    download_status = {
        "filename": title,
        "status": "END"
    }
    download_status = json.dumps(download_status)
    print(download_status, flush=True)
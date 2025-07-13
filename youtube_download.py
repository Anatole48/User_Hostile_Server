import yt_dlp
import sys
import json
import psutil
import os

url = sys.argv[1]
download_type = sys.argv[2]
download_path = sys.argv[3].replace("\\", "/")
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


def my_hook(d):
    default_filename = d['filename'].replace("\\", "/").split("/")[-1]
    filename_list = default_filename.split(".")
    filename = ""
    if "format_id" in d.get("info_dict", {}) and filename_list[-2]=='f'+d['info_dict']['format_id'] :
        del(filename_list[-2])
        for i in range(len(filename_list)-1):
            filename += filename_list[i] + "."
        filename += filename_list[len(filename_list)-1]
    else :
        filename = default_filename

    download_status = {
        "status": d['status'],
        "filename": filename
    }
    if d['status'] == 'downloading':
        download_status["progress"] = {
            "percent": d['_percent_str'],
            "speed": d['_speed_str'],
            "remaining_time": d['_eta_str']
        }

    if filename_list[-1]!='vtt':
        download_status = json.dumps(download_status)
        print(download_status, flush=True)


def download_video(url, download_path):
    ydl_opts = {
        'noprogress': True,
        'progress_hooks': [my_hook],
	    'format_sort': ['res:1080', 'ext:mkv'],
	    'outtmpl': download_path + '%(title)s.%(ext)s',
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['en', 'fr'],
        'postprocessors': [
            {'key': 'FFmpegEmbedSubtitle'}
        ]
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def download_music(url, download_path):
    ydl_opts = {
        'format': 'm4a/bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
        }],
        'noprogress': True,
        'progress_hooks': [my_hook],
	    'outtmpl': download_path + '%(title)s.%(ext)s'
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


if download_type == "video":
    download_video(url, download_path)
elif download_type == "music":
    download_music(url, download_path)
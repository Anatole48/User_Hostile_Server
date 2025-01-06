import yt_dlp
import sys
import json

url = sys.argv[1]

video_download_path = "/mnt/c/Users/anato/Videos/NOOOOO/"
music_download_path = "/mnt/c/Users/anato/Music/"

def my_hook(d):
    filename = d['filename'].split("/")[-1]
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
    download_status = json.dumps(download_status)
    print(download_status, flush=True)


def download_video(url):
    #browser = "chrome"
    ydl_opts = {
        'noprogress': True,
        'progress_hooks': [my_hook],
	'format_sort': ['res:1080', 'ext:mp4:m4a'],
	'outtmpl': video_download_path + '%(title)s.%(ext)s',
	#'cookiesfrombrowser': browser,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def download_music(url):
    ydl_opts = {
	'format': 'm4a/bestaudio/best',
        'postprocessors': [{  # Extract audio using ffmpeg
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a',
	}],
        'noprogress': True,
        'progress_hooks': [my_hook],
	'outtmpl': music_download_path + '%(title)s.%(ext)s'
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    """
    ydl_opts = {
        'format': 'm4a/bestaudio/best',
        'postprocessors': [{  # Extract audio using ffmpeg
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a',
        }]
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    """

if sys.argv[2] == "video":
    download_video(url)
elif sys.argv[2]=="music":
    download_music(url)
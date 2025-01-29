var express = require('express');
const { spawn, spawnSync } = require('child_process');

const app = express();
const PORT = 2000;

downloads_list = {}

app.use(express.json());

app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content, Accept, Content-Type, Authorization');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, PATCH, OPTIONS');
  next();
});

app.post('/', (req,res,next) => {
    url = req.body.video_url
    if (req.body.purpose == "check_download_status"){
        res.json(downloads_list[url])
    } else if (req.body.purpose == "clear_downloaded_video_data"){
	delete downloads_list[url]
	res.end()
    } else {
        download_type = req.body.download_type
        download_path = req.body.download_path
        video_download(url, download_type, download_path, downloads_list)
	res.send("download_launched")
    }
})

app.listen(PORT, '0.0.0.0', () => {
  console.log('Serveur en écoute. Port : ' + PORT.toString() );
});

module.exports = app;


const video_download = (url, download_type, download_path, downloads_list) => {
    downloads_list[url] = {
        "status": "Initialisation"
    }

    let is_python3_installed = spawnSync('python3', ['--version']).status
    let is_python_installed = spawnSync('python', ['--version']).status
    let python_to_use = ""
    if (is_python3_installed === 0) {
        python_to_use = "python3"
    } else if (is_python_installed === 0) {
        python_to_use = "python"
    }
    const video_download_process = spawn(python_to_use, ['Youtube_Download.py', url, download_type, download_path]);
    video_download_process.stdout.on('data', (data) => {
        data = data.toString()
        try {
            data = JSON.parse(data)
            downloads_list[url] = data
        } catch {
            let response = data.trim()
            if (response.substr(-27,27) == "has already been downloaded"){
            downloads_list[url] = {
                "status": "finished"
            }
            console.log("VIDEO ALREADY DOWNLOADED")
            } else if ((response.substr(0,6) != "[info]") && (response.substr(0,9) != "[youtube]") && (response.substr(0,10) != "[download]") && (response.substr(0,8) != "[Merger]") && (response.substr(0,11) != "[hlsnative]") && (response.substr(0,8) != "Deleting")){
            console.log("JSON PARSE ERROR CATCH")
            console.log(response)
            }
        }
    });

    video_download_process.stderr.on('data', (data) => {
        console.error(`Erreur du script Python : ${data.toString()}`);
    });
}
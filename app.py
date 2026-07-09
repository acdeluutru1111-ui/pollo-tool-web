"""Pollo Tool — Flask mobile-first web app for Pollo AI API"""
import os, json, uuid, hashlib, random, tempfile, time, threading, logging, sys
import requests as http_req
from flask import Flask, render_template, request, jsonify, send_file

# ═══════════════ LOGGING ═══════════════
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("pollo")

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB

# ═══════════════ UPLOAD ═══════════════
def upload_file(path, token):
    if not path or path.startswith("http"):
        return path
    fname = os.path.basename(path)
    ext = os.path.splitext(fname)[1].lower()
    mm = {".jpg":"image/jpeg",".jpeg":"image/jpeg",".png":"image/png",".gif":"image/gif",
          ".webp":"image/webp",".mp4":"video/mp4",".mov":"video/quicktime",".webm":"video/webm",
          ".mp3":"audio/mpeg",".wav":"audio/wav",".m4a":"audio/mp4"}
    mime = mm.get(ext, "application/octet-stream")
    sz = os.path.getsize(path)
    h = {"Content-Type":"application/json",
         "Cookie":f"__Secure-next-auth.callback-url=https%3A%2F%2Fpollo.ai;__Secure-next-auth.session-token={token}"}
    r = http_req.post("https://pollo.ai/api/upload/sign",
                      json={"filename":fname,"filetype":mime,"filesize":sz,
                            "type":"video" if mime.startswith("video/") else ("audio" if mime.startswith("audio/") else "image")},
                      headers=h, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Sign failed {r.status_code}")
    d = r.json()
    signed, access = d.get("sign"), d.get("accessURL")
    if not signed or not access:
        raise RuntimeError(f"Sign error: {r.text[:200]}")
    with open(path, "rb") as f:
        pr = http_req.put(signed, data=f, headers={"Content-Type":mime}, timeout=180)
    if pr.status_code not in (200,201):
        raise RuntimeError(f"PUT failed {pr.status_code}")
    return access


# ═══════════════ API ═══════════════
class PolloAPI:
    BASE = "https://api-mobile.pollo.ai/api/v1"
    DEVS = [{"m":"SM-G991B","v":"13","d":"QP1A.190711.020"},{"m":"SM-S908B","v":"14","d":"UP1A.231005.007"},
            {"m":"Pixel 7","v":"14","d":"AP2A.240805.005"},{"m":"23122PCD1G","v":"10","d":"TKQ1.221114.001"},
            {"m":"SM-G996B","v":"12","d":"SP1A.210812.016"},{"m":"SM-F916B","v":"13","d":"QP1A.190711.020"}]

    def __init__(self, token):
        self._t = token

    def _h(self):
        d = random.choice(self.DEVS)
        return {"user-agent":"android","deviceid":d["d"],"appversion":"3.5.2","accept-encoding":"gzip",
                "content-type":"application/json","time-zone":"+08:00","idfa":"",
                "cookie":f"__Secure-next-auth.callback-url=https%3A%2F%2Fapi-mobile.pollo.ai;__Secure-next-auth.session-token={self._t};",
                "devicesystemversion":d["v"],"idfv":"","host":"api-mobile.pollo.ai",
                "googleadid":str(uuid.uuid4()),"adid":hashlib.md5(str(uuid.uuid4()).encode()).hexdigest(),
                "amazonadid":"","devicemodel":d["m"],"user-language":"en"}

    def up(self, p):
        return upload_file(p, self._t)

    def _post(self, ep, body):
        url = f"{self.BASE}/{ep}"
        headers = self._h()
        logger.info(f"POST {url}")
        logger.debug(f"Headers: {json.dumps(headers, indent=2)}")
        logger.debug(f"Body: {json.dumps(body, indent=2)[:2000]}")
        try:
            r = http_req.post(url, headers=headers, json=body, verify=False, timeout=120)
            logger.info(f"Response {r.status_code}")
            logger.debug(f"Response body: {r.text[:1000]}")
            if r.status_code != 200:
                logger.error(f"HTTP ERROR {r.status_code}: {r.text[:500]}")
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
            d = r.json()
            if not d.get("id"):
                logger.error(f"No id in response: {json.dumps(d)[:300]}")
                raise RuntimeError(f"No id: {json.dumps(d)[:300]}")
            logger.info(f"Task created: id={d['id']}")
            return d
        except http_req.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise

    def text2img(self, prompt, model, aspect, res, n, q):
        return self._post("generation/enhanced-text2image", {
            "generationConfig":{"prompt":prompt,"aspectRatio":aspect,"resolution":res,"numOutputs":n,
                               "published":True,"protectionMode":False,"modelName":model,"outputQuality":q,"outputFormat":"png"},
            "published":True,"protectionMode":False,"enableMagicPrompt":False,"enableTranslatePrompt":True,
            "entryCode":"TextToImage","numOutputs":1.0,
            "createFlowId":"yp17ml8fipv7ym8z5nf9ochrl","createFlowFormId":"yazf6bhh1l2yg2r37ujrogg3a"})

    def img2img(self, prompt, model, aspect, res, urls):
        return self._post("generation/enhanced-image2image", {
            "generationConfig":{"prompt":prompt,"imageUrl":urls[0] if urls else "","images":urls,
                               "aspectRatio":aspect,"resolution":res,"numOutputs":1,
                               "published":True,"protectionMode":False,"modelName":model,"outputQuality":100,"outputFormat":"png"},
            "published":True,"protectionMode":False,"enableMagicPrompt":False,"enableTranslatePrompt":True,
            "entryCode":"ImageToImage","numOutputs":1.0,"createFlowId":"","createFlowFormId":""})

    def img2vid(self, url, prompt, model, length, aspect, audio):
        return self._post("generation/enhanced-image2video", {
            "generationConfig":{"image":url,"prompt":prompt,"generateAudio":audio,"length":length,
                               "aspectRatio":aspect,"resolution":"720p","numOutputs":1,
                               "published":True,"protectionMode":False,"modelName":model},
            "published":True,"protectionMode":False,"enableMagicPrompt":False,"enableTranslatePrompt":True,
            "entryCode":"ImageToVideo","numOutputs":1.0,
            "createFlowId":"asqun81275pifecbek3xs88xb","createFlowFormId":"k9r05qcgqrd6ejuxhbhh7ccls"})

    def ref2vid(self, refs, prompt, model, dur, aspect, res, audio, seed=None, audio_url=None):
        g = {"prompt":prompt,"duration":dur,"aspectRatio":aspect,"resolution":res,"generateAudio":audio,
             "numOutputs":1,"published":True,"protectionMode":False,"videoModel":model,
             "configType":"ref2video-v2","refs":refs}
        if seed is not None:
            g["seed"] = int(seed)
        if audio_url:
            g["audioUrl"] = audio_url
        return self._post("generation/ref2video", {
            "generationConfig":g,"published":True,"protectionMode":False,
            "enableMagicPrompt":False,"enableTranslatePrompt":True,
            "entryCode":"RefToVideo","numOutputs":1.0,"addAudioAuto":False,
            "createFlowId":"od3bwqcxwx4vud6x5gon1t3j8","createFlowFormId":"bz9g0yen9oxlwlatqgu0vbehr"})

    def mimic(self, img, vid, prompt, model, mode):
        return self._post("generation/actionImitation", {
            "generationConfig":{"imageUrl":img,"video":{"src":vid,"cover":"","metadata":{"width":1080,"height":1890,"duration":12}},
                               "modelName":model,"mode":mode,"prompt":prompt},
            "published":True,"protectionMode":False})

    def poll(self, tid):
        r = http_req.post(f"{self.BASE}/generation/records", headers=self._h(), json={"id":int(tid)}, verify=False, timeout=30)
        if r.status_code != 200:
            return {"status":"error","error":f"HTTP {r.status_code}"}
        d = r.json()
        rec = d.get("data", d) if isinstance(d, dict) else d
        if isinstance(rec, list) and rec:
            rec = rec[0]
        st = rec.get("status", "unknown")
        out = None
        if st in ("completed", "success"):
            o = rec.get("output", rec.get("data", {}))
            urls = []
            if isinstance(o, str):
                urls = [o]
            elif isinstance(o, dict):
                for k in ["url","urls","video","image","imageUrl","videoUrl"]:
                    if k in o:
                        v = o[k]
                        urls.extend(v if isinstance(v, list) else [v])
            elif isinstance(o, list):
                urls = o
            out = urls
        return {"status":st, "progress":rec.get("progress",0), "output":out}


# ═══════════════ TASK STORAGE ═══════════════
tasks = {}
UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "pollo_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _poll_task(api, task_id):
    for i in range(120):
        time.sleep(7)
        r = api.poll(task_id)
        if r["status"] in ("completed", "success"):
            tasks[task_id] = {"status":"completed","output":r.get("output",[]),"progress":1.0}
            return
        if r["status"] in ("failed", "error"):
            tasks[task_id] = {"status":"failed","error":r.get("error","Unknown"),"progress":0}
            return
        tasks[task_id] = {"status":"processing","progress":min(r.get("progress", i/120), 0.99)}
    tasks[task_id] = {"status":"failed","error":"Timeout after 14 minutes"}


def _get_fp(f):
    return f if isinstance(f, str) else (f.name if hasattr(f, "name") else str(f))


# ═══════════════ ROUTES ═══════════════
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return jsonify({"error":"No file"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error":"Empty filename"}), 400
    ext = os.path.splitext(f.filename)[1]
    fname = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_DIR, fname)
    f.save(path)
    return jsonify({"path":path, "name":f.filename})


@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.json
    token = data.get("token","")
    mode = data.get("mode","")
    logger.info(f"Generate request: mode={mode}")
    logger.debug(f"Request data: {json.dumps(data, indent=2)[:1000]}")

    if not token:
        logger.warning("No token provided")
        return jsonify({"error":"Token required"}), 400

    try:
        api = PolloAPI(token)

        if mode == "text2img":
            logger.info(f"text2img: prompt={data['prompt'][:50]}... model={data['model']}")
            d = api.text2img(data["prompt"], data["model"], data["aspect"], data["resolution"],
                             int(data.get("numOutputs",1)), int(data.get("quality",100)))
        elif mode == "img2img":
            logger.info(f"img2img: files={len(data.get('files',[]))}")
            urls = [api.up(p) for p in data.get("files",[])]
            d = api.img2img(data["prompt"], data["model"], data["aspect"], data["resolution"], urls)
        elif mode == "img2vid":
            logger.info(f"img2vid: file={data['file']}")
            d = api.img2vid(api.up(data["file"]), data["prompt"], data["model"],
                           int(data.get("length",4)), data["aspect"], data.get("audio",True))
        elif mode == "ref2vid":
            logger.info(f"ref2vid: images={len(data.get('images',[]))} videos={len(data.get('videos',[]))}")
            refs, order = [], 1
            for p in data.get("images",[]):
                refs.append({"type":"image","name":f"Image {order}","image":api.up(p),"order":order})
                order += 1
            for p in data.get("videos",[]):
                refs.append({"type":"video","name":f"Video {order}","video":api.up(p),"order":order})
                order += 1
            prompt = data["prompt"]
            for r in refs:
                n = r["order"]
                if r["type"]=="image":
                    prompt = prompt.replace(f"@Image {n}",f"[image{n}]").replace(f"Image {n}",f"[image{n}]")
                else:
                    prompt = prompt.replace(f"@Video {n}",f"[video{n}]").replace(f"Video {n}",f"[video{n}]")
            sv = int(data["seed"]) if data.get("seed") and str(data["seed"]).strip() else None
            d = api.ref2vid(refs, prompt, data["model"], int(data.get("duration",4)),
                           data["aspect"], data.get("resolution","480p"), data.get("audio",False), sv)
        elif mode == "mimic":
            logger.info(f"mimic: image={data['image']} video={data['video']}")
            d = api.mimic(api.up(data["image"]), api.up(data["video"]),
                         data["prompt"], data["model"], data["mode_param"])
        else:
            logger.error(f"Unknown mode: {mode}")
            return jsonify({"error":f"Unknown mode: {mode}"}), 400

        task_id = str(d["id"])
        tasks[task_id] = {"status":"processing","progress":0}
        logger.info(f"Starting poll thread for task {task_id}")
        t = threading.Thread(target=_poll_task, args=(api, task_id), daemon=True)
        t.start()
        return jsonify({"task_id":task_id})

    except Exception as e:
        logger.exception(f"Generate failed: {e}")
        return jsonify({"error":str(e)}), 500


@app.route("/api/status/<task_id>")
def api_status(task_id):
    t = tasks.get(task_id)
    if not t:
        return jsonify({"error":"Task not found"}), 404
    return jsonify(t)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    logger.info(f"Starting Pollo Tool on port {port}")
    app.run(host="0.0.0.0", port=port, debug=True)

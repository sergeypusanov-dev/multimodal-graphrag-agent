import base64, hashlib, subprocess
from pathlib import Path
from llm.adapter import vision_llm, batch_llm

def process_text_file(file_path: str, config: dict) -> dict:
    suffix = Path(file_path).suffix.lower()
    if suffix == ".pdf":
        import fitz
        doc  = fitz.open(file_path)
        text = "\n\n".join(p.get_text() for p in doc)
    elif suffix == ".docx":
        from docx import Document
        doc  = Document(file_path)
        text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    else:
        text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    return {"content":text,"media_type":"text","doc_date":_extract_doc_date(text)}

def process_image_file(file_path: str, config: dict) -> dict:
    with open(file_path,"rb") as f:
        img_data = base64.standard_b64encode(f.read()).decode()
    ext_map = {".jpg":"image/jpeg",".jpeg":"image/jpeg",".png":"image/png",
               ".gif":"image/gif",".webp":"image/webp"}
    mt = ext_map.get(Path(file_path).suffix.lower(),"image/jpeg")
    response = vision_llm.chat_with_vision(
        text="Describe for knowledge graph: entities, relationships, visible text, approximate date.",
        images_b64=[img_data])
    return {"content":response.text,"media_type":"image",
            "raw_image_data":img_data,"image_media_type":mt,"doc_date":None}

def process_audio_file(file_path: str, config: dict) -> dict:
    provider = config.get("media_processing", {}).get("transcription_provider", "local")
    if provider == "openai":
        return _transcribe_openai(file_path)
    else:
        return _transcribe_local(file_path, config)

def _transcribe_openai(file_path: str) -> dict:
    from openai import OpenAI
    oai = OpenAI()
    with open(file_path,"rb") as f:
        transcript = oai.audio.transcriptions.create(
            model="whisper-1",file=f,response_format="verbose_json",
            timestamp_granularities=["segment"])
    segments = [{"start":s.start,"end":s.end,"text":s.text}
                for s in (transcript.segments or [])]
    return {"content":transcript.text,"media_type":"audio","segments":segments,"doc_date":None}

def _transcribe_local(file_path: str, config: dict) -> dict:
    from faster_whisper import WhisperModel
    model_size = config.get("media_processing", {}).get("whisper_model", "base")
    device = config.get("media_processing", {}).get("whisper_device", "cpu")
    compute_type = "int8" if device == "cpu" else "float16"
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    result_segments, info = model.transcribe(file_path, beam_size=5, language=None)
    segments = []
    texts = []
    for seg in result_segments:
        segments.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})
        texts.append(seg.text.strip())
    return {"content": " ".join(texts), "media_type": "audio",
            "segments": segments, "doc_date": None}

def process_video_file(file_path: str, config: dict) -> dict:
    import cv2, os
    fps_target = config["media_processing"]["video_frames_per_minute"] / 60
    max_frames = config["media_processing"]["video_max_frames"]
    audio_path = str(Path(file_path).with_suffix("")) + "_audio.mp3"
    subprocess.run(["ffmpeg","-i",file_path,"-q:a","0","-map","a",audio_path,"-y"],capture_output=True)
    audio_result = (process_audio_file(audio_path,config)
                    if Path(audio_path).exists() else {"content":"","segments":[]})
    try: os.unlink(audio_path)
    except: pass
    cap  = cv2.VideoCapture(file_path)
    fps  = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1,int(fps/max(fps_target,0.001)))
    frames_data, frame_idx = [], 0
    while cap.isOpened() and len(frames_data) < max_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES,frame_idx)
        ret,frame = cap.read()
        if not ret: break
        _,buf = cv2.imencode(".jpg",frame)
        frames_data.append({"frame_number":frame_idx,"timestamp_ms":int(frame_idx/fps*1000),
                             "image_data":base64.standard_b64encode(buf).decode()})
        frame_idx += step
    cap.release()
    described = []
    for fr in frames_data:
        r = batch_llm.chat_with_vision("Briefly describe entities and actions.",
                                       [fr["image_data"]])
        described.append({**fr,"description":r.text})
    combined = audio_result["content"]+"\n\n"+\
               "\n".join(f"[{f['timestamp_ms']//1000}s] {f['description']}" for f in described)
    return {"content":combined,"media_type":"video",
            "segments":audio_result.get("segments",[]),"frames":described,"doc_date":None}

def process_file(file_path: str, config: dict) -> dict:
    suffix = Path(file_path).suffix.lower()
    if suffix in [".jpg",".jpeg",".png",".gif",".webp",".bmp"]:
        return process_image_file(file_path,config)
    elif suffix in [".mp3",".wav",".m4a",".ogg",".flac",".aac"]:
        return process_audio_file(file_path,config)
    elif suffix in [".mp4",".avi",".mov",".mkv",".webm",".m4v"]:
        return process_video_file(file_path,config)
    else:
        return process_text_file(file_path,config)

def _extract_doc_date(text: str):
    import re
    for p in [r'\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b',r'\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b']:
        m = re.search(p,text)
        if m: return m.group(0)
    return None

def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda: f.read(8192),b""): h.update(chunk)
    return h.hexdigest()

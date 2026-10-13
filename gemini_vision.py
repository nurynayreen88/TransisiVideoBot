"""Optional minimal Gemini image description; never embeds credentials or fabricates claims."""
import asyncio
import base64
import json
import logging
import os
import urllib.request

def _describe(data: bytes):
    key=os.environ.get('GEMINI_API_KEY','').strip()
    if not key or not data or len(data)>8_000_000: return None
    model=os.environ.get('GEMINI_VISION_MODEL','gemini-2.5-flash')
    if not all(x.isalnum() or x in '.-_' for x in model): return None
    body={'contents':[{'parts':[
      {'text':(
          'Inspect the uploaded product photograph carefully. Return concise Malay plain text with EXACTLY these lines: '
          'NAMA_PRODUK: [exact visible printed product name, including brand/model ONLY if fully legible; otherwise TIDAK PASTI]; '
          'KATEGORI: [specific visible product type or TIDAK PASTI]; '
          'TEKS_DISAHKAN: [verbatim legible words/specifications from packaging, separated by semicolons; otherwise TIADA]; '
          'CIRI_VISUAL: [2-4 specific directly observable physical attributes, colors, shapes, components; otherwise TIADA]; '
          'CIRI_BERTULIS: [only product claims/specifications explicitly legible in the image, preserving original wording; otherwise TIADA]; '
          'KETIDAKPASTIAN: [any unclear or cut-off lettering, otherwise TIADA]. '
          'Never guess missing letters, brand, model, ingredients, capacity, benefits, claims, prices, or unseen details. '
          'Distinguish printed packaging claims from independently observable facts. '
          'Do not paraphrase a printed name or translate brand/model. No marketing slogans. '
          'If text is blurry or partial, write TIDAK PASTI rather than reconstructing it.'
      )},
      {'inline_data':{'mime_type':'image/jpeg','data':base64.b64encode(data).decode('ascii')}}
    ]}],'generationConfig':{'temperature':0.1,'maxOutputTokens':420}}
    req=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent',
        data=json.dumps(body).encode(),headers={'Content-Type':'application/json','x-goog-api-key':key},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=18) as res: result=json.load(res)
        parts=result.get('candidates',[{}])[0].get('content',{}).get('parts',[])
        description=' '.join(p.get('text','') for p in parts).strip()
        return description[:1800] or None
    except Exception:
        logging.exception('Optional Gemini vision unavailable; use reference-only prompt')
        return None

async def describe_photo(data: bytes):
    return await asyncio.to_thread(_describe,data)

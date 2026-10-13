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
      {'text':('Describe only directly visible product properties in this photo, in concise Malay, maximum 65 words. '
               'Include product category, visible colors, shape, visible materials only if unambiguous, visible logo/text only if legible. '
               'Do not guess brand, unseen features, benefits, ingredients, prices or specifications. '
               'If unclear say tidak dapat dipastikan. Return plain text.')},
      {'inline_data':{'mime_type':'image/jpeg','data':base64.b64encode(data).decode('ascii')}}
    ]}],'generationConfig':{'temperature':0.1,'maxOutputTokens':180}}
    req=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent',
        data=json.dumps(body).encode(),headers={'Content-Type':'application/json','x-goog-api-key':key},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=18) as res: result=json.load(res)
        parts=result.get('candidates',[{}])[0].get('content',{}).get('parts',[])
        description=' '.join(p.get('text','') for p in parts).strip()
        return description[:700] or None
    except Exception:
        logging.exception('Optional Gemini vision unavailable; use reference-only prompt')
        return None

async def describe_photo(data: bytes):
    return await asyncio.to_thread(_describe,data)

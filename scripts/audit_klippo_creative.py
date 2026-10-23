import json,re,collections,statistics
from pathlib import Path
root=Path("prompts"); master=json.loads((root/"subcategory_variation_library.json").read_text(encoding="utf-8"))
files=sorted((root/"staging_batch100_20261023").glob("part_*.json"))
records=[(f"master:{c['subcategory_id']}",v) for c in master["subcategories"] for v in c["variations"]]
for p in files:
 d=json.loads(p.read_text(encoding="utf-8"))
 records.extend((p.name,v) for v in d["variations"])
fields=("hook","action","detail","camera","lighting","closing","audio")
def norm(s):return re.sub(r"\\s+"," ",re.sub(r"[^a-z0-9]+"," ",str(s).lower())).strip()
def creative(s):return re.sub(r"^(?:0.?2s|2.?6s|6.?8s|8.?10s|hook|action|detail|cta|hero)\\s*:?\\s*","",norm(s))
lengths=[]; long=[]; groups=collections.defaultdict(list); family=collections.defaultdict(list); missing=[]; timing=[]; percat=collections.Counter()
for source,v in records:
 ident=v.get("id",""); cat=ident.rsplit("_v",1)[0];percat[cat]+=1
 missing.extend((ident,k) for k in fields if not str(v.get(k,"")).strip())
 txt=" ".join(str(v.get(k,"")) for k in fields); words=len(txt.split());lengths.append(words)
 if words>110:long.append({"id":ident,"words":words,"source":source})
 groups[(cat,creative(v.get("hook","")),creative(v.get("action","")),creative(v.get("closing","")))].append(ident)
 family[(cat,creative(v.get("action","")),creative(v.get("detail","")))].append(ident)
 if not all(re.search(p,str(v.get(k,"")),re.I) for k,p in (("hook",r"0\s*[–-]\s*2s"),("action",r"2\s*[–-]\s*6s"),("detail",r"6\s*[–-]\s*8s"),("closing",r"8\s*[–-]\s*10s"))):timing.append(ident)
 report={"records":len(records),"categories":len(percat),"word_count":{"min":min(lengths),"median":statistics.median(lengths),"mean":round(statistics.mean(lengths),1),"p90":sorted(lengths)[int(.9*(len(lengths)-1))],"max":max(lengths)},"over_110_words":len(long),"longest":sorted(long,key=lambda x:-x["words"])[:25],"missing_fields":missing[:30],"missing_fields_count":len(missing),"missing_explicit_timing_count":len(timing),"missing_explicit_timing_examples":timing[:30],"same_hook_action_closing_groups":sum(len(x)>1 for x in groups.values()),"same_hook_action_closing_examples":[x[:8] for x in groups.values() if len(x)>1][:25],"same_action_detail_groups":sum(len(x)>1 for x in family.values()),"same_action_detail_examples":[x[:8] for x in family.values() if len(x)>1][:25],"categories_below_50":{k:v for k,v in percat.items() if v<50}}
Path("klippo_creative_audit_report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
print("CREATIVE_AUDIT_JSON="+json.dumps(report,ensure_ascii=False))

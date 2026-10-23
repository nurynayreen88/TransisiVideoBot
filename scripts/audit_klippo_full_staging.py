import json,re,collections,hashlib
from pathlib import Path
root=Path("prompts"); master=json.loads((root/"subcategory_variation_library.json").read_text(encoding="utf-8"))
cats=master["subcategories"]; order=[x["subcategory_id"] for x in cats]; required=("id","variation_number","name","hook","action","detail","camera","lighting","closing","audio")
files=sorted((root/"staging_batch100_20261023").glob("part_*.json"),key=lambda p:int(re.search(r"part_(\d+)",p.name).group(1)))
errors=[]; warnings=[]; seen={}; nums=collections.defaultdict(list); bodies=collections.defaultdict(list); records=[]
def check(r,source):
 if not isinstance(r,dict): errors.append([source,"not object"]);return
 for k in required:
  if k not in r or not isinstance(r[k],(str,int)) or (isinstance(r[k],str) and not r[k].strip()):errors.append([source,"missing/empty",k])
 ident=r.get("id","")
 if ident in seen:errors.append([source,"duplicate ID",ident,seen[ident]])
 else:seen[ident]=source
 match=re.fullmatch(r"(.+)_v(\d+)",str(ident))
 if not match or match.group(1) not in order or r.get("variation_number")!=int(match.group(2)):errors.append([source,"ID/number/category mismatch",ident])
 else:nums[match.group(1)].append((int(match.group(2)),source))
 body=tuple(str(r.get(k,"")).strip().casefold() for k in required[3:])
 bodies[body].append(source)
 records.append((source,r))
for c in cats:
 for i,r in enumerate(c["variations"]):check(r,f"master:{c['subcategory_id']}:{i}")
if len(cats)!=130:errors.append(["master","subcategory count",len(cats)])
if len(files)!=165:errors.append(["staging","file count",len(files)])
for n,p in enumerate(files,1):
 part=int(re.search(r"part_(\d+)",p.name).group(1))
 if part!=n:errors.append([p.name,"part gap",n])
 try:d=json.loads(p.read_text(encoding="utf-8"))
 except Exception as e:errors.append([p.name,"invalid JSON",str(e)]);continue
 vs=d.get("variations",[])
 if not isinstance(vs,list) or len(vs)!=20 or d.get("variation_count")!=20 or d.get("part")!=part:errors.append([p.name,"part metadata/count",len(vs) if isinstance(vs,list) else None])
 if isinstance(vs,list):
  for i,r in enumerate(vs):check(r,f"{p.name}:{i+1}")
for cat,items in nums.items():
 arr=sorted(n for n,_ in items)
 if len(arr)!=len(set(arr)):errors.append([cat,"duplicate number"])
 for a,b in zip(arr,arr[1:]):
  if b!=a+1:errors.append([cat,"number gap",a,b])
for body,sources in bodies.items():
 if len(sources)>1:warnings.append(["identical seven prompt fields",sources])
for source,r in records:
 text=" ".join(str(r.get(k,"")) for k in required[3:]).casefold()
 if len(set(str(r.get(k,"")).strip().casefold() for k in required[3:]))<5:warnings.append(["low field diversity",source])
summary={"master":sum(len(c["variations"]) for c in cats),"staging_files":len(files),"staging_records":len(records)-sum(len(c["variations"]) for c in cats),"unique_ids":len(seen),"errors":errors,"warnings":warnings}
Path("klippo_audit_report.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")
print(json.dumps({"master":summary["master"],"staging_files":len(files),"staging_records":summary["staging_records"],"unique_ids":len(seen),"errors_count":len(errors),"warnings_count":len(warnings),"errors":errors[:120],"warnings":warnings[:100]},ensure_ascii=False))

# Coverage audit: count distinct variations in master + all staging by subcategory.
coverage=[{"subcategory_id":cat,"count":len(nums[cat]),"shortfall":max(0,50-len(nums[cat]))} for cat in order]
print("COVERAGE_50_JSON="+json.dumps({"categories":len(coverage),"ready":sum(x["count"]>=50 for x in coverage),"below_50":[x for x in coverage if x["count"]<50],"total_shortfall":sum(x["shortfall"] for x in coverage),"distribution":coverage},ensure_ascii=False))
if errors or warnings:raise SystemExit(1)

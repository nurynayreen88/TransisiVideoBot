"""Deterministic six-shot storyboard planner; no paid API or fabricated product claims."""
TIMINGS={10:[1.5,1.5,2,2,1.5,1.5],15:[2,2.5,3,3,2.5,2],20:[3,3,4,4,3,3]}
SHOTS=[
("HOOK","Macro / punch-in","Zoom masuk pantas dan terkawal"),
("PENGENALAN","Produk penuh","Pan lembut kiri ke tengah"),
("KONTEKS","Pembungkusan jika ada; jika tiada guna gambar produk","Zoom keluar perlahan"),
("DETAIL","Perincian yang benar-benar kelihatan","Crop dekat dan pan"),
("HERO SHOT","Produk sebagai fokus utama","Simulasi orbit 2D / parallax ringan; bukan putaran 3D sebenar"),
("PENUTUP","Paparan produk bersih","Zoom keluar dan fade"),
]
def build_storyboard(image_count:int,duration:int=15):
    if image_count<1 or image_count>5: raise ValueError("Perlu 1 hingga 5 gambar")
    if duration not in TIMINGS: raise ValueError("Durasi mesti 10, 15 atau 20 saat")
    elapsed=0.0; scenes=[]
    for i,((purpose,shot,motion),seconds) in enumerate(zip(SHOTS,TIMINGS[duration])):
        # Cycle supplied images; never invent an unseen viewpoint.
        source=(i%image_count)+1
        scenes.append(dict(scene=i+1,purpose=purpose,start_seconds=elapsed,
                           end_seconds=elapsed+seconds,source_image_index=source,
                           shot=shot,motion=motion,transition_out="fade" if i<5 else "none"))
        elapsed+=seconds
    return dict(title="Storyboard Produk",format="9:16",duration_seconds=duration,
                scenes=scenes,notes="Pergerakan kamera digital pada gambar asal; tidak menjana sudut produk baharu.")
def format_storyboard(plan):
    lines=[f"🎬 STORYBOARD • {plan['duration_seconds']} SAAT • 9:16",
           "Enam babak daripada gambar yang dihantar:"]
    for s in plan["scenes"]:
        lines.append(f"\n{s['scene']}. {s['purpose']} ({s['start_seconds']:g}–{s['end_seconds']:g}s)\n"
                     f"Gambar {s['source_image_index']} • {s['shot']}\n{s['motion']}")
    lines.append("\nNota: Orbit ialah simulasi 2D, bukan 360° sebenar. Tiada dakwaan produk atau teks direka.")
    return "\n".join(lines)
def source_sequence(plan):
    return [s["source_image_index"]-1 for s in plan["scenes"]]

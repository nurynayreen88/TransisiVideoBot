            product = ('the product in the uploaded reference image. Visible observations (verify against reference image): ' + context.user_data.get('prompt_vision', '') + '. Optional user details: ' + context.user_data.get('prompt_product', ''))
            scene = context.user_data.get('prompt_scene', 'clean studio background')
            prompt = build_prompt(context.user_data.get('prompt_mode', 'normal'), product, scene, motion)
            context.user_data['stage'] = 'prompt_done'
            await query.message.reply_text('✅ PROMPT SIAP — gunakan bersama gambar produk. Semak ketepatan pemerhatian AI Vision jika tersedia.')
            # A single text attachment is the authoritative, complete copyable prompt.
            mode_name = 'storyboard' if context.user_data.get('prompt_mode') == 'storyboard' else 'biasa'
            prompt_file = BytesIO(prompt.encode('utf-8'))
            prompt_file.name = f'KLIPPO_prompt_{mode_name}.txt'
            await query.message.reply_document(
                document=prompt_file,
                filename=prompt_file.name,
                caption='📋 PROMPT PENUH — buka fail .txt ini, kemudian Select All → Copy. Semua arahan ada dalam satu fail.'
            )
            if mode_name == 'storyboard':
                await query.message.reply_text(
                    '🎬 Storyboard panjang: untuk salin SEMUA babak sekali gus, gunakan fail .txt di atas. '
                    'Di bawah ialah paparan mengikut bahagian supaya mudah dibaca atau disalin satu demi satu.'
                )
                # Split at actual shot headings instead of arbitrary character counts.
                sections = re.split(r'(?=\\b0[1-6] \\| (?:HOOK|REVEAL|CONTEXT|DETAIL|HERO|CLOSING) \\|)', prompt)
            else:
                sections = [prompt]
            for section in sections:
                remaining = section.strip()
                while remaining:
                    if len(remaining) <= 3000:
                        chunk, remaining = remaining, ''
                    else:
                        split_at = remaining.rfind('\\n\\n', 0, 3000)
                        if split_at < 1000:
                            split_at = remaining.rfind('\\n', 0, 3000)
                        if split_at < 1000:
                            split_at = 3000
                        chunk, remaining = remaining[:split_at], remaining[split_at:].lstrip('\\n')
                    await query.message.reply_text(
                        '<pre>' + html.escape(chunk) + '</pre>', parse_mode='HTML'
                    )
            await query.message.reply_text('Pilih tindakan seterusnya:', reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('🤖 Buka NexaBot', url='https://t.me/aigeneratornexa_bot?start=ref37141287'), InlineKeyboardButton('✨ Buka Gemini', url='https://gemini.google.com/')],
                [InlineKeyboardButton('✍️ Prompt Baharu', callback_data='prompt'), InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]
            ]))

    elif action == 'merge':
        reset(context)
        context.user_data['stage'] = 'merge_upload'
        context.user_data['merge_files'] = []
        await query.message.reply_text('🎞️ Hantar Video 1 sebagai fail MP4.\n\nTekan 📎 → File / Fail → pilih video dan hantar.\n\nMaksimum 5 video (19 MB dan 20 saat setiap klip).', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('✅ Selesai', callback_data='merge_done')], [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    elif action == 'merge_next':
        if stage not in ('merge_wait_next', 'merge_upload'):
            await query.message.reply_text('Sila mulakan Gabung Video dahulu.')
            return
        context.user_data['stage'] = 'merge_upload'
        await query.message.reply_text(f"📤 Hantar Video {len(context.user_data.get('merge_files', [])) + 1} sebagai File / Document.")
    elif action == 'merge_done':
        if stage not in ('merge_upload', 'merge_wait_next') or len(context.user_data.get('merge_files', [])) < 2:
            await query.message.reply_text('Hantar sekurang-kurangnya 2 video dahulu.')
            return
        context.user_data['stage'] = 'merge_style'
        await query.message.reply_text('Pilih transisi:', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('✨ Fade', callback_data='merge_style:fade'), InlineKeyboardButton('🌊 Smooth', callback_data='merge_style:smoothleft')], [InlineKeyboardButton('⚡ Slide', callback_data='merge_style:slideleft'), InlineKeyboardButton('🔍 Zoom', callback_data='merge_style:zoomin')]]))
    elif action.startswith('merge_style:') and stage == 'merge_style':
        await generate_merge(update, context, action.split(':', 1)[1])
    elif action == 'convert':
        reset(context)
        context.user_data['stage'] = 'convert'
        await query.message.reply_text('🔄 TUKAR FORMAT VIDEO UNTUK AFFILIATE\n\nUntuk kualiti terbaik:\n1. Tekan ikon 📎 di ruang mesej.\n2. Pilih File / Fail (bukan Gallery / Video).\n3. Pilih video MP4 asal dan hantar.\n\nBot akan menukar format secara automatik dan menghantar hasil sebagai fail MP4.\n\nNota: Telegram mungkin memampatkan video yang dihantar melalui Gallery / Video.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    elif action == 'photos_order' and stage in ('photos', 'duration'):
        ids = context.user_data.get('photos', [])
        if not ids:
            await query.message.reply_text('Belum ada gambar. Sila hantar gambar dahulu.', reply_markup=photos_menu())
        else:
            for index, file_id in enumerate(ids, 1):
                await query.message.reply_photo(photo=file_id, caption=f'Gambar {index}')
            await query.message.reply_text('📋 Susunan semasa. Gunakan ⬆️ ⬇️ atau ❌ untuk menyusun:', reply_markup=order_menu(len(ids)))
    elif action == 'photos_undo' and stage == 'photos':
        ids = context.user_data.get('photos', [])
        if ids:
            ids.pop()
        await query.message.reply_text(f'Gambar terakhir dibuang. Baki: {len(ids)}.', reply_markup=photos_menu())
    elif action.startswith(('photo_up:', 'photo_down:', 'photo_remove:')) and stage in ('photos', 'duration'):
        ids = context.user_data.get('photos', [])
        action_type, index_text = action.split(':', 1)
        index = int(index_text)
        if index >= len(ids):
            await query.message.reply_text('Susunan telah berubah. Semak semula.', reply_markup=order_menu(len(ids)))
        else:
            if action_type == 'photo_remove':
                ids.pop(index)
            elif action_type == 'photo_up' and index > 0:
                ids[index-1], ids[index] = ids[index], ids[index-1]
            elif action_type == 'photo_down' and index < len(ids)-1:
                ids[index+1], ids[index] = ids[index], ids[index+1]
            await query.message.reply_text(f'📋 Susunan dikemas kini. {len(ids)} gambar.', reply_markup=order_menu(len(ids)) if ids else photos_menu())
    elif action == 'photos_more' and stage in ('photos', 'duration'):
        context.user_data['stage'] = 'photos'
        await query.message.reply_text('📤 Hantar gambar seterusnya.', reply_markup=photos_menu())
    elif action.startswith('duration:') and stage == 'duration':
        duration = int(action.split(':', 1)[1])
        if duration in (10, 15, 20):
            context.user_data['duration'] = duration
            context.user_data['stage'] = 'style'
            await query.message.reply_text(f'⏱️ {duration} saat dipilih. Pilih gaya:', reply_markup=style_menu())
    elif action == 'photos_done':
        if stage not in ('photos', 'duration') or not context.user_data.get('photos'):
            await query.message.reply_text('Hantar sekurang-kurangnya satu gambar dahulu.', reply_markup=photos_menu())
            return
        context.user_data['stage'] = 'duration'
        await query.message.reply_text('⏱️ Pilih durasi video:', reply_markup=duration_menu())
    elif action == 'styles' and stage in ('style', 'music', 'confirm'):
        context.user_data['stage'] = 'style'
        await query.message.reply_text('Langkah 2/4 — Pilih gaya:', reply_markup=style_menu())
    elif action.startswith('preview:') and stage == 'style':
        chosen = action.split(':', 1)[1]
        if chosen not in STYLES:
            return
        lock = context.application.bot_data.setdefault('render_lock', asyncio.Lock())
        if lock.locked():
            await query.message.reply_text('Server sedang sibuk. Cuba preview sebentar lagi.')
            return
        async with lock:
            context.user_data['busy'] = True
            try:
                with tempfile.TemporaryDirectory(prefix='preview_') as td:
                    folder = Path(td)
                    paths = []
                    for i, fid in enumerate(context.user_data['photos'][:2]):
                        path = folder / f'{i}.jpg'
                        await (await context.bot.get_file(fid)).download_to_drive(path)
                        paths.append(path)
                    video = folder / 'preview.mp4'
                    await asyncio.to_thread(render_video, paths, video, None, chosen)
                    with video.open('rb') as handle:
                        await query.message.reply_video(video=handle, caption=f'▶️ Contoh {chosen}. Pilih gaya di bawah.', reply_markup=style_menu(), supports_streaming=True)
            except Exception:
                logging.exception('Style preview failed')
                await query.message.reply_text('Preview gagal. Sila pilih gaya atau cuba semula.', reply_markup=style_menu())
            finally:
                context.user_data['busy'] = False
    elif action.startswith('style:') and stage == 'style':
        context.user_data['style'] = action.split(':', 1)[1]
        if context.user_data.get('storyboard_mode'):
            context.user_data['stage'] = 'doodle'
            await query.message.reply_text('Pilih efek garisan / doodle untuk prompt storyboard:', reply_markup=doodle_menu())
        else:
            context.user_data['stage'] = 'music'
            await query.message.reply_text(f"✅ Gaya {context.user_data['style']} dipilih.\\nLangkah 3/4 — Pilih muzik:", reply_markup=music_menu())
    elif action.startswith('doodle:') and stage == 'doodle' and context.user_data.get('storyboard_mode'):
        choice = action.split(':', 1)[1]
        if choice in DOODLE_OPTIONS:
            context.user_data['doodle_choice'] = choice
            context.user_data['stage'] = 'music'
            await query.message.reply_text('✅ Efek untuk storyboard: '+DOODLE_OPTIONS[choice]+'\\nEfek pilihan akan dimasukkan ke dalam MP4.\\nPilih muzik:', reply_markup=music_menu())
    elif action == 'music' and stage in ('music', 'confirm'):
        context.user_data['stage'] = 'music'
        await query.message.reply_text('Langkah 3/4 — Pilih muzik:', reply_markup=music_menu())
    elif action == 'music_previews' and stage == 'music':
        await query.message.reply_text('Tekan untuk mendengar contoh muzik:', reply_markup=music_preview_menu())
    elif action.startswith('listen:') and stage == 'music':
        name = action.split(':', 1)[1]
        if name in MUSIC_CHOICES and name not in ('auto', 'none', 'custom'):
            path = resolve_music(name, context.user_data.get('style', 'hybrid'))
            if path:
                with path.open('rb') as handle:
                    await query.message.reply_audio(audio=handle, title=name.title(), reply_markup=music_preview_menu())
            else:
                await query.message.reply_text('Fail muzik belum tersedia pada server.')
    elif action.startswith('music:') and stage == 'music':
        choice = action.split(':', 1)[1]
        if choice in MUSIC_CHOICES:
            context.user_data['music_choice'] = choice
            if choice != 'custom':
                context.user_data['music'] = None
            context.user_data['stage'] = 'confirm'
            await query.message.reply_text(('Hantar MP3 sendiri, kemudian tekan Hasilkan Video.' if choice == 'custom' else f'✅ Muzik {choice} dipilih.\nLangkah 4/4 — Semak dan hasilkan.'), reply_markup=confirm_menu())
    elif action == 'confirm' and stage == 'confirm':
        await generate(update, context)
    elif action == 'subscription':
        await query.message.reply_text('💎 LANGGANAN KLIPPO\n\nRM5 / 30 hari\nSehingga 30 video sebulan.\n\nBayar melalui QR DuitNow. Selepas pembayaran, upload resit untuk semakan admin.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📱 Papar QR DuitNow', callback_data='subscription_qr')], [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    elif action == 'subscription_qr':
        qr_path = Path(__file__).resolve().parent / 'klippo_qr.jpg'
        if not qr_path.is_file():
            await query.message.reply_text('QR pembayaran belum tersedia. Sila cuba lagi kemudian.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
        else:
            with qr_path.open('rb') as qr_file:
                await query.message.reply_photo(photo=qr_file, caption='💎 KLIPPO — DuitNow QR\n\nPelan Penyokong Awal: RM5 / 30 hari (sehingga 30 video sebulan).\n\nTekan 📎 Upload Resit selepas pembayaran. Pengaktifan adalah manual selepas semakan.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📎 Upload Resit', callback_data='receipt_upload')], [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    elif action == 'receipt_upload':
        context.user_data['stage'] = 'receipt_upload'
        await query.message.reply_text('📎 Sila hantar gambar atau fail PDF resit pembayaran di sini.')
    elif action == 'account':
        await account_info(update, context)
    elif action == 'help':
        await query.message.reply_text('❓ CARA GUNA\n\n1. Tekan Jana Video.\n2. Hantar 1–5 gambar, kemudian tekan Selesai.\n3. Lihat contoh dan pilih gaya.\n4. Dengar contoh dan pilih muzik.\n5. Tekan Hasilkan Video.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    elif action == 'check':
        await status(update, context)
    elif action == 'reset':
        await start(update, context)
    elif action == 'home':
        await start(update, context)
    else:
        await query.message.reply_text('Pilihan lama telah tamat. Mulakan semula melalui menu utama.', reply_markup=main_menu())


async def menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stage = context.user_data.get('stage')
    value = update.message.text.strip()
    if value == '🏠 Menu Utama':
        await start(update, context)
        return
    shortcuts = {
        '🎬 Jana Video Affiliate': 'make',
        '🎬 Jana Video Transisi': 'make',
        '🔄 Tukar Format Video': 'convert',
        '✍️ Sediakan Prompt Video': 'prompt',
        '✍️ Hasilkan Prompt': 'prompt',
        '💎 Langganan': 'subscription',
        '👤 Akaun Saya': 'account',
        '❓ Bantuan': 'help',
        '🗑 Mula Semula': 'home',
    }
    if value in shortcuts:
        action = shortcuts[value]
        if action == 'make':
            reset(context)
            context.user_data['stage'] = 'photos'
            await update.message.reply_text('Langkah 1/4 — Hantar 1–5 gambar produk. Tekan Selesai apabila cukup.', reply_markup=photos_menu())
        elif action == 'convert':
            reset(context)
            context.user_data['stage'] = 'convert'
            await update.message.reply_text('🔄 TUKAR FORMAT VIDEO\n\nTekan 📎 → File / Fail → pilih video MP4 asal. Bot akan memprosesnya secara automatik.', reply_markup=main_menu())
        elif action == 'prompt':
            reset(context)
            context.user_data['stage'] = 'prompt_type'
            await update.message.reply_text('✍️ HASILKAN PROMPT — Pilih jenis:', reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('✨ Prompt Biasa', callback_data='prompt_type:normal')],
                [InlineKeyboardButton('🎞️ Prompt Storyboard (6 Babak)', callback_data='prompt_type:storyboard')],
                [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
            ]))
        elif action == 'subscription':
            await update.message.reply_text('💎 LANGGANAN KLIPPO\n\nPelan Penyokong Awal: RM5 / 30 hari, sehingga 30 video sebulan. Pengaktifan manual selepas resit disemak.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📱 Papar QR DuitNow', callback_data='subscription_qr')]]))
        elif action == 'account':
            await account_info(update, context)
        elif action == 'help':
            await update.message.reply_text('❓ BANTUAN\n\nJana Video: hantar gambar, pilih gaya dan muzik.\nTukar Format: hantar MP4.\nVideo AI: upload gambar, tambah maklumat jika mahu, kemudian pilih latar dan gerakan kamera. Prompt digunakan bersama gambar di penjana video luar.')
        else:
            await start(update, context)
        return
    if stage == 'prompt_details_text':
        context.user_data['prompt_product'] = value[:600]
        context.user_data['stage'] = 'prompt_scene'
        await update.message.reply_text('Maklumat tambahan disimpan. Pilih latar atau taip Auto:')
    elif stage == 'prompt_scene':
        if len(value) < 5 and value.lower() != 'auto':
            await update.message.reply_text('Nyatakan latar ringkas atau taip Auto.')
            return
        context.user_data['prompt_scene'] = 'clean premium studio background' if value.lower() == 'auto' else value[:400]
        context.user_data['stage'] = 'prompt_motion'
        await update.message.reply_text('Langkah 2/2: Pilih gerakan kamera:', reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('🔄 Orbit Terkawal', callback_data='motion:orbit')],
            [InlineKeyboardButton('🔍 Zoom Masuk', callback_data='motion:push')],
            [InlineKeyboardButton('↔️ Gerak Sisi', callback_data='motion:side')],
            [InlineKeyboardButton('✨ Studio Statik', callback_data='motion:static')],
        ]))
    else:
        await update.message.reply_text('Gunakan butang menu di bawah.', reply_markup=main_menu())


async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    ids = context.user_data.get('photos', [])
    if not ids:
        await message.reply_text('Hantar gambar dahulu.', reply_markup=main_menu())
        return
    if context.user_data.get('busy'):
        await message.reply_text('Video sedang diproses.')
        return
    lock = context.application.bot_data.setdefault('render_lock', asyncio.Lock())
    if lock.locked():
        await message.reply_text('Server sedang menjana video lain. Cuba sebentar lagi.')
        return
    await lock.acquire()
    context.user_data['busy'] = True
    await message.reply_text('⏳ Menjana video, sila tunggu...')
    try:
        with tempfile.TemporaryDirectory(prefix='telegram_video_') as td:
            folder = Path(td)
            paths = []
            for i, fid in enumerate(list(ids)):
                p = folder / f'{i}.jpg'
                await (await context.bot.get_file(fid)).download_to_drive(p)
                paths.append(p)
            music = None
            if context.user_data.get('music_choice') == 'custom' and context.user_data.get('music'):
                music = folder / 'music.mp3'
                await (await context.bot.get_file(context.user_data['music'])).download_to_drive(music)
            elif context.user_data.get('music_choice') == 'custom':
                await message.reply_text('Sila hantar MP3 sendiri dahulu, atau pilih muzik lain.', reply_markup=music_menu())
                return
            elif context.user_data.get('music_choice', 'auto') != 'none':
                music = resolve_music(context.user_data.get('music_choice', 'auto'), context.user_data.get('style', 'hybrid'))
                if music is None:
                    await message.reply_text('Muzik pilihan belum tersedia pada server. Video akan dijana tanpa muzik.')
            result = folder / 'video.mp4'
            if context.user_data.get('storyboard_mode'):
                plan = build_storyboard(len(paths), context.user_data.get('duration', 10))
                await message.reply_text(format_storyboard(plan) + '\n\nEfek prompt: ' + DOODLE_OPTIONS[context.user_data.get('doodle_choice', 'none')] + '\nArahan AI: Tambah efek pilihan secara halus di luar label dan logo produk. Jangan ubah identiti produk. (Efek overlay turut dirender pada MP4.)')
                paths = [paths[i] for i in source_sequence(plan)]
                selected_style = 'cinematic'
                doodle = context.user_data.get('doodle_choice', 'none')
            else:
                selected_style = context.user_data.get('style', 'hybrid')
                doodle = 'none'
            await asyncio.to_thread(render_video, paths, result, music, selected_style, context.user_data.get('duration', 10), doodle)
            with result.open('rb') as f:
                await message.reply_video(video=f, caption='🎬 Video siap! Hantar gambar baharu untuk video seterusnya.', supports_streaming=True,
                                                 read_timeout=120, write_timeout=120)
        reset(context)
        await message.reply_text('Mahu buat video lagi? Hantar gambar baharu.', reply_markup=main_menu())
    except Exception:
        logging.exception('Video generation failed')
        await message.reply_text('❌ Gagal menjana video. Cuba kurangkan gambar atau semak log FFmpeg.')
    finally:
        context.user_data['busy'] = False
        lock.release()


def main():
    if not TOKEN:
        raise RuntimeError('BOT_TOKEN belum ditetapkan')
    if not shutil.which('ffmpeg'):
        raise RuntimeError('FFmpeg belum dipasang')
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('admin', admin))
    app.add_handler(CommandHandler('reset', start))
    app.add_handler(CommandHandler('periksa', status))
    app.add_handler(CommandHandler('jana', generate, block=False))
    for style in STYLES:
        app.add_handler(CommandHandler(style, choose_style))
    app.add_handler(CallbackQueryHandler(buttons, pattern=r'^(photos_order|photos_undo|photos_more|photo_up:[0-4]|photo_down:[0-4]|photo_remove:[0-4]|duration:(10|15|20)|admin_pending|admin_approve:[0-9]+|admin_reject:[0-9]+|admin|receipt_upload|subscription_qr|make|storyboard|doodle:(auto|white|sparkle|motion|all|none)|convert|merge|merge_next|merge_done|merge_style:(fade|smoothleft|slideleft|zoomin)|prompt|prompt_type:(normal|storyboard)|prompt_details:(add|skip)|motion:(orbit|push|side|static)|photos_done|confirm|styles|music|music_previews|subscription|account|help|check|reset|home|preview:(hybrid|cinematic|luxury|dynamic|zoom|smooth|creative|morph)|listen:(cinematic|energetic|happy|luxury|nature|beauty)|style:(hybrid|cinematic|luxury|dynamic|zoom|smooth|creative|morph)|music:(auto|cinematic|energetic|happy|luxury|nature|beauty|none|custom))$'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_text))
    app.add_handler(MessageHandler(filters.PHOTO, photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE | filters.Document.MimeType('application/pdf'), receive_receipt))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.MimeType('video/mp4'), convert_upload))
    app.add_handler(MessageHandler(filters.AUDIO | filters.Document.MimeType('audio/mpeg'), audio))
    url = os.environ.get('WEBHOOK_URL', '').rstrip('/')
    secret = os.environ.get('WEBHOOK_SECRET', '')
    if not url.startswith('https://') or not secret:
        raise RuntimeError('WEBHOOK_URL (https) dan WEBHOOK_SECRET wajib ditetapkan')
    app.run_webhook(
        listen='0.0.0.0',
        port=int(os.environ.get('PORT', '10000')),
        url_path='telegram',
        webhook_url=url + '/telegram',
        secret_token=secret,
        drop_pending_updates=True,
    )

if __name__ == '__main__':
    main()
                product = ('the product in the uploaded reference image. Visible observations (verify against reference image): ' + context.user_data.get('prompt_vision', '') + '. Optional user details: ' + context.user_data.get('prompt_product', ''))
                scene = context.user_data.get('prompt_scene', 'clean studio background')
                prompt = build_prompt(context.user_data.get('prompt_mode', 'normal'), product, scene, motion)
                context.user_data['stage'] = 'prompt_done'
                await query.message.reply_text('✅ PROMPT SIAP — gunakan bersama gambar produk. Semak ketepatan pemerhatian AI Vision jika tersedia.')
                # A single text attachment is the authoritative, complete copyable prompt.
                mode_name = 'storyboard' if context.user_data.get('prompt_mode') == 'storyboard' else 'biasa'
                prompt_file = BytesIO(prompt.encode('utf-8'))
                prompt_file.name = f'KLIPPO_prompt_{mode_name}.txt'
                await query.message.reply_document(
                    document=prompt_file,
                    filename=prompt_file.name,
                    caption='📋 PROMPT PENUH — buka fail .txt ini, kemudian Select All → Copy. Semua arahan ada dalam satu fail.'
                )
                if mode_name == 'storyboard':
                    await query.message.reply_text(
                        '🎬 Storyboard panjang: untuk salin SEMUA babak sekali gus, gunakan fail .txt di atas. '
                        'Di bawah ialah paparan mengikut bahagian supaya mudah dibaca atau disalin satu demi satu.'
                    )
                    # Split at actual shot headings instead of arbitrary character counts.
                    sections = re.split(r'(?=\\b0[1-6] \\| (?:HOOK|REVEAL|CONTEXT|DETAIL|HERO|CLOSING) \\|)', prompt)
                else:
                    sections = [prompt]
                for section in sections:
                    remaining = section.strip()
                    while remaining:
                        if len(remaining) <= 3000:
                            chunk, remaining = remaining, ''
                        else:
                            split_at = remaining.rfind('\\n\\n', 0, 3000)
                            if split_at < 1000:
                                split_at = remaining.rfind('\\n', 0, 3000)
                            if split_at < 1000:
                                split_at = 3000
                            chunk, remaining = remaining[:split_at], remaining[split_at:].lstrip('\\n')
                        await query.message.reply_text(
                            '<pre>' + html.escape(chunk) + '</pre>', parse_mode='HTML'
                        )
                await query.message.reply_text('Pilih tindakan seterusnya:', reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('🤖 Buka NexaBot', url='https://t.me/aigeneratornexa_bot?start=ref37141287'), InlineKeyboardButton('✨ Buka Gemini', url='https://gemini.google.com/')],
                    [InlineKeyboardButton('✍️ Prompt Baharu', callback_data='prompt'), InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]
                ]))

            finally:
                if waiting is not None:
                    try:
                        await waiting.delete()
                    except Exception:
                        pass

    elif action == 'merge':
        reset(context)
        context.user_data['stage'] = 'merge_upload'
        context.user_data['merge_files'] = []
        await query.message.reply_text('🎞️ Hantar Video 1 sebagai fail MP4.\n\nTekan 📎 → File / Fail → pilih video dan hantar.\n\nMaksimum 5 video (19 MB dan 20 saat setiap klip).', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('✅ Selesai', callback_data='merge_done')], [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    elif action == 'merge_next':
        if stage not in ('merge_wait_next', 'merge_upload'):
            await query.message.reply_text('Sila mulakan Gabung Video dahulu.')
            return
        context.user_data['stage'] = 'merge_upload'
        await query.message.reply_text(f"📤 Hantar Video {len(context.user_data.get('merge_files', [])) + 1} sebagai File / Document.")
    elif action == 'merge_done':
        if stage not in ('merge_upload', 'merge_wait_next') or len(context.user_data.get('merge_files', [])) < 2:
            await query.message.reply_text('Hantar sekurang-kurangnya 2 video dahulu.')
            return
        context.user_data['stage'] = 'merge_style'
        await query.message.reply_text('Pilih transisi:', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('✨ Fade', callback_data='merge_style:fade'), InlineKeyboardButton('🌊 Smooth', callback_data='merge_style:smoothleft')], [InlineKeyboardButton('⚡ Slide', callback_data='merge_style:slideleft'), InlineKeyboardButton('🔍 Zoom', callback_data='merge_style:zoomin')]]))
    elif action.startswith('merge_style:') and stage == 'merge_style':
        await generate_merge(update, context, action.split(':', 1)[1])
    elif action == 'convert':
        reset(context)
        context.user_data['stage'] = 'convert'
        await query.message.reply_text('🔄 TUKAR FORMAT VIDEO UNTUK AFFILIATE\n\nUntuk kualiti terbaik:\n1. Tekan ikon 📎 di ruang mesej.\n2. Pilih File / Fail (bukan Gallery / Video).\n3. Pilih video MP4 asal dan hantar.\n\nBot akan menukar format secara automatik dan menghantar hasil sebagai fail MP4.\n\nNota: Telegram mungkin memampatkan video yang dihantar melalui Gallery / Video.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    elif action == 'photos_order' and stage in ('photos', 'duration'):
        ids = context.user_data.get('photos', [])
        if not ids:
            await query.message.reply_text('Belum ada gambar. Sila hantar gambar dahulu.', reply_markup=photos_menu())
        else:
            for index, file_id in enumerate(ids, 1):
                await query.message.reply_photo(photo=file_id, caption=f'Gambar {index}')
            await query.message.reply_text('📋 Susunan semasa. Gunakan ⬆️ ⬇️ atau ❌ untuk menyusun:', reply_markup=order_menu(len(ids)))
    elif action == 'photos_undo' and stage == 'photos':
        ids = context.user_data.get('photos', [])
        if ids:
            ids.pop()
        await query.message.reply_text(f'Gambar terakhir dibuang. Baki: {len(ids)}.', reply_markup=photos_menu())
    elif action.startswith(('photo_up:', 'photo_down:', 'photo_remove:')) and stage in ('photos', 'duration'):
        ids = context.user_data.get('photos', [])
        action_type, index_text = action.split(':', 1)
        index = int(index_text)
        if index >= len(ids):
            await query.message.reply_text('Susunan telah berubah. Semak semula.', reply_markup=order_menu(len(ids)))
        else:
            if action_type == 'photo_remove':
                ids.pop(index)
            elif action_type == 'photo_up' and index > 0:
                ids[index-1], ids[index] = ids[index], ids[index-1]
            elif action_type == 'photo_down' and index < len(ids)-1:
                ids[index+1], ids[index] = ids[index], ids[index+1]
            await query.message.reply_text(f'📋 Susunan dikemas kini. {len(ids)} gambar.', reply_markup=order_menu(len(ids)) if ids else photos_menu())
    elif action == 'photos_more' and stage in ('photos', 'duration'):
        context.user_data['stage'] = 'photos'
        await query.message.reply_text('📤 Hantar gambar seterusnya.', reply_markup=photos_menu())
    elif action.startswith('duration:') and stage == 'duration':
        duration = int(action.split(':', 1)[1])
        if duration in (10, 15, 20):
            context.user_data['duration'] = duration
            context.user_data['stage'] = 'style'
            await query.message.reply_text(f'⏱️ {duration} saat dipilih. Pilih gaya:', reply_markup=style_menu())
    elif action == 'photos_done':
        if stage not in ('photos', 'duration') or not context.user_data.get('photos'):
            await query.message.reply_text('Hantar sekurang-kurangnya satu gambar dahulu.', reply_markup=photos_menu())
            return
        context.user_data['stage'] = 'duration'
        await query.message.reply_text('⏱️ Pilih durasi video:', reply_markup=duration_menu())
    elif action == 'styles' and stage in ('style', 'music', 'confirm'):
        context.user_data['stage'] = 'style'
        await query.message.reply_text('Langkah 2/4 — Pilih gaya:', reply_markup=style_menu())
    elif action.startswith('preview:') and stage == 'style':
        chosen = action.split(':', 1)[1]
        if chosen not in STYLES:
            return
        lock = context.application.bot_data.setdefault('render_lock', asyncio.Lock())
        if lock.locked():
            await query.message.reply_text('Server sedang sibuk. Cuba preview sebentar lagi.')
            return
        async with lock:
            context.user_data['busy'] = True
            try:
                with tempfile.TemporaryDirectory(prefix='preview_') as td:
                    folder = Path(td)
                    paths = []
                    for i, fid in enumerate(context.user_data['photos'][:2]):
                        path = folder / f'{i}.jpg'
                        await (await context.bot.get_file(fid)).download_to_drive(path)
                        paths.append(path)
                    video = folder / 'preview.mp4'
                    await asyncio.to_thread(render_video, paths, video, None, chosen)
                    with video.open('rb') as handle:
                        await query.message.reply_video(video=handle, caption=f'▶️ Contoh {chosen}. Pilih gaya di bawah.', reply_markup=style_menu(), supports_streaming=True)
            except Exception:
                logging.exception('Style preview failed')
                await query.message.reply_text('Preview gagal. Sila pilih gaya atau cuba semula.', reply_markup=style_menu())
            finally:
                context.user_data['busy'] = False
    elif action.startswith('style:') and stage == 'style':
        context.user_data['style'] = action.split(':', 1)[1]
        if context.user_data.get('storyboard_mode'):
            context.user_data['stage'] = 'doodle'
            await query.message.reply_text('Pilih efek garisan / doodle untuk prompt storyboard:', reply_markup=doodle_menu())
        else:
            context.user_data['stage'] = 'music'
            await query.message.reply_text(f"✅ Gaya {context.user_data['style']} dipilih.\\nLangkah 3/4 — Pilih muzik:", reply_markup=music_menu())
    elif action.startswith('doodle:') and stage == 'doodle' and context.user_data.get('storyboard_mode'):
        choice = action.split(':', 1)[1]
        if choice in DOODLE_OPTIONS:
            context.user_data['doodle_choice'] = choice
            context.user_data['stage'] = 'music'
            await query.message.reply_text('✅ Efek untuk storyboard: '+DOODLE_OPTIONS[choice]+'\\nEfek pilihan akan dimasukkan ke dalam MP4.\\nPilih muzik:', reply_markup=music_menu())
    elif action == 'music' and stage in ('music', 'confirm'):
        context.user_data['stage'] = 'music'
        await query.message.reply_text('Langkah 3/4 — Pilih muzik:', reply_markup=music_menu())
    elif action == 'music_previews' and stage == 'music':
        await query.message.reply_text('Tekan untuk mendengar contoh muzik:', reply_markup=music_preview_menu())
    elif action.startswith('listen:') and stage == 'music':
        name = action.split(':', 1)[1]
        if name in MUSIC_CHOICES and name not in ('auto', 'none', 'custom'):
            path = resolve_music(name, context.user_data.get('style', 'hybrid'))
            if path:
                with path.open('rb') as handle:
                    await query.message.reply_audio(audio=handle, title=name.title(), reply_markup=music_preview_menu())
            else:
                await query.message.reply_text('Fail muzik belum tersedia pada server.')
    elif action.startswith('music:') and stage == 'music':
        choice = action.split(':', 1)[1]
        if choice in MUSIC_CHOICES:
            context.user_data['music_choice'] = choice
            if choice != 'custom':
                context.user_data['music'] = None
            context.user_data['stage'] = 'confirm'
            await query.message.reply_text(('Hantar MP3 sendiri, kemudian tekan Hasilkan Video.' if choice == 'custom' else f'✅ Muzik {choice} dipilih.\nLangkah 4/4 — Semak dan hasilkan.'), reply_markup=confirm_menu())
    elif action == 'confirm' and stage == 'confirm':
        await generate(update, context)
    elif action == 'subscription':
        await query.message.reply_text('💎 LANGGANAN KLIPPO\n\nRM5 / 30 hari\nSehingga 30 video sebulan.\n\nBayar melalui QR DuitNow. Selepas pembayaran, upload resit untuk semakan admin.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📱 Papar QR DuitNow', callback_data='subscription_qr')], [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    elif action == 'subscription_qr':
        qr_path = Path(__file__).resolve().parent / 'klippo_qr.jpg'
        if not qr_path.is_file():
            await query.message.reply_text('QR pembayaran belum tersedia. Sila cuba lagi kemudian.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
        else:
            with qr_path.open('rb') as qr_file:
                await query.message.reply_photo(photo=qr_file, caption='💎 KLIPPO — DuitNow QR\n\nPelan Penyokong Awal: RM5 / 30 hari (sehingga 30 video sebulan).\n\nTekan 📎 Upload Resit selepas pembayaran. Pengaktifan adalah manual selepas semakan.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📎 Upload Resit', callback_data='receipt_upload')], [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    elif action == 'receipt_upload':
        context.user_data['stage'] = 'receipt_upload'
        await query.message.reply_text('📎 Sila hantar gambar atau fail PDF resit pembayaran di sini.')
    elif action == 'account':
        await account_info(update, context)
    elif action == 'help':
        await query.message.reply_text('❓ CARA GUNA\n\n1. Tekan Jana Video.\n2. Hantar 1–5 gambar, kemudian tekan Selesai.\n3. Lihat contoh dan pilih gaya.\n4. Dengar contoh dan pilih muzik.\n5. Tekan Hasilkan Video.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('↩️ Menu Utama', callback_data='home')]]))
    elif action == 'check':
        await status(update, context)
    elif action == 'reset':
        await start(update, context)
    elif action == 'home':
        await start(update, context)
    else:
        await query.message.reply_text('Pilihan lama telah tamat. Mulakan semula melalui menu utama.', reply_markup=main_menu())


async def menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stage = context.user_data.get('stage')
    value = update.message.text.strip()
    if value == '🏠 Menu Utama':
        await start(update, context)
        return
    shortcuts = {
        '🎬 Jana Video Affiliate': 'make',
        '🎬 Jana Video Transisi': 'make',
        '🔄 Tukar Format Video': 'convert',
        '✍️ Sediakan Prompt Video': 'prompt',
        '✍️ Hasilkan Prompt': 'prompt',
        '💎 Langganan': 'subscription',
        '👤 Akaun Saya': 'account',
        '❓ Bantuan': 'help',
        '🗑 Mula Semula': 'home',
    }
    if value in shortcuts:
        action = shortcuts[value]
        if action == 'make':
            reset(context)
            context.user_data['stage'] = 'photos'
            await update.message.reply_text('Langkah 1/4 — Hantar 1–5 gambar produk. Tekan Selesai apabila cukup.', reply_markup=photos_menu())
        elif action == 'convert':
            reset(context)
            context.user_data['stage'] = 'convert'
            await update.message.reply_text('🔄 TUKAR FORMAT VIDEO\n\nTekan 📎 → File / Fail → pilih video MP4 asal. Bot akan memprosesnya secara automatik.', reply_markup=main_menu())
        elif action == 'prompt':
            reset(context)
            context.user_data['stage'] = 'prompt_type'
            await update.message.reply_text('✍️ HASILKAN PROMPT — Pilih jenis:', reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('✨ Prompt Biasa', callback_data='prompt_type:normal')],
                [InlineKeyboardButton('🎞️ Prompt Storyboard (6 Babak)', callback_data='prompt_type:storyboard')],
                [InlineKeyboardButton('↩️ Menu Utama', callback_data='home')],
            ]))
        elif action == 'subscription':
            await update.message.reply_text('💎 LANGGANAN KLIPPO\n\nPelan Penyokong Awal: RM5 / 30 hari, sehingga 30 video sebulan. Pengaktifan manual selepas resit disemak.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📱 Papar QR DuitNow', callback_data='subscription_qr')]]))
        elif action == 'account':
            await account_info(update, context)
        elif action == 'help':
            await update.message.reply_text('❓ BANTUAN\n\nJana Video: hantar gambar, pilih gaya dan muzik.\nTukar Format: hantar MP4.\nVideo AI: upload gambar, tambah maklumat jika mahu, kemudian pilih latar dan gerakan kamera. Prompt digunakan bersama gambar di penjana video luar.')
        else:
            await start(update, context)
        return
    if stage == 'prompt_details_text':
        context.user_data['prompt_product'] = value[:600]
        context.user_data['stage'] = 'prompt_scene'
        await update.message.reply_text('Maklumat tambahan disimpan. Pilih latar atau taip Auto:')
    elif stage == 'prompt_scene':
        if len(value) < 5 and value.lower() != 'auto':
            await update.message.reply_text('Nyatakan latar ringkas atau taip Auto.')
            return
        context.user_data['prompt_scene'] = 'clean premium studio background' if value.lower() == 'auto' else value[:400]
        context.user_data['stage'] = 'prompt_motion'
        await update.message.reply_text('Langkah 2/2: Pilih gerakan kamera:', reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('🔄 Orbit Terkawal', callback_data='motion:orbit')],
            [InlineKeyboardButton('🔍 Zoom Masuk', callback_data='motion:push')],
            [InlineKeyboardButton('↔️ Gerak Sisi', callback_data='motion:side')],
            [InlineKeyboardButton('✨ Studio Statik', callback_data='motion:static')],
        ]))
    else:
        await update.message.reply_text('Gunakan butang menu di bawah.', reply_markup=main_menu())


async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    ids = context.user_data.get('photos', [])
    if not ids:
        await message.reply_text('Hantar gambar dahulu.', reply_markup=main_menu())
        return
    if context.user_data.get('busy'):
        await message.reply_text('Video sedang diproses.')
        return
    lock = context.application.bot_data.setdefault('render_lock', asyncio.Lock())
    if lock.locked():
        await message.reply_text('Server sedang menjana video lain. Cuba sebentar lagi.')
        return
    await lock.acquire()
    context.user_data['busy'] = True
    await message.reply_text('⏳ Menjana video, sila tunggu...')
    try:
        with tempfile.TemporaryDirectory(prefix='telegram_video_') as td:
            folder = Path(td)
            paths = []
            for i, fid in enumerate(list(ids)):
                p = folder / f'{i}.jpg'
                await (await context.bot.get_file(fid)).download_to_drive(p)
                paths.append(p)
            music = None
            if context.user_data.get('music_choice') == 'custom' and context.user_data.get('music'):
                music = folder / 'music.mp3'
                await (await context.bot.get_file(context.user_data['music'])).download_to_drive(music)
            elif context.user_data.get('music_choice') == 'custom':
                await message.reply_text('Sila hantar MP3 sendiri dahulu, atau pilih muzik lain.', reply_markup=music_menu())
                return
            elif context.user_data.get('music_choice', 'auto') != 'none':
                music = resolve_music(context.user_data.get('music_choice', 'auto'), context.user_data.get('style', 'hybrid'))
                if music is None:
                    await message.reply_text('Muzik pilihan belum tersedia pada server. Video akan dijana tanpa muzik.')
            result = folder / 'video.mp4'
            if context.user_data.get('storyboard_mode'):
                plan = build_storyboard(len(paths), context.user_data.get('duration', 10))
                await message.reply_text(format_storyboard(plan) + '\n\nEfek prompt: ' + DOODLE_OPTIONS[context.user_data.get('doodle_choice', 'none')] + '\nArahan AI: Tambah efek pilihan secara halus di luar label dan logo produk. Jangan ubah identiti produk. (Efek overlay turut dirender pada MP4.)')
                paths = [paths[i] for i in source_sequence(plan)]
                selected_style = 'cinematic'
                doodle = context.user_data.get('doodle_choice', 'none')
            else:
                selected_style = context.user_data.get('style', 'hybrid')
                doodle = 'none'
            await asyncio.to_thread(render_video, paths, result, music, selected_style, context.user_data.get('duration', 10), doodle)
            with result.open('rb') as f:
                await message.reply_video(video=f, caption='🎬 Video siap! Hantar gambar baharu untuk video seterusnya.', supports_streaming=True,
                                                 read_timeout=120, write_timeout=120)
        reset(context)
        await message.reply_text('Mahu buat video lagi? Hantar gambar baharu.', reply_markup=main_menu())
    except Exception:
        logging.exception('Video generation failed')
        await message.reply_text('❌ Gagal menjana video. Cuba kurangkan gambar atau semak log FFmpeg.')
    finally:
        context.user_data['busy'] = False
        lock.release()


def main():
    if not TOKEN:
        raise RuntimeError('BOT_TOKEN belum ditetapkan')
    if not shutil.which('ffmpeg'):
        raise RuntimeError('FFmpeg belum dipasang')
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('admin', admin))
    app.add_handler(CommandHandler('reset', start))
    app.add_handler(CommandHandler('periksa', status))
    app.add_handler(CommandHandler('jana', generate, block=False))
    for style in STYLES:
        app.add_handler(CommandHandler(style, choose_style))
    app.add_handler(CallbackQueryHandler(buttons, pattern=r'^(photos_order|photos_undo|photos_more|photo_up:[0-4]|photo_down:[0-4]|photo_remove:[0-4]|duration:(10|15|20)|admin_pending|admin_approve:[0-9]+|admin_reject:[0-9]+|admin|receipt_upload|subscription_qr|make|storyboard|doodle:(auto|white|sparkle|motion|all|none)|convert|merge|merge_next|merge_done|merge_style:(fade|smoothleft|slideleft|zoomin)|prompt|prompt_type:(normal|storyboard)|prompt_details:(add|skip)|motion:(orbit|push|side|static)|photos_done|confirm|styles|music|music_previews|subscription|account|help|check|reset|home|preview:(hybrid|cinematic|luxury|dynamic|zoom|smooth|creative|morph)|listen:(cinematic|energetic|happy|luxury|nature|beauty)|style:(hybrid|cinematic|luxury|dynamic|zoom|smooth|creative|morph)|music:(auto|cinematic|energetic|happy|luxury|nature|beauty|none|custom))$'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_text))
    app.add_handler(MessageHandler(filters.PHOTO, photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE | filters.Document.MimeType('application/pdf'), receive_receipt))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.MimeType('video/mp4'), convert_upload))
    app.add_handler(MessageHandler(filters.AUDIO | filters.Document.MimeType('audio/mpeg'), audio))
    url = os.environ.get('WEBHOOK_URL', '').rstrip('/')
    secret = os.environ.get('WEBHOOK_SECRET', '')
    if not url.startswith('https://') or not secret:
        raise RuntimeError('WEBHOOK_URL (https) dan WEBHOOK_SECRET wajib ditetapkan')
    app.run_webhook(
        listen='0.0.0.0',
        port=int(os.environ.get('PORT', '10000')),
        url_path='telegram',
        webhook_url=url + '/telegram',
        secret_token=secret,
        drop_pending_updates=True,
    )

if __name__ == '__main__':
    main()

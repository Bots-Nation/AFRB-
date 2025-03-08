@Client.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def auto_rename_files(client, message: Message):
    user_id = message.from_user.id
    user = message.from_user

    # Initialize file_id and file_name early
    file_id = None
    file_name = None

    # Check if the user is an admin.
    is_admin = False
    if hasattr(Config, "ADMINS") and user_id in Config.ADMINS:
        is_admin = True

    # Check premium status
    user_data = await codeflixbots.col.find_one({"_id": int(user_id)})  
    is_premium = user_data.get("is_premium", False) if user_data else False
    premium_expiry = user_data.get("premium_expiry")
    if is_premium and premium_expiry:
        if datetime.now() < premium_expiry:
            is_premium = True
        else:
            await codeflixbots.col.update_one(
                {"_id": user_id},
                {"$set": {"is_premium": False, "premium_expiry": None}}
            )
            is_premium = False

    if not is_premium:
        current_tokens = user_data.get("token", 69)
        if current_tokens <= 0:
            await message.reply_text(
                "❌ You've run out of tokens!\n\n"
                "Generate more tokens by completing short links.",
            )
            return

        # Deduct token
        new_tokens = current_tokens - 1
        await codeflixbots.col.update_one(
            {"_id": user_id},
            {"$set": {"token": new_tokens}}
        )

    concurrency_limit = 8 if (is_admin or is_premium) else 4
    if user_id in USER_LIMITS:
        if USER_LIMITS[user_id] != concurrency_limit:
            USER_SEMAPHORES[user_id] = asyncio.Semaphore(concurrency_limit)
            USER_LIMITS[user_id] = concurrency_limit
    else:
        USER_LIMITS[user_id] = concurrency_limit
        USER_SEMAPHORES[user_id] = asyncio.Semaphore(concurrency_limit)

    semaphore = USER_SEMAPHORES[user_id]

    async with semaphore:
        if user_id in active_sequences:
            # Ensure file_id and file_name are defined
            if message.document:
                file_id = message.document.file_id
                file_name = message.document.file_name
            elif message.video:
                file_id = message.video.file_id
                file_name = f"{message.video.file_name}.mp4"
            elif message.audio:
                file_id = message.audio.file_id
                file_name = f"{message.audio.file_name}.mp3"

            file_info = {
                "file_id": file_id,
                "file_name": file_name if file_name else "Unknown"
            }
            active_sequences[user_id].append(file_info)
            await message.reply_text(f"File received in sequence...")
            return

        # Auto-Rename Logic (Runs only when not in sequence mode)
        format_template = await codeflixbots.get_format_template(user_id)
        media_preference = await codeflixbots.get_media_preference(user_id)

        if not format_template:
            return await message.reply_text(
                "Please Set An Auto Rename Format First Using /autorename"
            )

        if message.document:
            file_id = message.document.file_id
            file_name = message.document.file_name
            media_type = media_preference or "document"
        elif message.video:
            file_id = message.video.file_id
            file_name = f"{message.video.file_name}.mp4"
            media_type = media_preference or "video"
        elif message.audio:
            file_id = message.audio.file_id
            file_name = f"{message.audio.file_name}.mp3"
            media_type = media_preference or "audio"
        else:
            return await message.reply_text("Unsupported File Type")

        # Anti-NSFW check
        if await check_anti_nsfw(file_name, message):
            return await message.reply_text("NSFW content detected. File upload rejected.")

        if file_id in renaming_operations:
            elapsed_time = (datetime.now() - renaming_operations[file_id]).seconds
            if elapsed_time < 10:
                return

        renaming_operations[file_id] = datetime.now()

        episode_number = extract_episode_number(file_name)
        if episode_number:
            placeholders = ["episode", "Episode", "EPISODE", "{episode}"]
            for placeholder in placeholders:
                format_template = format_template.replace(placeholder, str(episode_number), 1)

            # Add extracted qualities to the format template
            quality_placeholders = ["quality", "Quality", "QUALITY", "{quality}"]
            for quality_placeholder in quality_placeholders:
                if quality_placeholder in format_template:
                    extracted_qualities = extract_quality(file_name)
                    if extracted_qualities == "Unknown":
                        await message.reply_text("**__I Was Not Able To Extract The Quality Properly. Renaming As 'Unknown'...__**")
                        # Mark the file as ignored
                        del renaming_operations[file_id]
                        return  # Exit the handler if quality extraction fails
                
                    format_template = format_template.replace(quality_placeholder, "".join(extracted_qualities))

        _, file_extension = os.path.splitext(file_name)
        renamed_file_name = f"{format_template}{file_extension}"
        renamed_file_path = f"downloads/{renamed_file_name}"
        metadata_file_path = f"Metadata/{renamed_file_name}"
        os.makedirs(os.path.dirname(renamed_file_path), exist_ok=True)
        os.makedirs(os.path.dirname(metadata_file_path), exist_ok=True)

        download_msg = await message.reply_text("**__Downloading...__**")

        try:
            path = await client.download_media(
                message,
                file_name=renamed_file_path,
                progress=progress_for_pyrogram,
                progress_args=("Download Started...", download_msg, time.time()),
            )
        except Exception as e:
            del renaming_operations[file_id]
            return await download_msg.edit(f"**Download Error:** {e}")

        await download_msg.edit("**__Renaming and Adding Metadata...__**")

        try:
            # Rename the file
            os.rename(path, renamed_file_path)
            path = renamed_file_path

            # Prepare metadata command
            ffmpeg_cmd = shutil.which('ffmpeg')
            metadata_command = [
                ffmpeg_cmd,
                '-i', path,
                '-metadata', f'title={await codeflixbots.get_title(user_id)}',
                '-metadata', f'artist={await codeflixbots.get_artist(user_id)}',
                '-metadata', f'author={await codeflixbots.get_author(user_id)}',
                '-metadata:s:v', f'title={await codeflixbots.get_video(user_id)}',
                '-metadata:s:a', f'title={await codeflixbots.get_audio(user_id)}',
                '-metadata:s:s', f'title={await codeflixbots.get_subtitle(user_id)}',
                '-metadata', f'encoded_by={await codeflixbots.get_encoded_by(user_id)}',
                '-metadata', f'custom_tag={await codeflixbots.get_custom_tag(user_id)}',
                '-map', '0',
                '-c', 'copy',
                '-loglevel', 'error',
                metadata_file_path
            ]

            # Execute the metadata command
            process = await asyncio.create_subprocess_exec(
                *metadata_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_message = stderr.decode()
                await download_msg.edit(f"**Metadata Error:**\n{error_message}")
                return
                
            # Use the new metadata file path for the upload
            path = metadata_file_path

            # Upload the file
            upload_msg = await download_msg.edit("**__Uploading...__**")
            await codeflixbots.col.update_one(
                {"_id": user_id},
                {"$inc": {"rename_count": 1}}
            )

            ph_path = None
            c_caption = await codeflixbots.get_caption(message.chat.id)
            c_thumb = await codeflixbots.get_thumbnail(message.chat.id)

            caption = (
                c_caption.format(
                    filename=renamed_file_name,
                    filesize=humanbytes(message.document.file_size),
                    duration=convert(0),
                )
                if c_caption
                else f"**{renamed_file_name}**"
            )

            if c_thumb:
                ph_path = await client.download_media(c_thumb)
            elif media_type == "video" and message.video.thumbs:
                ph_path = await client.download_media(message.video.thumbs[0].file_id)

            if ph_path:
                img = Image.open(ph_path).convert("RGB")
                img = img.resize((320, 320))
                img.save(ph_path, "JPEG")

            try:
                # Send to USER and capture the sent message
                if media_type == "document":
                    user_sent_message = await client.send_document(
                        message.chat.id,
                        document=path,
                        thumb=ph_path,
                        caption=caption,
                        progress=progress_for_pyrogram,
                        progress_args=("Upload Started...", upload_msg, time.time()),
                    )
                elif media_type == "video":
                    user_sent_message = await client.send_video(
                        message.chat.id,
                        video=path,
                        caption=caption,
                        thumb=ph_path,
                        duration=0,
                        progress=progress_for_pyrogram,
                        progress_args=("Upload Started...", upload_msg, time.time()),
                    )
                elif media_type == "audio":
                    user_sent_message = await client.send_audio(
                        message.chat.id,
                        audio=path,
                        caption=caption,
                        thumb=ph_path,
                        duration=0,
                        progress=progress_for_pyrogram,
                        progress_args=("Upload Started...", upload_msg, time.time()),
                    )

                # Now forward the sent message to DUMP CHANNEL with forward tag
                if Config.DUMP_CHANNEL:
                    try:
                        timestamp = datetime.now(pytz.timezone("Asia/Kolkata")).strftime('%Y-%m-%d %H:%M:%S %Z')
                        user_details = (
                            f"👤 **User Details**\n"
                            f"• ID: `{user.id}`\n"
                            f"• Name: {user.first_name or 'Unknown'}\n"
                            f"• Username: @{user.username if user.username else 'N/A'}\n"
                            f"• Premium: {'✅' if is_premium else '❌'}\n"
                            f"⏰ Time: `{timestamp}`\n"
                            f"📄 Original Filename: `{file_name}`\n"
                            f"🔄 Renamed Filename: `{renamed_file_name}`\n"
                        )

                        # Use copy_message to forward with a custom caption
                        await client.copy_message(
                            chat_id=Config.DUMP_CHANNEL,
                            from_chat_id=message.chat.id,
                            message_id=user_sent_message.id,
                            caption=user_details
                        )

                        logging.info(f"File forwarded to dump channel: {renamed_file_name}")

                    except Exception as e:
                        error_msg = f"⚠️ Failed to forward file to dump channel: {str(e)}"
                        await client.send_message(Config.LOG_CHANNEL, error_msg)
                        logging.error(error_msg, exc_info=True)

            except Exception as e:
                logging.error(f"Error Upload file: {e}")

            await download_msg.delete() 

        except Exception as e:
            logging.error(f"Error in file processing: {e}")
            await download_msg.edit(f"**Error:** {e}")

        finally:
            # Clean up
            if os.path.exists(renamed_file_path):
                os.remove(renamed_file_path)
            if os.path.exists(metadata_file_path):
                os.remove(metadata_file_path)
            if ph_path and os.path.exists(ph_path):
                os.remove(ph_path)
            if file_id in renaming_operations:
                del renaming_operations[file_id]

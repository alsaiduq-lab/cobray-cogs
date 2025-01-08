import asyncio
import base64
import json
import logging
import os
import re
import tempfile
from typing import Optional

import aiohttp
import discord
from discord.ext import commands

log = logging.getLogger("red.ComfyAPI")

IMAGE_MIME_REGEX = re.compile(r"^image/(png|jpe?g|gif|webp)$", re.IGNORECASE)
VIDEO_MIME_REGEX = re.compile(r"^video/(mp4|webm)$", re.IGNORECASE)


async def run_workflow(
    ctx: commands.Context,
    workflow: dict,
    base_url: str = "http://localhost:8188",
    endpoint: str = "/workflow",
    timeout_seconds: int = 60,
):
    """
    Send a workflow to the ComfyUI API and handle the response.

    This function:
      - Posts the workflow to ComfyUI.
      - Checks status codes and content-type.
      - If an image/video is returned directly, uploads it to Discord.
      - If JSON is returned, tries to parse potential base64 or multiple media.
      - Otherwise, sends fallback text to Discord.

    :param ctx: Redbot command context.
    :param workflow: Python dict representing the workflow.
    :param base_url: The ComfyUI server base URL.
    :param endpoint: The endpoint to POST workflows to.
    :param timeout_seconds: The number of seconds before request times out.
    """
    url = f"{base_url.rstrip('/')}{endpoint}"
    log.debug(f"Sending workflow to ComfyUI endpoint: {url}")

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.post(url, json=workflow) as response:
                status = response.status
                content_type = response.headers.get("Content-Type", "").lower()

                if status != 200:
                    text_data = await safe_read_text(response)
                    await ctx.send(
                        f"Failed to run workflow. HTTP status: {status}\n"
                        f"Server response (truncated): {text_data[:1000]}"
                    )
                    return

                if IMAGE_MIME_REGEX.match(content_type):
                    await handle_direct_file_response(ctx, response, file_type="image")
                elif VIDEO_MIME_REGEX.match(content_type):
                    await handle_direct_file_response(ctx, response, file_type="video")
                elif "application/json" in content_type:
                    json_data = await safe_read_json(response)
                    if json_data is None:
                        await ctx.send("Could not parse JSON response from ComfyUI.")
                        return
                    await handle_json_response(ctx, json_data)
                else:
                    text_data = await safe_read_text(response)
                    await ctx.send(f"Workflow executed. Response:\n{text_data[:2000]}")
        except asyncio.TimeoutError:
            await ctx.send(
                f"Request to ComfyUI timed out after {timeout_seconds} seconds."
            )
        except aiohttp.ClientConnectionError as e:
            log.error("Error communicating with ComfyUI API (connection error): %s", e)
            await ctx.send(f"Connection error: {e}")
        except aiohttp.ClientError as e:
            log.error("aiohttp.ClientError encountered: %s", e, exc_info=True)
            await ctx.send(f"An unexpected client error occurred: {e}")
        except Exception as e:
            log.error(
                "Unexpected exception while processing ComfyUI response.", exc_info=True
            )
            await ctx.send(f"An unexpected error occurred: {e}")


async def handle_direct_file_response(
    ctx: commands.Context, response: aiohttp.ClientResponse, file_type: str
):
    """
    Save and send a single file (image or video) returned directly in the HTTP response.
    """
    data = await response.read()
    content_type = response.headers.get("Content-Type", "").lower()
    guessed_ext = guess_extension_from_content_type(content_type) or ".dat"

    file_path = await save_temp_file(data, guessed_ext)
    try:
        await ctx.send(
            file=discord.File(file_path, filename=f"comfy_output{guessed_ext}")
        )
    except discord.HTTPException as e:
        log.error("Error sending file to Discord: %s", e, exc_info=True)
        await ctx.send(f"Failed to upload the {file_type} to Discord: {e}")
    finally:
        cleanup_file(file_path)


async def handle_json_response(ctx: commands.Context, json_data: dict):
    """
    Handle a JSON response from ComfyUI. This may contain:
      - textual data
      - direct base64 image/video content
      - multiple images/videos
      - or anything else your ComfyUI server might return.
    """
    images = json_data.get("images", [])
    videos = json_data.get("videos", [])
    base64_str = json_data.get("base64_image")

    # If we have direct lists of images/videos
    if images or videos:
        await handle_multiple_media(ctx, images, videos)
        return

    if isinstance(base64_str, str):
        try:
            img_data = base64.b64decode(base64_str)
            file_path = await save_temp_file(img_data, ".png")
            try:
                await ctx.send(
                    file=discord.File(file_path, filename="comfy_output.png")
                )
            except discord.HTTPException as e:
                log.error("Error sending base64 file to Discord: %s", e, exc_info=True)
                await ctx.send(f"Failed to upload the base64 image: {e}")
            finally:
                cleanup_file(file_path)
            return
        except base64.binascii.Error:
            await ctx.send("Invalid base64 data in JSON response.")
            return

    snippet = json.dumps(json_data, indent=2)
    if len(snippet) > 1900:
        snippet = snippet[:1900] + "...\n(Truncated)"
    await ctx.send(f"JSON response:\n```json\n{snippet}\n```")


async def handle_multiple_media(ctx: commands.Context, images: list, videos: list):
    """
    Example function to handle lists of base64-encoded images/videos from JSON.
    If they are URLs, you'd fetch them with aiohttp, etc. Adjust as necessary.
    """
    # Handle images
    for idx, img_str in enumerate(images, start=1):
        if isinstance(img_str, str):
            try:
                img_data = base64.b64decode(img_str)
            except base64.binascii.Error:
                await ctx.send(f"Invalid base64 in images[{idx}]. Skipping...")
                continue

            path = await save_temp_file(img_data, ".png")
            try:
                await ctx.send(
                    file=discord.File(path, filename=f"comfy_image_{idx}.png")
                )
            except discord.HTTPException as e:
                log.error("Error sending image file to Discord: %s", e, exc_info=True)
                await ctx.send(f"Failed to upload image {idx}: {e}")
            finally:
                cleanup_file(path)

    for idx, vid_str in enumerate(videos, start=1):
        if isinstance(vid_str, str):
            try:
                vid_data = base64.b64decode(vid_str)
            except base64.binascii.Error:
                await ctx.send(f"Invalid base64 in videos[{idx}]. Skipping...")
                continue

            path = await save_temp_file(vid_data, ".mp4")
            try:
                await ctx.send(
                    file=discord.File(path, filename=f"comfy_video_{idx}.mp4")
                )
            except discord.HTTPException as e:
                log.error("Error sending video file to Discord: %s", e, exc_info=True)
                await ctx.send(f"Failed to upload video {idx}: {e}")
            finally:
                cleanup_file(path)


async def safe_read_text(response: aiohttp.ClientResponse) -> str:
    """Safely read text from the HTTP response."""
    try:
        return await response.text()
    except (aiohttp.ClientError, UnicodeDecodeError) as e:
        log.error("Could not read text response: %s", e, exc_info=True)
        return "<Unable to read text response>"


async def safe_read_json(response: aiohttp.ClientResponse) -> Optional[dict]:
    """Safely parse JSON from the HTTP response. Return None on error."""
    try:
        return await response.json()
    except (aiohttp.ClientError, json.JSONDecodeError) as e:
        log.error("Error parsing JSON response: %s", e, exc_info=True)
        return None


def guess_extension_from_content_type(content_type: str) -> Optional[str]:
    """Guess a file extension from a given Content-Type string."""
    if "png" in content_type:
        return ".png"
    if "jpeg" in content_type or "jpg" in content_type:
        return ".jpg"
    if "gif" in content_type:
        return ".gif"
    if "webp" in content_type:
        return ".webp"
    if "mp4" in content_type:
        return ".mp4"
    if "webm" in content_type:
        return ".webm"
    return None


async def save_temp_file(data: bytes, suffix: str) -> str:
    """
    Save data bytes to a named temporary file with the specified suffix (extension).
    Return the temporary file path (caller must clean up).
    """
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(data)
            return tmp_file.name
    except Exception as e:
        log.error("Failed to save temporary file: %s", e, exc_info=True)
        raise


def cleanup_file(file_path: str):
    """Remove the temporary file, ignoring certain errors."""
    try:
        os.remove(file_path)
    except FileNotFoundError:
        pass
    except PermissionError as e:
        log.warning("Could not remove temp file (permission error): %s", e)
    except Exception as e:
        log.error("Unexpected error removing temp file: %s", e, exc_info=True)

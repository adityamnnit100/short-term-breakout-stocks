"""
Service to connect to Telegram as a user client to read channel messages.
Uses the Telethon library.
"""
import asyncio
import streamlit as st
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.errors.rpcerrorlist import ApiIdInvalidError, PhoneNumberInvalidError


@st.cache_resource(ttl=3600)
def get_telegram_client(api_id, api_hash, session_string=None):
    """
    Creates and returns a Telethon client.
    Caches the client resource for performance.
    """
    if not api_id or not api_hash:
        return None
    
    # Use an in-memory session for Streamlit's execution model
    client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
    return client


async def fetch_messages_from_channel(client: TelegramClient, channel_entity, limit=100):
    """
    Asynchronously fetches messages from a specific Telegram channel/group.
    """
    messages_data = []
    if not client.is_connected():
        await client.connect()

    try:
        entity = await client.get_entity(channel_entity)
        messages = await client.get_messages(entity, limit=limit)
        
        for message in messages:
            if message and message.text:
                messages_data.append({
                    "id": message.id,
                    "date": message.date,
                    "text": message.text,
                    "sender_id": message.sender_id,
                })
    except ValueError:
        # Raised if the channel is not found
        return None, "Channel not found. Please check the name or ID."
    except Exception as e:
        return None, f"An error occurred: {e}"
    finally:
        if client.is_connected():
            await client.disconnect()
            
    return messages_data, None